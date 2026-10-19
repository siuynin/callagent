import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from voiceos.db import utcnow


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class TenantScoped(IdMixin, TimestampMixin):
    """Every domain row belongs to exactly one tenant (ADR 0002)."""

    @declared_attr
    def tenant_id(cls) -> Mapped[uuid.UUID]:  # noqa: N805
        return mapped_column(Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), index=True, nullable=False)


class Versioned:
    """Optimistic locking; PATCH must send If-Match with this value."""

    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
