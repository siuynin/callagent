"""Synthetic calls and inbox tasks for UI work in dev (tenant A only). Idempotent.

Not used by tests. Every call is from the "mock-seed" provider so it can never be mistaken for a real one.
"""

from datetime import timedelta

from sqlalchemy import select

from voiceos.db import utcnow
from voiceos.domain.phone import normalize_vn_phone
from voiceos.models import Call, CallTurn, Contact, Task, ToolRun
from voiceos.seed import TENANT_A, USER_STAFF_A

PROVIDER = "mock-seed"


def _contact(session, name: str, phone: str, need: str) -> Contact:
    found = session.scalar(select(Contact).where(Contact.tenant_id == TENANT_A, Contact.name == name))
    if found:
        return found
    n = normalize_vn_phone(phone)
    c = Contact(
        tenant_id=TENANT_A,
        name=name,
        phone_raw=phone,
        normalized_phone=n.e164,
        phone_status=n.status,
        need=need,
    )
    session.add(c)
    session.flush()
    return c


def _call(
    session,
    key: str,
    contact: Contact,
    *,
    ago_min: int,
    seconds: int,
    outcome: str | None,
    status: str = "ended",
    after_hours: bool = False,
    turns=(),
    tools=(),
) -> Call:
    start = utcnow() - timedelta(minutes=ago_min)
    answered = start + timedelta(seconds=4) if seconds else None
    call = Call(
        tenant_id=TENANT_A,
        direction="inbound",
        contact_id=contact.id,
        provider=PROVIDER,
        provider_call_id=key,
        started_at=start,
        answered_at=answered,
        ended_at=(answered + timedelta(seconds=seconds)) if answered else start + timedelta(seconds=25),
        technical_status=status,
        business_outcome=outcome,
        after_hours=after_hours,
    )
    session.add(call)
    session.flush()
    for seq, (speaker, ms, text) in enumerate(turns, 1):
        session.add(
            CallTurn(tenant_id=TENANT_A, call_id=call.id, seq=seq, speaker=speaker, text=text, started_ms=ms)
        )
    for seq, (name, args, result_status, result) in enumerate(tools, 1):
        session.add(
            ToolRun(
                tenant_id=TENANT_A,
                call_id=call.id,
                seq=seq,
                tool_name=name,
                args_redacted=args,
                status=result_status,
                result=result,
                idempotency_key=f"{key}-{seq}",
                started_at=start + timedelta(seconds=20 * seq),
                finished_at=start + timedelta(seconds=20 * seq, milliseconds=300),
            )
        )
    return call


def seed_demo(session) -> bool:
    if session.scalar(select(Call.id).where(Call.tenant_id == TENANT_A, Call.provider == PROVIDER)):
        return False
    a = _contact(session, "Khách mẫu A", "0900000001", "Tư vấn")
    d = _contact(session, "Khách mẫu D", "0900000004", "Hỏi trả góp SUV")
    e = _contact(session, "Khách mẫu E", "0900000005", "Gọi nhỡ")
    f = _contact(session, "Khách mẫu F", "0900000006", "Gọi lại ngoài giờ")
    now = utcnow()

    booked = _call(
        session,
        "seed-1",
        a,
        ago_min=95,
        seconds=204,
        outcome="booked",
        turns=[
            (
                "agent",
                3000,
                "Dạ, Showroom mẫu xin nghe. Em là trợ lý AI, cuộc gọi được ghi âm để phục vụ anh/chị tốt hơn.",
            ),
            ("customer", 12000, "Mình muốn lái thử một mẫu SUV vào chiều mai."),
            ("agent", 18000, "Dạ, anh/chị muốn đến vào khoảng mấy giờ để em kiểm tra lịch ạ?"),
            ("customer", 27000, "Khoảng 3 giờ chiều."),
            (
                "agent",
                35000,
                "Dạ 15 giờ chiều mai còn trống ạ. Anh/chị cho em xin họ tên và số điện thoại nhé?",
            ),
            (
                "customer",
                44000,
                "Khách mẫu A, số không chín không không, không không không, không không một.",
            ),
            (
                "agent",
                52000,
                "Em đọc lại: 15 giờ chiều mai, Khách mẫu A, số 0900 000 001. Anh/chị xác nhận giúp em ạ?",
            ),
            ("customer", 58000, "Đúng rồi, đặt giúp mình."),
            (
                "agent",
                63000,
                "Dạ, em đã đặt xong lịch lái thử 15 giờ chiều mai. Nhân viên sẽ gọi xác nhận trước giờ hẹn ạ.",
            ),
        ],
        tools=[
            (
                "check_available_slots",
                {"date": "(ngày mai)", "preferred_time": "15:00"},
                "ok",
                {"preferred_available": True},
            ),
            (
                "create_appointment",
                {"start": "(ngày mai) 15:00", "purpose": "test_drive", "phone": "***0001"},
                "ok",
                {"appointment_id": "APT-0001"},
            ),
        ],
    )
    handoff = _call(
        session,
        "seed-2",
        d,
        ago_min=40,
        seconds=250,
        outcome="handoff",
        turns=[
            (
                "agent",
                3000,
                "Dạ, Showroom mẫu xin nghe. Em là trợ lý AI, cuộc gọi được ghi âm để phục vụ anh/chị tốt hơn.",
            ),
            ("customer", 10000, "Cho chị hỏi mua SUV trả góp thì lãi suất bao nhiêu em?"),
            (
                "agent",
                16000,
                "Dạ, phần trả góp nhân viên tư vấn sẽ báo chính xác cho chị. Em chuyển yêu cầu ngay ạ.",
            ),
            ("agent", 19000, "Em đã chuyển yêu cầu, nhân viên sẽ liên hệ chị trong ít phút ạ."),
        ],
        tools=[
            (
                "request_handoff",
                {"reason": "Hỏi lãi suất trả góp", "summary": "Khách nữ hỏi trả góp SUV"},
                "ok",
                {"handoff_status": "queued"},
            ),
        ],
    )
    missed = _call(session, "seed-3", e, ago_min=25, seconds=0, outcome=None, status="missed")
    after_hours = _call(
        session,
        "seed-4",
        f,
        ago_min=600,
        seconds=96,
        outcome="callback",
        after_hours=True,
        turns=[
            (
                "agent",
                3000,
                "Dạ, showroom hiện ngoài giờ làm việc. Em là trợ lý AI, em ghi nhận yêu cầu để nhân viên gọi lại ạ.",
            ),
            ("customer", 9000, "Sáng mai gọi lại cho anh khoảng 9 giờ nhé."),
            ("agent", 15000, "Dạ, em đã ghi nhận yêu cầu gọi lại khoảng 9 giờ sáng mai ạ."),
        ],
    )

    session.add_all(
        [
            Task(
                tenant_id=TENANT_A,
                type="human_request",
                title="Khách hỏi trả góp, cần tư vấn tài chính",
                contact_id=d.id,
                call_id=handoff.id,
                priority="high",
                due_at=now - timedelta(minutes=15),
            ),
            Task(
                tenant_id=TENANT_A,
                type="missed_call",
                title="Cuộc gọi nhỡ, gọi lại khách",
                contact_id=e.id,
                call_id=missed.id,
                due_at=now + timedelta(hours=2),
            ),
            Task(
                tenant_id=TENANT_A,
                type="callback",
                title="Gọi lại theo yêu cầu ngoài giờ",
                contact_id=f.id,
                call_id=after_hours.id,
                owner_id=USER_STAFF_A,
                status="in_progress",
                due_at=now + timedelta(hours=5),
            ),
            Task(
                tenant_id=TENANT_A,
                type="appointment_confirm",
                title="Xác nhận lịch lái thử",
                contact_id=a.id,
                call_id=booked.id,
                due_at=now + timedelta(days=1),
            ),
        ]
    )
    session.commit()
    return True


if __name__ == "__main__":
    from voiceos import db

    factory = db.configure()
    with factory() as s:
        print("Đã tạo dữ liệu mẫu" if seed_demo(s) else "Dữ liệu mẫu đã có, bỏ qua")
