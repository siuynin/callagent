"""Workspace members: invite, change role, remove (ADR 0008). Admin and owner only.

Rules: only an owner grants or removes the owner role; nobody changes or removes themselves; a workspace
always keeps at least one owner or admin; removing someone returns their open tasks to "unassigned".
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, update

from voiceos.api.deps import AuthContext, DbSession, require_writer
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.models import Membership, Task, User
from voiceos.models.tasks import TERMINAL
from voiceos.services import enqueue, record_audit

router = APIRouter(prefix="/admin/members", tags=["members"])

Admin = Annotated[AuthContext, Depends(require_writer("admin"))]
Role = Literal["owner", "admin", "manager", "staff", "auditor"]


def _out(m: Membership, u: User) -> dict:
    return {
        "user_id": str(u.id),
        "name": u.display_name,
        "email": u.email,
        "role": m.role,
        "status": "active" if u.oidc_subject else "invited",
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "invited_at": m.created_at.isoformat(),
    }


def _member(db, auth: AuthContext, user_id: uuid.UUID) -> tuple[Membership, User]:
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id, Membership.user_id == user_id)
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy thành viên")
    return row


def _admins_left(db, auth: AuthContext, excluding: uuid.UUID) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.tenant_id == auth.tenant_id,
            Membership.role.in_(("owner", "admin")),
            Membership.user_id != excluding,
        )
    )


def _check_grant(auth: AuthContext, role: str) -> None:
    if role == "owner" and auth.role != "owner":
        raise ApiError(403, "OWNER_ONLY", "Chỉ chủ sở hữu mới cấp được quyền chủ sở hữu")


@router.get("")
def list_members(auth: Admin, db: DbSession):
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id)
        .order_by(User.display_name)
    ).all()
    return {"items": [_out(m, u) for m, u in rows], "trace_id": trace_id_var.get()}


class InviteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role: Role = "staff"


@router.post("", status_code=201)
def invite(body: InviteIn, auth: Admin, db: DbSession):
    _check_grant(auth, body.role)
    email = body.email.lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=body.display_name)
        db.add(user)
        db.flush()
    elif db.scalar(
        select(Membership.id).where(Membership.tenant_id == auth.tenant_id, Membership.user_id == user.id)
    ):
        raise ApiError(409, "ALREADY_MEMBER", "Email này đã là thành viên của workspace")
    m = Membership(tenant_id=auth.tenant_id, user_id=user.id, role=body.role)
    db.add(m)
    db.flush()
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=m,
        action="invite",
        after={"email": email, "role": body.role},
    )
    # M1 notification adapter sends the invitation email; until then the admin shares the sign-in link
    enqueue(db, tenant_id=auth.tenant_id, topic="member.invited", payload={"user_id": str(user.id)})
    db.commit()
    return {"data": _out(m, user), "trace_id": trace_id_var.get()}


class RoleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Role


@router.patch("/{user_id}")
def change_role(user_id: uuid.UUID, body: RoleIn, auth: Admin, db: DbSession):
    if user_id == auth.user_id:
        raise ApiError(409, "SELF_CHANGE", "Không tự đổi vai trò của chính mình")
    m, u = _member(db, auth, user_id)
    _check_grant(auth, body.role)
    if m.role == "owner" and auth.role != "owner":
        raise ApiError(403, "OWNER_ONLY", "Chỉ chủ sở hữu mới đổi được vai trò của chủ sở hữu")
    if (
        m.role in ("owner", "admin")
        and body.role not in ("owner", "admin")
        and _admins_left(db, auth, user_id) == 0
    ):
        raise ApiError(409, "LAST_ADMIN", "Workspace cần ít nhất một quản trị viên")
    before = m.role
    m.role = body.role
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=m,
        action="change_role",
        before={"role": before},
        after={"role": body.role},
    )
    db.commit()
    return {"data": _out(m, u), "trace_id": trace_id_var.get()}


@router.delete("/{user_id}")
def remove(user_id: uuid.UUID, auth: Admin, db: DbSession):
    if user_id == auth.user_id:
        raise ApiError(409, "SELF_CHANGE", "Không tự gỡ chính mình khỏi workspace")
    m, u = _member(db, auth, user_id)
    if m.role == "owner" and auth.role != "owner":
        raise ApiError(403, "OWNER_ONLY", "Chỉ chủ sở hữu mới gỡ được chủ sở hữu")
    if m.role in ("owner", "admin") and _admins_left(db, auth, user_id) == 0:
        raise ApiError(409, "LAST_ADMIN", "Workspace cần ít nhất một quản trị viên")
    released = db.execute(
        update(Task)
        .where(Task.tenant_id == auth.tenant_id, Task.owner_id == user_id, Task.status.not_in(TERMINAL))
        .values(owner_id=None, status="new", version=Task.version + 1)
    ).rowcount
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=m,
        action="remove",
        before={"email": u.email, "role": m.role},
        after={"released_tasks": released},
    )
    db.delete(m)
    db.commit()
    return {"removed": True, "released_tasks": released, "trace_id": trace_id_var.get()}
