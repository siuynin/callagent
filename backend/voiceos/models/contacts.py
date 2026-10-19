import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, Versioned

CONSENT_PURPOSES = ("service_call", "marketing_call", "recording", "sms", "zalo")


class Contact(TenantScoped, Versioned, Base):
    __tablename__ = "contacts"
    # not unique: a shared family phone may belong to several people (plan/docs/03)
    __table_args__ = (Index("ix_contacts_tenant_phone", "tenant_id", "normalized_phone"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone_raw: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_status: Mapped[str] = mapped_column(String(16), nullable=False)  # valid | invalid | uncertain
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    need: Mapped[str | None] = mapped_column(String(500), nullable=True)
    optout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConsentRecord(TenantScoped, Base):
    """Append-only. Current state per purpose = latest record (plan/docs/09)."""

    __tablename__ = "consent_records"

    contact_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("contacts.id"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
