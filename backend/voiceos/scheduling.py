"""Tenant working calendar and inbound route: defaults, loading, routing decision (AC23, AC24)."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select

from voiceos.domain.calendar import Calendar, DayException, due_in_next_window, status_at
from voiceos.models import BusinessCalendar, CalendarException, InboundRoute, Membership, Tenant

DEFAULT_WEEKLY = {
    "1": [["08:00", "17:30"]],
    "2": [["08:00", "17:30"]],
    "3": [["08:00", "17:30"]],
    "4": [["08:00", "17:30"]],
    "5": [["08:00", "17:30"]],
    "6": [["08:00", "12:00"]],
    "7": [],
}
DEFAULT_ANNOUNCEMENT = (
    "Dạ, cảm ơn anh/chị đã gọi. Hiện đang ngoài giờ làm việc. Nhân viên sẽ gọi lại cho anh/chị "
    "trong giờ làm việc tiếp theo."
)
SAMPLE_LABEL = " (mẫu, đối chiếu thông báo chính thức)"
# Sample holidays so a new workspace is not open on Tết. Lunar dates and bridging days change every year
# and must be checked by the admin against the official announcement (plan/docs/08).
SAMPLE_HOLIDAYS = [
    (date(2026, 1, 1), date(2026, 1, 1), "Tết Dương lịch"),
    (date(2026, 2, 14), date(2026, 2, 22), "Tết Nguyên đán"),
    (date(2026, 4, 26), date(2026, 4, 26), "Giỗ Tổ Hùng Vương"),
    (date(2026, 4, 30), date(2026, 5, 1), "Giải phóng miền Nam, Quốc tế Lao động"),
    (date(2026, 9, 1), date(2026, 9, 2), "Quốc khánh"),
    (date(2027, 1, 1), date(2027, 1, 1), "Tết Dương lịch"),
    (date(2027, 2, 5), date(2027, 2, 10), "Tết Nguyên đán"),
    (date(2027, 4, 16), date(2027, 4, 16), "Giỗ Tổ Hùng Vương"),
    (date(2027, 4, 30), date(2027, 5, 1), "Giải phóng miền Nam, Quốc tế Lao động"),
    (date(2027, 9, 2), date(2027, 9, 3), "Quốc khánh"),
]
CALLBACK_GRACE = timedelta(minutes=30)


def ensure_defaults(db, tenant_id: uuid.UUID) -> tuple[BusinessCalendar, InboundRoute]:
    """Every tenant has one working calendar and a default route ("*"). Created on first use."""
    cal = db.scalar(
        select(BusinessCalendar)
        .where(BusinessCalendar.tenant_id == tenant_id)
        .order_by(BusinessCalendar.created_at)
    )
    if cal is None:
        tenant = db.get(Tenant, tenant_id)
        cal = BusinessCalendar(
            tenant_id=tenant_id,
            name="Giờ làm việc",
            timezone=tenant.timezone if tenant else "Asia/Ho_Chi_Minh",
            weekly_hours=DEFAULT_WEEKLY,
        )
        db.add(cal)
        db.flush()
        for start, end, label in SAMPLE_HOLIDAYS:
            db.add(
                CalendarException(
                    tenant_id=tenant_id,
                    calendar_id=cal.id,
                    date_from=start,
                    date_to=end,
                    kind="holiday",
                    label=label + SAMPLE_LABEL,
                )
            )
    route = db.scalar(
        select(InboundRoute).where(InboundRoute.tenant_id == tenant_id, InboundRoute.number == "*")
    )
    if route is None:
        route = InboundRoute(
            tenant_id=tenant_id, number="*", calendar_id=cal.id, announcement=DEFAULT_ANNOUNCEMENT
        )
        db.add(route)
    db.flush()
    return cal, route


def exceptions_of(db, cal: BusinessCalendar) -> list[CalendarException]:
    return list(
        db.scalars(
            select(CalendarException)
            .where(CalendarException.calendar_id == cal.id)
            .order_by(CalendarException.date_from, CalendarException.created_at)
        )
    )


def to_domain(cal: BusinessCalendar, exceptions: list[CalendarException]) -> Calendar:
    return Calendar(
        timezone=cal.timezone,
        weekly_hours={k: [tuple(w) for w in v] for k, v in (cal.weekly_hours or {}).items()},
        exceptions=tuple(
            DayException(e.date_from, e.date_to, e.kind, [tuple(w) for w in (e.hours or [])], e.label)
            for e in exceptions
        ),
    )


def load(
    db, tenant_id: uuid.UUID, number: str | None = None
) -> tuple[InboundRoute, BusinessCalendar, Calendar]:
    _, default_route = ensure_defaults(db, tenant_id)
    route = default_route
    if number and number != "*":
        route = (
            db.scalar(
                select(InboundRoute).where(InboundRoute.tenant_id == tenant_id, InboundRoute.number == number)
            )
            or default_route
        )
    cal = db.get(BusinessCalendar, route.calendar_id)
    return route, cal, to_domain(cal, exceptions_of(db, cal))


@dataclass(frozen=True)
class RoutingDecision:
    route_id: uuid.UUID
    after_hours: bool
    target: str
    announcement: str
    opens_at: datetime | None
    closes_at: datetime | None
    reason: str
    timezone: str


def decide(db, tenant_id: uuid.UUID, at: datetime, number: str | None = None) -> RoutingDecision:
    route, cal, domain = load(db, tenant_id, number)
    st = status_at(domain, at)
    return RoutingDecision(
        route_id=route.id,
        after_hours=not st.open,
        target=route.in_hours_target if st.open else route.after_hours_target,
        announcement=route.announcement,
        opens_at=st.opens_at,
        closes_at=st.closes_at,
        reason=st.reason,
        timezone=cal.timezone,
    )


def after_hours_assignment(
    db, tenant_id: uuid.UUID, at: datetime
) -> tuple[uuid.UUID | None, datetime | None]:
    """Owner and due time for a request left over from an after-hours call (AC24)."""
    route, _, domain = load(db, tenant_id)
    owner = route.after_hours_owner_id
    if owner is not None:
        still_member = db.scalar(
            select(Membership.id).where(Membership.tenant_id == tenant_id, Membership.user_id == owner)
        )
        owner = owner if still_member else None
    return owner, due_in_next_window(domain, at, CALLBACK_GRACE)
