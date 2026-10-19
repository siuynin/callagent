"""Authentication and tenant context.

Tenant is derived from an authenticated membership, never from the request body (plan/docs/06).
M0 only ships the dev authenticator ("Authorization: Bearer dev:<user_uuid>", APP_ENV=dev only);
OIDC replaces it in M1 behind the same `AuthContext`.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from voiceos.api.errors import ApiError
from voiceos.config import get_settings
from voiceos.db import get_session
from voiceos.models import Membership
from voiceos.models.tenancy import ROLE_RANK

DbSession = Annotated[Session, Depends(get_session)]


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


def _parse_uuid(value: str, code: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ApiError(401, code, "Thông tin xác thực không hợp lệ") from exc


def get_auth(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> AuthContext:
    settings = get_settings()
    if not authorization or not authorization.startswith("Bearer "):
        raise ApiError(401, "UNAUTHENTICATED", "Cần đăng nhập")
    token = authorization.removeprefix("Bearer ").strip()
    if not (settings.dev_auth and settings.app_env == "dev" and token.startswith("dev:")):
        raise ApiError(401, "UNAUTHENTICATED", "Phương thức đăng nhập chưa được hỗ trợ")
    user_id = _parse_uuid(token.removeprefix("dev:"), "UNAUTHENTICATED")

    memberships = db.scalars(select(Membership).where(Membership.user_id == user_id)).all()
    if not memberships:
        raise ApiError(403, "NO_MEMBERSHIP", "Tài khoản chưa thuộc workspace nào")
    if x_tenant_id:
        wanted = _parse_uuid(x_tenant_id, "INVALID_TENANT")
        match = next((m for m in memberships if m.tenant_id == wanted), None)
        if match is None:
            # same answer as a non-existent tenant: do not reveal which tenants exist
            raise ApiError(403, "FORBIDDEN", "Không có quyền với workspace này")
    elif len(memberships) == 1:
        match = memberships[0]
    else:
        raise ApiError(400, "TENANT_REQUIRED", "Cần chọn workspace (header X-Tenant-Id)")
    return AuthContext(user_id=user_id, tenant_id=match.tenant_id, role=match.role)


Auth = Annotated[AuthContext, Depends(get_auth)]


def require_role(minimum: str):
    def checker(auth: Auth) -> AuthContext:
        if ROLE_RANK.get(auth.role, -1) < ROLE_RANK[minimum]:
            raise ApiError(403, "FORBIDDEN", "Vai trò hiện tại không đủ quyền")
        return auth

    return checker


def require_writer(minimum: str):
    """Auditors are read-only regardless of rank."""

    def checker(auth: Auth) -> AuthContext:
        if auth.role == "auditor" or ROLE_RANK.get(auth.role, -1) < ROLE_RANK[minimum]:
            raise ApiError(403, "FORBIDDEN", "Vai trò hiện tại không đủ quyền")
        return auth

    return checker
