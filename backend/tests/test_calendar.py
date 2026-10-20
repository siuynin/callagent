"""Business calendar (AC23) and after-hours inbound routing (AC24)."""

import uuid
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from conftest import ADMIN_A, ADMIN_B, STAFF_A, TENANT_A, USER_STAFF_A

from voiceos.domain.calendar import (
    Calendar,
    DayException,
    due_in_next_window,
    next_open,
    status_at,
    weekly_problems,
)
from voiceos.models import Task
from voiceos.scheduling import DEFAULT_WEEKLY

ICT = timezone(timedelta(hours=7))
SVC = {"X-Service-Token": "test-service-token", "X-Tenant-Id": str(TENANT_A)}
CAL = Calendar("Asia/Ho_Chi_Minh", {k: [tuple(w) for w in v] for k, v in DEFAULT_WEEKLY.items()})


def at(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=ICT)


# --- domain (2026-10-19 is a Monday) ---


def test_open_and_closes_at():
    st = status_at(CAL, at(2026, 10, 19, 10))
    assert st.open and st.closes_at == at(2026, 10, 19, 17, 30)


def test_after_close_moves_to_next_morning():
    assert next_open(CAL, at(2026, 10, 19, 18)) == at(2026, 10, 20, 8)
    assert next_open(CAL, at(2026, 10, 19, 6)) == at(2026, 10, 19, 8)


def test_saturday_afternoon_and_sunday_move_to_monday():
    assert next_open(CAL, at(2026, 10, 24, 13)) == at(2026, 10, 26, 8)
    assert next_open(CAL, at(2026, 10, 25, 9)) == at(2026, 10, 26, 8)


def test_open_time_is_returned_as_is_and_utc_input_works():
    t = at(2026, 10, 19, 9, 15)
    assert next_open(CAL, t) == t
    assert status_at(CAL, datetime(2026, 10, 19, 3, 0, tzinfo=UTC)).open  # 10:00 ICT


def test_tet_holiday_moves_to_first_working_day_after():
    tet = Calendar(
        CAL.timezone,
        CAL.weekly_hours,
        (DayException(date(2027, 2, 5), date(2027, 2, 10), "holiday", label="Tết"),),
    )
    st = status_at(tet, at(2027, 2, 8, 10))  # Monday, inside Tết
    assert not st.open and st.reason == "Tết"
    assert st.opens_at == at(2027, 2, 11, 8)


def test_special_hours_replace_weekly_and_closed_wins():
    cal = Calendar(
        CAL.timezone,
        CAL.weekly_hours,
        (
            DayException(
                date(2026, 10, 25), date(2026, 10, 25), "special_hours", [("09:00", "11:00")], "Mở CN"
            ),
            DayException(
                date(2026, 10, 20), date(2026, 10, 20), "special_hours", [("13:00", "15:00")], "Chiều"
            ),
            DayException(date(2026, 10, 20), date(2026, 10, 20), "closed", label="Kiểm kê"),
        ),
    )
    assert status_at(cal, at(2026, 10, 25, 10)).open  # Sunday opened specially
    assert next_open(cal, at(2026, 10, 24, 13)) == at(2026, 10, 25, 9)
    assert next_open(cal, at(2026, 10, 20, 7)) == at(2026, 10, 21, 8)  # closed beats special hours


def test_24_hours_and_no_window_within_horizon():
    always = Calendar(CAL.timezone, {str(d): [("00:00", "24:00")] for d in range(1, 8)})
    assert status_at(always, at(2026, 10, 19, 23, 59)).open
    never = Calendar(CAL.timezone, {})
    assert next_open(never, at(2026, 10, 19, 10)) is None


def test_due_in_next_window_is_clamped_to_window_end():
    assert due_in_next_window(CAL, at(2026, 10, 19, 20), timedelta(minutes=30)) == at(2026, 10, 20, 8, 30)
    assert due_in_next_window(CAL, at(2026, 10, 24, 11, 50), timedelta(minutes=30)) == at(2026, 10, 24, 12)


@pytest.mark.parametrize(
    "weekly",
    [
        {"1": [["17:30", "08:00"]]},
        {"1": [["8:00", "17:00"]]},
        {"1": [["08:00", "12:00"], ["11:00", "17:00"]]},
        {"8": [["08:00", "12:00"]]},
        {"1": [["24:00", "24:00"]]},
        {str(d): [] for d in range(1, 8)},
    ],
)
def test_weekly_validation(weekly):
    assert weekly_problems(weekly)


# --- API ---


def _calendar(client, headers=ADMIN_A):
    r = client.get("/api/v1/business-calendars", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


def test_tenant_has_default_calendar_and_route(client):
    cal = _calendar(client)
    assert set(cal["weekly_hours"]) == {str(d) for d in range(1, 8)}
    routes = client.get("/api/v1/inbound-routes", headers=ADMIN_A).json()["items"]
    assert [r["number"] for r in routes] == ["*"]
    assert routes[0]["after_hours_owner"]["name"] == "Quản trị A"


def test_staff_cannot_read_and_tenants_are_isolated(client):
    assert client.get("/api/v1/business-calendars", headers=STAFF_A).status_code == 403
    cal_a = _calendar(client)
    r = client.post(
        f"/api/v1/business-calendars/{cal_a['id']}/exceptions",
        json={"date_from": "2027-02-05", "date_to": "2027-02-06", "kind": "holiday", "label": "Tết"},
        headers=ADMIN_B,
    )
    assert r.status_code == 404


def test_update_hours_requires_if_match_and_validates(client):
    cal = _calendar(client)
    body = {"name": "Giờ showroom", "timezone": "Asia/Ho_Chi_Minh", "weekly_hours": DEFAULT_WEEKLY}
    url = f"/api/v1/business-calendars/{cal['id']}"
    assert client.put(url, json=body, headers=ADMIN_A).status_code == 428
    bad = {**body, "weekly_hours": {"1": [["18:00", "08:00"]]}}
    r = client.put(url, json=bad, headers={**ADMIN_A, "If-Match": str(cal["version"])})
    assert r.status_code == 422 and r.json()["error"]["field_errors"]["weekly_hours"]
    r = client.put(
        url, json={**body, "timezone": "Mars/Base"}, headers={**ADMIN_A, "If-Match": str(cal["version"])}
    )
    assert r.status_code == 422
    r = client.put(url, json=body, headers={**ADMIN_A, "If-Match": str(cal["version"])})
    assert r.status_code == 200 and r.json()["data"]["weekly_hours"]["7"] == []
    stale = client.put(url, json=body, headers={**ADMIN_A, "If-Match": str(cal["version"])})
    assert stale.status_code == 409


def test_exceptions_add_validate_delete(client):
    cal = _calendar(client)
    url = f"/api/v1/business-calendars/{cal['id']}/exceptions"
    r = client.post(
        url,
        json={"date_from": "2027-02-10", "date_to": "2027-02-05", "kind": "holiday", "label": "x"},
        headers=ADMIN_A,
    )
    assert r.status_code == 422
    r = client.post(
        url,
        json={"date_from": "2027-02-06", "date_to": "2027-02-06", "kind": "special_hours", "label": "x"},
        headers=ADMIN_A,
    )
    assert r.status_code == 422  # special hours need hours
    r = client.post(
        url,
        json={"date_from": "2027-02-05", "date_to": "2027-02-10", "kind": "holiday", "label": "Tết"},
        headers=ADMIN_A,
    )
    assert r.status_code == 201
    exc_id = r.json()["data"]["id"]
    assert [e["label"] for e in _calendar(client)["exceptions"]] == ["Tết"]
    assert client.delete(f"{url}/{exc_id}", headers=ADMIN_A).json()["deleted"] is True
    assert _calendar(client)["exceptions"] == []


def test_route_update_rules(client):
    route = client.get("/api/v1/inbound-routes", headers=ADMIN_A).json()["items"][0]
    url = f"/api/v1/inbound-routes/{route['id']}"
    h = {**ADMIN_A, "If-Match": str(route["version"])}
    body = {"in_hours_target": "agent", "after_hours_target": "announcement", "announcement": ""}
    assert client.put(url, json=body, headers=h).status_code == 422  # announcement text required
    r = client.put(
        url,
        json={
            **body,
            "announcement": "Ngoài giờ",
            "after_hours_owner_id": "00000000-0000-4000-8000-0000000000b1",
        },
        headers=h,
    )
    assert r.status_code == 422  # owner from another tenant
    r = client.put(
        url, json={**body, "announcement": "Ngoài giờ", "after_hours_owner_id": str(USER_STAFF_A)}, headers=h
    )
    assert r.status_code == 200
    assert r.json()["data"]["after_hours_owner"]["name"] == "Nhân viên A"


# --- internal routing and after-hours tasks (AC24) ---


def _office_hours(client):
    cal = _calendar(client)
    body = {"name": cal["name"], "timezone": "Asia/Ho_Chi_Minh", "weekly_hours": DEFAULT_WEEKLY}
    r = client.put(
        f"/api/v1/business-calendars/{cal['id']}",
        json=body,
        headers={**ADMIN_A, "If-Match": str(cal["version"])},
    )
    assert r.status_code == 200


@pytest.fixture()
def clock(monkeypatch):
    def set_to(dt):
        import voiceos.api.routers.calendars as c
        import voiceos.api.routers.internal as i

        monkeypatch.setattr(i, "utcnow", lambda: dt.astimezone(UTC))
        monkeypatch.setattr(c, "utcnow", lambda: dt.astimezone(UTC))

    return set_to


def _start(client, when, key="gw-ah"):
    r = client.post(
        "/api/v1/internal/calls",
        json={"provider": "openai", "provider_call_id": key, "started_at": when.isoformat()},
        headers=SVC,
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_routing_in_hours(client, clock):
    _office_hours(client)
    clock(at(2026, 10, 19, 10))
    r = client.get("/api/v1/internal/routing", headers=SVC).json()
    assert r["after_hours"] is False and r["target"] == "agent"
    assert r["closes_at"].startswith("2026-10-19T17:30")


def test_after_hours_handoff_goes_to_default_owner_next_morning(client, clock, session_factory):
    _office_hours(client)
    night = at(2026, 10, 19, 21)
    clock(night)
    r = client.get("/api/v1/internal/routing", headers=SVC).json()
    assert r["after_hours"] is True and r["opens_at"] == at(2026, 10, 20, 8).isoformat()
    cid = _start(client, night)
    body = {"reason": "Khách muốn gặp tư vấn", "summary": "Hỏi giá xe"}
    h1 = client.post(f"/api/v1/internal/calls/{cid}/handoff", json=body, headers=SVC).json()
    h2 = client.post(f"/api/v1/internal/calls/{cid}/handoff", json=body, headers=SVC).json()
    assert h1["after_hours"] is True and h1["task_id"] == h2["task_id"] and h2["created"] is False
    with session_factory() as s:
        tasks = s.query(Task).filter(Task.call_id == uuid.UUID(cid)).all()
        assert len(tasks) == 1  # exactly one task (AC24)
        t = tasks[0]
        assert t.type == "callback" and str(t.owner_id).endswith("a1")
        assert t.due_at == at(2026, 10, 20, 8, 30)
    detail = client.get(f"/api/v1/calls/{cid}", headers=ADMIN_A).json()
    assert detail["data"]["after_hours"] is True


def test_after_hours_announcement_route(client, clock):
    _office_hours(client)
    route = client.get("/api/v1/inbound-routes", headers=ADMIN_A).json()["items"][0]
    client.put(
        f"/api/v1/inbound-routes/{route['id']}",
        json={"in_hours_target": "agent", "after_hours_target": "announcement", "announcement": "Đã hết giờ"},
        headers={**ADMIN_A, "If-Match": str(route["version"])},
    )
    clock(at(2026, 10, 25, 9))  # Sunday
    r = client.get("/api/v1/internal/routing", headers=SVC).json()
    assert r["target"] == "announcement" and r["announcement"] == "Đã hết giờ"


def test_removed_owner_is_not_assigned(client, clock, session_factory):
    _office_hours(client)
    route = client.get("/api/v1/inbound-routes", headers=ADMIN_A).json()["items"][0]
    client.put(
        f"/api/v1/inbound-routes/{route['id']}",
        json={
            "in_hours_target": "agent",
            "after_hours_target": "agent",
            "announcement": "Ngoài giờ",
            "after_hours_owner_id": str(USER_STAFF_A),
        },
        headers={**ADMIN_A, "If-Match": str(route["version"])},
    ).raise_for_status()
    assert client.delete(f"/api/v1/admin/members/{USER_STAFF_A}", headers=ADMIN_A).status_code == 200
    assert (
        client.get("/api/v1/inbound-routes", headers=ADMIN_A).json()["items"][0]["after_hours_owner"] is None
    )
    clock(at(2026, 10, 19, 22))
    cid = _start(client, at(2026, 10, 19, 22), key="gw-ah2")
    client.post(f"/api/v1/internal/calls/{cid}/handoff", json={"reason": "Gọi lại"}, headers=SVC)
    with session_factory() as s:
        assert s.query(Task).filter(Task.call_id == uuid.UUID(cid)).one().owner_id is None
