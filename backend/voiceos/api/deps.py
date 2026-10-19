"""Authentication and tenant context.

Tenant is derived from an authenticated membership, never from the request body (plan/docs/06).
Two authenticators produce the same `AuthContext`:
- OIDC ID token (ADR 0008): signature/issuer/audience verified, user found by (issuer, subject); the first
  sign-in of an invited, provider-verified email binds that identity.
- dev token "dev:<user_uuid>", only when APP_ENV=dev and DEV_AUTH=true.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from voiceos.api.errors import ApiError
from voiceos.auth.oidc import TokenError, verify_id_token
from voiceos.config import get_settings
from voiceos.db import get_session, utcnow
from voiceos.models import Membership, User
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
    if token.startswith("dev:"):
        if not (settings.dev_auth and settings.app_env == "dev"):
            raise ApiError(401, "UNAUTHENTICATED", "Token dev chỉ dùng trong môi trường dev")
        user_id = _parse_uuid(token.removeprefix("dev:"), "UNAUTHENTICATED")
    else:
        user_id = _oidc_user(db, token)

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


def _oidc_user(db: Session, token: str) -> uuid.UUID:
    s = get_settings()
    try:
        ident = verify_id_token(token, issuer=s.oidc_issuer, audience=s.oidc_audience)
    except TokenError as exc:
        status = 503 if exc.code == "OIDC_UNAVAILABLE" else 401
        raise ApiError(status, exc.code, str(exc)) from exc
    user = db.scalar(select(User).where(User.oidc_issuer == ident.issuer, User.oidc_subject == ident.subject))
    if user is None:
        # first sign-in: only an invited email that the provider has verified may claim the account
        if not (ident.email and ident.email_verified):
            raise ApiError(403, "EMAIL_NOT_VERIFIED", "Email chưa được nhà cung cấp đăng nhập xác minh")
        user = db.scalar(select(User).where(User.email == ident.email))
        if user is None:
            raise ApiError(403, "NOT_INVITED", "Tài khoản chưa được mời vào workspace nào")
        if user.oidc_subject is not None:
            # invited email already bound to another identity: never re-bind by email (account takeover)
            raise ApiError(403, "IDENTITY_MISMATCH", "Email này đã gắn với một tài khoản đăng nhập khác")
        user.oidc_issuer, user.oidc_subject = ident.issuer, ident.subject
    user.last_login_at = utcnow()
    db.commit()
    return user.id


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
