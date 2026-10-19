import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import TenantScoped, UTCDateTime, Versioned


class Agent(TenantScoped, Versioned, Base):
    __tablename__ = "agents"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # version live calls use; no FK to avoid an agents <-> agent_versions cycle (checked in code)
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class AgentVersion(TenantScoped, Base):
    """Immutable once published; calls pin the version they used."""

    __tablename__ = "agent_versions"
    __table_args__ = (UniqueConstraint("agent_id", "number", name="uq_agent_version_number"),)

    agent_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("agents.id"), index=True, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default="draft", nullable=False
    )  # draft|published|retired
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    test_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
