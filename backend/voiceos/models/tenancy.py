import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from voiceos.db import Base
from voiceos.models.base import IdMixin, TenantScoped, TimestampMixin, UTCDateTime, Versioned

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
    __table_args__ = (UniqueConstraint("oidc_issuer", "oidc_subject", name="uq_user_oidc_identity"),)

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # bound on first OIDC sign-in of an invited email; never matched again by email afterwards
    oidc_issuer: Mapped[str | None] = mapped_column(String(300), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class Membership(TenantScoped, Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),)

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    branch_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
