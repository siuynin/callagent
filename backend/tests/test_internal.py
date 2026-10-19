from datetime import timedelta

from conftest import ADMIN_A, ADMIN_B, TENANT_A, TENANT_B

from voiceos.db import utcnow
from voiceos.models import Task

SVC = {"X-Service-Token": "test-service-token", "X-Tenant-Id": str(TENANT_A)}
SVC_B = {"X-Service-Token": "test-service-token", "X-Tenant-Id": str(TENANT_B)}


def _call(client, provider_call_id="gw-1", headers=SVC, **body):
    payload = {
        "provider": "openai",
        "provider_call_id": provider_call_id,
        "started_at": utcnow().isoformat(),
        **body,
    }
    r = client.post("/api/v1/internal/calls", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_service_token_required(client):
    body = {"provider": "openai", "provider_call_id": "x", "started_at": utcnow().isoformat()}
    assert client.post("/api/v1/internal/calls", json=body).status_code == 401
    bad = {**SVC, "X-Service-Token": "wrong"}
    assert client.post("/api/v1/internal/calls", json=body, headers=bad).status_code == 401
    # a user session cannot use internal routes either
    assert client.post("/api/v1/internal/calls", json=body, headers=ADMIN_A).status_code == 401


def test_internal_api_disabled_without_token(client, monkeypatch):
    from voiceos.config import get_settings

    monkeypatch.setattr(get_settings(), "gateway_service_token", "")
    body = {"provider": "openai", "provider_call_id": "x", "started_at": utcnow().isoformat()}
    assert client.post("/api/v1/internal/calls", json=body, headers=SVC).status_code == 503


def test_create_call_is_idempotent_and_visible_to_users(client):
    first = _call(client)
    again = _call(client)
    assert first["created"] and not again["created"] and first["id"] == again["id"]
    calls = client.get("/api/v1/calls", headers=ADMIN_A).json()["items"]
    assert [c["id"] for c in calls] == [first["id"]]
    assert client.get("/api/v1/calls", headers=ADMIN_B).json()["items"] == []


def test_caller_number_links_single_contact_only(client):
    # seed: Khách mẫu A has +84900000001
    linked = _call(client, "gw-link", caller_number="0900000001")
    detail = client.get(f"/api/v1/calls/{linked['id']}", headers=ADMIN_A).json()["data"]
    assert detail["contact_name"] == "Khách mẫu A"
    # second contact on the same phone: shared family phone, do not guess (AC03)
    client.post(
        "/api/v1/contacts",
        json={"name": "Người nhà A", "phone": "+84900000001"},
        headers={**ADMIN_A, "Idempotency-Key": "fam"},
    )
    shared = _call(client, "gw-shared", caller_number="0900000001")
    assert client.get(f"/api/v1/calls/{shared['id']}", headers=ADMIN_A).json()["data"]["contact_id"] is None


def test_turns_and_tool_runs_are_idempotent(client):
    cid = _call(client)["id"]
    turns = {
        "turns": [
            {"seq": 1, "speaker": "agent", "text": "Xin chào", "started_ms": 0},
            {"seq": 2, "speaker": "customer", "text": "Cho hỏi", "started_ms": 2000},
        ]
    }
    assert client.post(f"/api/v1/internal/calls/{cid}/turns", json=turns, headers=SVC).json()["accepted"] == 2
    again = client.post(f"/api/v1/internal/calls/{cid}/turns", json=turns, headers=SVC).json()
    assert again == {**again, "accepted": 0, "duplicates": 2}
    runs = {
        "runs": [
            {
                "seq": 1,
                "tool": "check_available_slots",
                "args": {"date": "2026-10-20"},
                "status": "ok",
                "result": {"slots": ["15:00"]},
                "idempotency_key": "gw-1:call_a",
                "started_ms": 3000,
                "duration_ms": 12,
            }
        ]
    }
    assert (
        client.post(f"/api/v1/internal/calls/{cid}/tool-runs", json=runs, headers=SVC).json()["accepted"] == 1
    )
    assert (
        client.post(f"/api/v1/internal/calls/{cid}/tool-runs", json=runs, headers=SVC).json()["accepted"] == 0
    )
    detail = client.get(f"/api/v1/calls/{cid}", headers=ADMIN_A).json()
    assert [t["text"] for t in detail["turns"]] == ["Xin chào", "Cho hỏi"]
    assert detail["tool_runs"][0]["started_ms"] == 3000


def test_handoff_creates_at_most_one_task(client, session_factory):
    cid = _call(client)["id"]
    body = {"reason": "Khách hỏi trả góp", "summary": "Muốn biết lãi suất"}
    r1 = client.post(f"/api/v1/internal/calls/{cid}/handoff", json=body, headers=SVC).json()
    r2 = client.post(f"/api/v1/internal/calls/{cid}/handoff", json=body, headers=SVC).json()
    assert r1["created"] and not r2["created"] and r1["task_id"] == r2["task_id"]
    assert r1["status"] == "queued"  # a request, never "connected"
    tasks = client.get("/api/v1/tasks?type=human_request", headers=ADMIN_A).json()["items"]
    assert len(tasks) == 1
    t = tasks[0]
    assert t["priority"] == "high" and t["call_id"] == cid and t["description"] == "Muốn biết lãi suất"
    with session_factory() as s:
        assert s.query(Task).filter_by(source_key=f"handoff:{cid}").count() == 1


def test_end_call_is_monotonic_and_booking_creates_confirm_task(client):
    cid = _call(client)["id"]
    end = {"ended_at": (utcnow() + timedelta(minutes=2)).isoformat(), "business_outcome": "booked"}
    assert client.post(f"/api/v1/internal/calls/{cid}/end", json=end, headers=SVC).json()["updated"] is True
    late = {"ended_at": (utcnow() + timedelta(minutes=9)).isoformat(), "technical_status": "failed"}
    assert client.post(f"/api/v1/internal/calls/{cid}/end", json=late, headers=SVC).json()["updated"] is False
    data = client.get(f"/api/v1/calls/{cid}", headers=ADMIN_A).json()["data"]
    assert data["technical_status"] == "ended" and data["business_outcome"] == "booked"
    assert data["duration_s"] >= 110
    confirm = client.get("/api/v1/tasks?type=appointment_confirm", headers=ADMIN_A).json()["items"]
    assert len(confirm) == 1 and confirm[0]["call_id"] == cid


def test_service_cannot_touch_other_tenant_call(client):
    cid = _call(client)["id"]
    turns = {"turns": [{"seq": 1, "speaker": "agent", "text": "x", "started_ms": 0}]}
    assert client.post(f"/api/v1/internal/calls/{cid}/turns", json=turns, headers=SVC_B).status_code == 404
    assert (
        client.post(f"/api/v1/internal/calls/{cid}/handoff", json={"reason": "x"}, headers=SVC_B).status_code
        == 404
    )


def test_api_datetimes_always_carry_an_offset(client):
    # SQLite returns naive values; without an offset browsers render them in local time (7 h shift)
    cid = _call(client)["id"]
    data = client.get(f"/api/v1/calls/{cid}", headers=ADMIN_A).json()["data"]
    assert data["started_at"].endswith(("Z", "+00:00"))
    contact = client.get("/api/v1/contacts", headers=ADMIN_A).json()["items"][0]
    assert contact["created_at"].endswith(("Z", "+00:00"))
