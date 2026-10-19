import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, UTCDateTime, Versioned

TASK_TYPES = ("missed_call", "human_request", "callback", "appointment_confirm", "follow_up")
TASK_STATUSES = ("new", "in_progress", "resolved", "cancelled")
TERMINAL = ("resolved", "cancelled")
PRIORITIES = ("high", "normal")


class Task(TenantScoped, Versioned, Base):
    """Inbox item (plan/docs/03 tasks). State machine: new -> in_progress -> resolved/cancelled.

    Owner is required for in_progress, a resolution note for resolved (AC08); enforced in the API.
    """

    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_tenant_status_due", "tenant_id", "status", "due_at"),
        # system-created tasks carry a deterministic key (e.g. "handoff:<call_id>") so a retried
        # gateway request can never create a second one (AC07: at most one callback per handoff)
        UniqueConstraint("tenant_id", "source_key", name="uq_task_source_key"),
    )

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True)
    call_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("calls.id"), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
