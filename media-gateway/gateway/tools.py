"""Mock receptionist tools for the spike. Results use the adapter envelope from plan/docs/04.

Business guards live here, not in the prompt: create_appointment refuses without explicit customer
confirmation and a valid phone, and is idempotent per call so a model retry cannot double-book.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from gateway.providers.base import ToolSpec

OPEN_DAYS = {0, 1, 2, 3, 4, 5}  # Mon-Sat
SLOTS = [time(h) for h in range(9, 17)]  # 09:00 .. 16:00 start times
_PHONE = re.compile(r"^(?:\+?84|0)([35789]\d{8}|2\d{9})$")

TOOL_SPECS = [
    ToolSpec(
        name="check_available_slots",
        description=(
            "Tra các khung giờ còn trống để lái thử/tư vấn tại showroom trong một ngày. "
            "Gọi trước khi đề xuất giờ hẹn. Ngày theo định dạng YYYY-MM-DD theo giờ Việt Nam."
        ),
        parameters={
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "preferred_time": {"type": "string", "description": "HH:MM nếu khách có giờ mong muốn"},
            },
            "required": ["date"],
        },
    ),
    ToolSpec(
        name="create_appointment",
        description=(
            "Tạo lịch hẹn SAU KHI đã đọc lại ngày giờ, họ tên, số điện thoại và khách đồng ý rõ ràng. "
            "Chỉ báo khách đã đặt xong khi kết quả trả về status=ok."
        ),
        parameters={
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "phone": {"type": "string", "description": "Chỉ chữ số, ví dụ 0901234567"},
                "start": {"type": "string", "description": "YYYY-MM-DDTHH:MM giờ Việt Nam"},
                "purpose": {"type": "string", "enum": ["test_drive", "consultation", "service"]},
                "confirmed_by_customer": {"type": "boolean"},
            },
            "required": ["customer_name", "phone", "start", "purpose", "confirmed_by_customer"],
        },
    ),
    ToolSpec(
        name="request_handoff",
        description=(
            "Chuyển cho nhân viên khi khách yêu cầu người thật, hỏi trả góp, giá lăn bánh, khiếu nại, "
            "hoặc khi không chắc chắn. Kết quả 'queued' nghĩa là CHƯA có nhân viên nhận."
        ),
        parameters={
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "summary": {"type": "string", "description": "Tóm tắt nhu cầu để nhân viên đọc"},
            },
            "required": ["reason", "summary"],
        },
    ),
]


def _envelope(status: str, data=None, message: str | None = None) -> dict:
    out = {"status": status, "source_provider": "mock-calendar", "data": data or {}}
    if message:
        out["message"] = message
    return out


@dataclass
class Toolbox:
    tz: ZoneInfo
    now: datetime | None = None  # injectable clock for tests
    booked: set[datetime] = field(default_factory=set)
    _by_key: dict[str, dict] = field(default_factory=dict)

    def _now(self) -> datetime:
        return self.now or datetime.now(self.tz)

    def _free(self, day: date) -> list[str]:
        if day.weekday() not in OPEN_DAYS:
            return []
        now = self._now()
        out = []
        for t in SLOTS:
            start = datetime.combine(day, t, self.tz)
            if start > now + timedelta(hours=1) and start not in self.booked and t.hour != 12:
                out.append(t.strftime("%H:%M"))
        return out

    def execute(self, name: str, args: dict) -> dict:
        try:
            if name == "check_available_slots":
                return self._check(args)
            if name == "create_appointment":
                return self._create(args)
            if name == "request_handoff":
                return _envelope("ok", {"handoff_status": "queued", "estimated_wait_minutes": 5})
        except (KeyError, ValueError) as exc:
            return _envelope("invalid_arguments", message=str(exc))
        return _envelope("unavailable", message=f"Công cụ {name} không được cấp cho agent này")

    def _check(self, args: dict) -> dict:
        day = date.fromisoformat(args["date"])
        if day < self._now().date():
            return _envelope("invalid_arguments", message="Ngày đã qua")
        free = self._free(day)
        if not free:
            return _envelope(
                "ok", {"date": day.isoformat(), "slots": [], "note": "Showroom nghỉ hoặc đã kín"}
            )
        pref = args.get("preferred_time")
        return _envelope(
            "ok",
            {"date": day.isoformat(), "slots": free, "preferred_available": pref in free if pref else None},
        )

    def _create(self, args: dict) -> dict:
        if args.get("confirmed_by_customer") is not True:
            return _envelope("needs_confirmation", message="Đọc lại thông tin và hỏi khách xác nhận trước")
        phone = re.sub(r"[\s.\-()]", "", str(args["phone"]))
        if not _PHONE.match(phone):
            return _envelope("invalid_arguments", message="Số điện thoại chưa hợp lệ, hỏi lại khách")
        start = datetime.fromisoformat(args["start"]).replace(tzinfo=self.tz)
        key = f"{phone}|{start.isoformat()}|{args['purpose']}"
        if key in self._by_key:  # same booking requested again: return the original result
            return self._by_key[key]
        if start.strftime("%H:%M") not in self._free(start.date()):
            return _envelope("slot_unavailable", message="Khung giờ không còn trống, tra lịch lại")
        self.booked.add(start)
        result = _envelope(
            "ok",
            {
                "appointment_id": f"APT-{len(self.booked):04d}",
                "start": start.isoformat(),
                "customer_name": args["customer_name"],
                "phone_last4": phone[-4:],
            },
        )
        self._by_key[key] = result
        return result
