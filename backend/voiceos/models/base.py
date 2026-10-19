import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column
from sqlalchemy.types import TypeDecorator

from voiceos.db import utcnow


class UTCDateTime(TypeDecorator):
    """timestamptz that always comes back timezone-aware.

    SQLite (dev/tests) drops the offset and returns naive values; serialised without an offset they are
    read as local time by clients (a 7 hour shift in Vietnam). Values are stored as UTC everywhere.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(UTC)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantScoped(IdMixin, TimestampMixin):
    """Every domain row belongs to exactly one tenant (ADR 0002)."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), index=True, nullable=False)


class Versioned:
    """Optimistic locking; PATCH must send If-Match with this value."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
