from datetime import timedelta

from conftest import ADMIN_A, ADMIN_B, STAFF_A, TENANT_A

from voiceos.db import utcnow
from voiceos.models import OutboxMessage, Task
from voiceos.seed import USER_ADMIN_A, USER_ADMIN_B, USER_STAFF_A


def _create(client, headers=ADMIN_A, key="t1", **body):
    payload = {"type": "human_request", "title": "Khách muốn gặp nhân viên", **body}
    r = client.post("/api/v1/tasks", json=payload, headers={**headers, "Idempotency-Key": key})
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _patch(client, task, headers=ADMIN_A, **body):
    return client.patch(
        f"/api/v1/tasks/{task['id']}", json=body, headers={**headers, "If-Match": str(task["version"])}
    )


# --- AC08 ---


def test_in_progress_requires_owner(client):
    t = _create(client)
    r = _patch(client, t, status="in_progress")
    assert r.status_code == 422
    assert "owner_id" in r.json()["error"]["field_errors"]
    ok = _patch(client, t, status="in_progress", owner_id=str(USER_STAFF_A))
    assert ok.status_code == 200 and ok.json()["data"]["owner"]["name"] == "Nhân viên A"


def test_resolved_requires_resolution_note(client):
    t = _create(client, owner_id=str(USER_STAFF_A))
    r = _patch(client, t, status="resolved")
    assert r.status_code == 422 and "resolution_note" in r.json()["error"]["field_errors"]
    r = _patch(client, t, status="resolved", resolution_note="   ")
    assert r.status_code == 422
    ok = _patch(client, t, status="resolved", resolution_note="Đã gọi lại, khách hẹn thứ Bảy")
    data = ok.json()["data"]
    assert data["status"] == "resolved" and data["resolved_at"]


def test_closed_task_cannot_reopen(client):
    t = _create(client, owner_id=str(USER_STAFF_A))
    t = _patch(client, t, status="resolved", resolution_note="xong").json()["data"]
    r = _patch(client, t, status="in_progress")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INVALID_TRANSITION"


def test_overdue_uses_server_clock(client):
    past = (utcnow() - timedelta(minutes=15)).isoformat()
    future = (utcnow() + timedelta(hours=2)).isoformat()
    _create(client, key="a", due_at=past)
    _create(client, key="b", due_at=future)
    items = client.get("/api/v1/tasks", headers=ADMIN_A).json()["items"]
    assert [i["overdue"] for i in items] == [True, False]  # overdue sorted first (earlier deadline)
    assert len(client.get("/api/v1/tasks?overdue=true", headers=ADMIN_A).json()["items"]) == 1
    summary = client.get("/api/v1/tasks/summary", headers=ADMIN_A).json()
    assert summary["overdue"] == 1 and summary["unassigned"] == 2


def test_resolved_task_is_never_overdue(client):
    past = (utcnow() - timedelta(hours=1)).isoformat()
    t = _create(client, due_at=past, owner_id=str(USER_STAFF_A))
    _patch(client, t, status="resolved", resolution_note="xong")
    assert client.get("/api/v1/tasks/summary", headers=ADMIN_A).json()["overdue"] == 0


# --- permissions and tenancy ---


def test_staff_can_take_unassigned_but_not_others(client):
    free = _create(client, key="free")
    r = _patch(client, free, headers=STAFF_A, owner_id=str(USER_STAFF_A), status="in_progress")
    assert r.status_code == 200
    mine_to_admin = _patch(client, r.json()["data"], headers=STAFF_A, owner_id=str(USER_ADMIN_A))
    assert mine_to_admin.status_code == 403
    others = _create(client, key="others", owner_id=str(USER_ADMIN_A))
    assert _patch(client, others, headers=STAFF_A, status="in_progress").status_code == 403


def test_owner_must_belong_to_tenant(client):
    t = _create(client)
    r = _patch(client, t, owner_id=str(USER_ADMIN_B))
    assert r.status_code == 422 and r.json()["error"]["code"] == "OWNER_NOT_MEMBER"


def test_tenant_isolation(client):
    t = _create(client)
    assert client.get("/api/v1/tasks", headers=ADMIN_B).json()["items"] == []
    r = client.patch(
        f"/api/v1/tasks/{t['id']}", json={"status": "cancelled"}, headers={**ADMIN_B, "If-Match": "1"}
    )
    assert r.status_code == 404
    assert client.get("/api/v1/tasks/summary", headers=ADMIN_B).json()["unassigned"] == 0


def test_contact_from_other_tenant_rejected(client):
    other = client.post(
        "/api/v1/contacts",
        json={"name": "B", "phone": "0900000099"},
        headers={**ADMIN_B, "Idempotency-Key": "c"},
    ).json()["data"]
    r = client.post(
        "/api/v1/tasks",
        json={"type": "callback", "title": "x", "contact_id": other["id"]},
        headers={**ADMIN_A, "Idempotency-Key": "x"},
    )
    assert r.status_code == 422


def test_version_conflict_and_if_match(client):
    t = _create(client)
    assert (
        client.patch(f"/api/v1/tasks/{t['id']}", json={"priority": "high"}, headers=ADMIN_A).status_code
        == 428
    )
    assert _patch(client, t, priority="high").status_code == 200
    stale = _patch(client, t, priority="normal")  # still version 1
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_assignment_emits_outbox_and_idempotent_create(client, session_factory):
    t1 = _create(client, key="same", owner_id=str(USER_STAFF_A))
    t2 = _create(client, key="same", owner_id=str(USER_STAFF_A))
    assert t1["id"] == t2["id"]
    with session_factory() as s:
        assert s.query(Task).filter_by(tenant_id=TENANT_A).count() == 1
        assert s.query(OutboxMessage).filter_by(topic="task.assigned").count() == 1


def test_members_directory(client):
    items = client.get("/api/v1/members", headers=STAFF_A).json()["items"]
    assert {m["name"] for m in items} == {"Quản trị A", "Nhân viên A"}
    assert set(items[0]) == {"user_id", "name", "role"}  # no emails or contact data


def test_unauthenticated_cannot_create(client):
    # unauthenticated cannot create
    r = client.post(
        "/api/v1/tasks", json={"type": "callback", "title": "x"}, headers={"Idempotency-Key": "k"}
    )
    assert r.status_code == 401
