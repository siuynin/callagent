import uuid

from conftest import ADMIN_A, ADMIN_B, STAFF_A, TENANT_A, TENANT_B, auth

from voiceos.models import AuditEvent, Call, OutboxMessage
from voiceos.seed import USER_ADMIN_A


def _create(client, headers, key="k1", **body):
    payload = {"name": "Khách thử", "phone": "0900000009", **body}
    return client.post("/api/v1/contacts", json=payload, headers={**headers, "Idempotency-Key": key})


def test_health_exposes_safe_modes(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["modes"]["outbound_enabled"] is False
    assert r.headers["x-trace-id"]


def test_auth_required_and_error_envelope(client):
    r = client.get("/api/v1/contacts")
    assert r.status_code == 401
    body = r.json()
    assert body["error"]["code"] == "UNAUTHENTICATED" and body["trace_id"]


def test_me(client):
    r = client.get("/api/v1/me", headers=ADMIN_A)
    assert r.json()["tenant"]["timezone"] == "Asia/Ho_Chi_Minh"
    assert r.json()["display_name"] == "Quản trị A" and r.json()["role"] == "admin"


# --- AC01 tenant isolation ---


def test_tenant_b_cannot_list_or_read_tenant_a_contacts(client):
    a_items = client.get("/api/v1/contacts", headers=ADMIN_A).json()["items"]
    assert len(a_items) == 3
    assert client.get("/api/v1/contacts", headers=ADMIN_B).json()["items"] == []
    guessed = a_items[0]["id"]
    r = client.get(f"/api/v1/contacts/{guessed}", headers=ADMIN_B)
    assert r.status_code == 404  # not 403: do not reveal existence
    r = client.patch(f"/api/v1/contacts/{guessed}", json={"name": "x"}, headers={**ADMIN_B, "If-Match": "1"})
    assert r.status_code == 404


def test_cannot_switch_to_tenant_without_membership(client):
    r = client.get("/api/v1/contacts", headers=auth(USER_ADMIN_A, TENANT_B))
    assert r.status_code == 403
    r = client.get("/api/v1/contacts", headers=auth(USER_ADMIN_A, TENANT_A))
    assert r.status_code == 200


def test_tenant_b_cannot_read_tenant_a_call(client, session_factory):
    from voiceos.db import utcnow

    with session_factory() as s:
        call = Call(
            tenant_id=TENANT_A,
            direction="inbound",
            provider="mock",
            provider_call_id="c1",
            started_at=utcnow(),
        )
        s.add(call)
        s.commit()
        call_id = call.id
    assert client.get(f"/api/v1/calls/{call_id}", headers=ADMIN_A).status_code == 200
    assert client.get(f"/api/v1/calls/{call_id}", headers=ADMIN_B).status_code == 404
    assert client.get("/api/v1/calls", headers=ADMIN_B).json()["items"] == []


# --- contacts write path ---


def test_create_contact_normalizes_and_audits(client, session_factory):
    r = _create(client, STAFF_A, phone="090 000 0009")
    assert r.status_code == 201
    data = r.json()["data"]
    assert data["normalized_phone"] == "+84900000009" and data["phone_status"] == "valid"
    with session_factory() as s:
        assert s.query(AuditEvent).filter_by(object_id=uuid.UUID(data["id"]), action="create").count() == 1
        assert s.query(OutboxMessage).filter_by(topic="contact.created").count() == 1


def test_invalid_phone_is_stored_with_reason_not_rejected(client):
    r = _create(client, STAFF_A, phone="12345")
    assert r.status_code == 201
    assert r.json()["phone_check"] == {"status": "invalid", "reason": "bad_length_or_prefix"}


def test_idempotency_replay_and_conflict(client):
    first = _create(client, STAFF_A, key="same")
    replay = _create(client, STAFF_A, key="same")
    assert replay.status_code == 201
    assert replay.json()["data"]["id"] == first.json()["data"]["id"]
    assert len(client.get("/api/v1/contacts", headers=ADMIN_A).json()["items"]) == 4
    changed = _create(client, STAFF_A, key="same", name="Khác")
    assert changed.status_code == 409
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_idempotency_key_required(client):
    r = client.post("/api/v1/contacts", json={"name": "a", "phone": "0900000009"}, headers=STAFF_A)
    assert r.status_code == 400 and r.json()["error"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_idempotency_keys_are_per_tenant(client):
    a = _create(client, ADMIN_A, key="shared")
    b = _create(client, ADMIN_B, key="shared")
    assert a.status_code == b.status_code == 201
    assert a.json()["data"]["id"] != b.json()["data"]["id"]


def test_patch_requires_if_match_and_detects_conflict(client):
    cid = _create(client, STAFF_A).json()["data"]["id"]
    url = f"/api/v1/contacts/{cid}"
    assert client.patch(url, json={"need": "x"}, headers=STAFF_A).status_code == 428
    ok = client.patch(url, json={"need": "Lái thử"}, headers={**STAFF_A, "If-Match": "1"})
    assert ok.status_code == 200 and ok.json()["data"]["version"] == 2
    stale = client.patch(url, json={"need": "Khác"}, headers={**STAFF_A, "If-Match": "1"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_unknown_fields_rejected(client):
    r = _create(client, STAFF_A, tenant_id=str(TENANT_B))  # tenant must never come from the body
    assert r.status_code == 400


def test_pagination_cursor(client):
    for i in range(4):
        _create(client, STAFF_A, key=f"p{i}", phone=f"090000001{i}")
    page1 = client.get("/api/v1/contacts?limit=5", headers=ADMIN_A).json()
    page2 = client.get(f"/api/v1/contacts?limit=5&cursor={page1['next_cursor']}", headers=ADMIN_A).json()
    ids = [c["id"] for c in page1["items"] + page2["items"]]
    assert len(ids) == 7 and len(set(ids)) == 7 and page2["next_cursor"] is None


def test_filter_by_phone_uses_normalization(client):
    r = client.get("/api/v1/contacts", params={"phone": "+84 900 000 001"}, headers=ADMIN_A)
    assert [c["name"] for c in r.json()["items"]] == ["Khách mẫu A"]


def test_dev_auth_refused_outside_dev():
    import pytest

    from voiceos.config import Settings

    with pytest.raises(RuntimeError):
        Settings(app_env="production", dev_auth=True).check_safety()
