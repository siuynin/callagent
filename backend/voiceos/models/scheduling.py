import uuid
from datetime import date

from sqlalchemy import JSON, Date, ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, Versioned

ROUTE_TARGETS = ("agent", "announcement")


class BusinessCalendar(TenantScoped, Versioned, Base):
    """Working hours (plan/docs/03). weekly_hours: {"1": [["08:00", "17:30"]], …, "7": []}."""

    __tablename__ = "business_calendars"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", nullable=False)
    weekly_hours: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class CalendarException(TenantScoped, Base):
    """Dated override: holiday/closed (whole day shut) or special_hours (replaces the weekly hours)."""

    __tablename__ = "calendar_exceptions"
    __table_args__ = (Index("ix_calendar_exceptions_calendar_dates", "calendar_id", "date_from", "date_to"),)

    calendar_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("business_calendars.id", ondelete="CASCADE"), nullable=False
    )
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    hours: Mapped[list | None] = mapped_column(JSON, nullable=True)
    label: Mapped[str] = mapped_column(String(200), default="", nullable=False)


class InboundRoute(TenantScoped, Versioned, Base):
    """What answers an inbound number in and out of hours (plan/docs/03 inbound_routes, AC24).

    number "*" is the tenant default until phone numbers/SIP exist (ADR 0004). Unfinished after-hours
    requests become tasks for after_hours_owner_id, due in the next working window.
    """

    __tablename__ = "inbound_routes"
    __table_args__ = (UniqueConstraint("tenant_id", "number", name="uq_inbound_route_number"),)

    number: Mapped[str] = mapped_column(String(32), default="*", nullable=False)
    calendar_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("business_calendars.id"), nullable=False)
    in_hours_target: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)
    after_hours_target: Mapped[str] = mapped_column(String(16), default="agent", nullable=False)
    ai_failure_target: Mapped[str] = mapped_column(String(16), default="announcement", nullable=False)
    after_hours_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    announcement: Mapped[str] = mapped_column(Text, default="", nullable=False)
