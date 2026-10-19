import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import IdMixin, TenantScoped, TimestampMixin, Versioned

ROLES = ("owner", "admin", "manager", "staff", "auditor")
# higher number = more privilege; auditor is read-only and checked separately
ROLE_RANK = {"auditor": 0, "staff": 1, "manager": 2, "admin": 3, "owner": 4}


class Tenant(IdMixin, TimestampMixin, Versioned, Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Ho_Chi_Minh", nullable=False)
    outbound_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compliance_gates: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)


class Membership(TenantScoped, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    branch_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
