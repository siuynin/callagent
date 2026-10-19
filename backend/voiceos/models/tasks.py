import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, Versioned

TASK_TYPES = ("missed_call", "human_request", "callback", "appointment_confirm", "follow_up")
TASK_STATUSES = ("new", "in_progress", "resolved", "cancelled")
TERMINAL = ("resolved", "cancelled")
PRIORITIES = ("high", "normal")


class Task(TenantScoped, Versioned, Base):
    """Inbox item (plan/docs/03 tasks). State machine: new -> in_progress -> resolved/cancelled.

    Owner is required for in_progress, a resolution note for resolved (AC08); enforced in the API.
    """

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_tenant_status_due", "tenant_id", "status", "due_at"),)

    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("contacts.id"), nullable=True)
    call_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("calls.id"), nullable=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(8), default="normal", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new", nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
