from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from gateway.tools import Toolbox

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NOW = datetime(2026, 10, 19, 8, 0, tzinfo=TZ)  # Monday


@pytest.fixture()
def box():
    return Toolbox(tz=TZ, now=NOW)


def booking(**over):
    args = {
        "customer_name": "Nguyễn Văn A",
        "phone": "0901 234 567",
        "start": "2026-10-20T15:00",
        "purpose": "test_drive",
        "confirmed_by_customer": True,
    }
    return {**args, **over}


def test_slots_skip_lunch_and_sunday(box):
    tue = box.execute("check_available_slots", {"date": "2026-10-20", "preferred_time": "15:00"})
    assert tue["status"] == "ok" and "12:00" not in tue["data"]["slots"]
    assert tue["data"]["preferred_available"] is True
    sun = box.execute("check_available_slots", {"date": "2026-10-25"})
    assert sun["data"]["slots"] == []


def test_past_date_rejected(box):
    assert box.execute("check_available_slots", {"date": "2026-10-18"})["status"] == "invalid_arguments"


def test_create_requires_explicit_confirmation(box):
    r = box.execute("create_appointment", booking(confirmed_by_customer=False))
    assert r["status"] == "needs_confirmation"
    assert box.booked == set()


def test_create_rejects_bad_phone(box):
    assert box.execute("create_appointment", booking(phone="12345"))["status"] == "invalid_arguments"


def test_create_is_idempotent_and_blocks_double_booking(box):
    first = box.execute("create_appointment", booking())
    again = box.execute("create_appointment", booking())
    assert first["status"] == "ok" and again == first  # model retry does not double-book
    other = box.execute("create_appointment", booking(phone="0912345678", customer_name="B"))
    assert other["status"] == "slot_unavailable"
    assert "15:00" not in box.execute("check_available_slots", {"date": "2026-10-20"})["data"]["slots"]


def test_handoff_is_queued_not_accepted(box):
    r = box.execute("request_handoff", {"reason": "trả góp", "summary": "hỏi lãi suất"})
    assert r["data"]["handoff_status"] == "queued"


def test_unknown_tool(box):
    assert box.execute("refund_order", {})["status"] == "unavailable"


def test_missing_argument_is_reported(box):
    assert box.execute("create_appointment", {"confirmed_by_customer": True})["status"] == "invalid_arguments"
