import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, Versioned


class Call(TenantScoped, Versioned, Base):
    __tablename__ = "calls"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "provider_call_id", name="uq_call_provider_id"),
    )

    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # inbound | outbound
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True)
    agent_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("agent_versions.id"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    technical_status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    business_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    after_hours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class CallTurn(TenantScoped, Base):
    __tablename__ = "call_turns"
    __table_args__ = (UniqueConstraint("call_id", "seq", name="uq_call_turn_seq"),)

    call_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("calls.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(8), nullable=False)  # customer | agent | staff
    text: Mapped[str] = mapped_column(Text, nullable=False)
    started_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    ended_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # barge-in: only audio the customer actually heard (plan/docs/02)
    played_until_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ToolRun(TenantScoped, Base):
    __tablename__ = "tool_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_tool_run_idem"),)

    call_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("calls.id"), index=True, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    args_redacted: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ok|not_found|unavailable|error|timeout
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
