"""Inbox tasks (plan/docs/01 Inbox, plan/docs/03 Task state machine, plan/docs/07 AC08)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select

from voiceos.api.deps import AuthContext, DbSession, require_role, require_writer
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.db import utcnow
from voiceos.models import Contact, Membership, Task, User
from voiceos.models.tasks import TERMINAL
from voiceos.models.tenancy import ROLE_RANK
from voiceos.services import enqueue, find_idempotent, record_audit, store_idempotent

router = APIRouter(tags=["tasks"])

Reader = Annotated[AuthContext, Depends(require_role("auditor"))]
Writer = Annotated[AuthContext, Depends(require_writer("staff"))]

TaskType = Literal["missed_call", "human_request", "callback", "appointment_confirm", "follow_up"]
Status = Literal["new", "in_progress", "resolved", "cancelled"]
ALLOWED = {
    "new": {"new", "in_progress", "resolved", "cancelled"},
    "in_progress": {"in_progress", "resolved", "cancelled", "new"},
    "resolved": {"resolved"},
    "cancelled": {"cancelled"},
}


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: TaskType
    title: str = Field(min_length=1, max_length=200)
    contact_id: uuid.UUID | None = None
    call_id: uuid.UUID | None = None
    owner_id: uuid.UUID | None = None
    priority: Literal["high", "normal"] = "normal"
    due_at: datetime | None = None


class TaskPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: uuid.UUID | None = None
    status: Status | None = None
    priority: Literal["high", "normal"] | None = None
    due_at: datetime | None = None
    outcome: str | None = Field(default=None, max_length=64)
    resolution_note: str | None = Field(default=None, max_length=4000)


def _aware(dt: datetime | None) -> datetime | None:
    # SQLite returns naive datetimes; values are always stored as UTC
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def _out(task: Task, contact: Contact | None, owner: User | None, now: datetime) -> dict:
    due = _aware(task.due_at)
    return {
        "id": str(task.id),
        "type": task.type,
        "title": task.title,
        "contact": {"id": str(contact.id), "name": contact.name} if contact else None,
        "call_id": str(task.call_id) if task.call_id else None,
        "owner": {"id": str(owner.id), "name": owner.display_name} if owner else None,
        "priority": task.priority,
        "due_at": due.isoformat() if due else None,
        # computed with the server clock, never the browser's (AC08)
        "overdue": bool(due and due < now and task.status not in TERMINAL),
        "status": task.status,
        "outcome": task.outcome,
        "resolution_note": task.resolution_note,
        "resolved_at": _aware(task.resolved_at).isoformat() if task.resolved_at else None,
        "version": task.version,
        "created_at": _aware(task.created_at).isoformat(),
    }


def _rows(db, auth: AuthContext, stmt):
    stmt = stmt.outerjoin(Contact, and_(Contact.id == Task.contact_id, Contact.tenant_id == Task.tenant_id))
    stmt = stmt.outerjoin(User, User.id == Task.owner_id)
    return db.execute(stmt.add_columns(Contact, User)).all()


def _get(db, auth: AuthContext, task_id: uuid.UUID) -> Task:
    task = db.scalar(select(Task).where(Task.id == task_id, Task.tenant_id == auth.tenant_id))
    if task is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy công việc")
    return task


def _check_member(db, auth: AuthContext, user_id: uuid.UUID) -> None:
    member = db.scalar(
        select(Membership).where(Membership.tenant_id == auth.tenant_id, Membership.user_id == user_id)
    )
    if member is None:
        raise ApiError(
            422,
            "OWNER_NOT_MEMBER",
            "Người phụ trách không thuộc workspace này",
            field_errors={"owner_id": ["invalid"]},
        )


def _check_ref(db, auth: AuthContext, model, ref_id: uuid.UUID | None, field: str) -> None:
    if (
        ref_id
        and db.scalar(select(model.id).where(model.id == ref_id, model.tenant_id == auth.tenant_id)) is None
    ):
        raise ApiError(
            422, "INVALID_REFERENCE", "Tham chiếu không hợp lệ", field_errors={field: ["not found"]}
        )


@router.get("/tasks")
def list_tasks(
    auth: Reader,
    db: DbSession,
    status: Annotated[Status | None, Query()] = None,
    overdue: bool = False,
    unassigned: bool = False,
    task_type: Annotated[TaskType | None, Query(alias="type")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    now = utcnow()
    stmt = select(Task).where(Task.tenant_id == auth.tenant_id)
    if status:
        stmt = stmt.where(Task.status == status)
    if task_type:
        stmt = stmt.where(Task.type == task_type)
    if overdue:
        stmt = stmt.where(Task.due_at < now, Task.status.not_in(TERMINAL))
    if unassigned:
        stmt = stmt.where(Task.owner_id.is_(None), Task.status.not_in(TERMINAL))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Task.title).like(like), func.lower(Contact.name).like(like)))
    # open work first, then by deadline (no deadline last), newest otherwise
    stmt = stmt.order_by(
        Task.status.in_(TERMINAL), Task.due_at.is_(None), Task.due_at, Task.created_at.desc()
    )
    rows = _rows(db, auth, stmt.limit(limit))
    return {"items": [_out(t, c, u, now) for t, c, u in rows], "trace_id": trace_id_var.get()}


@router.get("/tasks/summary")
def task_summary(auth: Reader, db: DbSession):
    now = utcnow()
    base = select(func.count()).select_from(Task).where(Task.tenant_id == auth.tenant_id)
    open_ = Task.status.not_in(TERMINAL)
    return {
        "unassigned": db.scalar(base.where(open_, Task.owner_id.is_(None))),
        "overdue": db.scalar(base.where(open_, Task.due_at < now)),
        "in_progress": db.scalar(base.where(Task.status == "in_progress")),
        "resolved": db.scalar(base.where(Task.status == "resolved")),
        "trace_id": trace_id_var.get(),
    }


@router.post("/tasks", status_code=201)
def create_task(
    body: TaskIn,
    auth: Writer,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    payload = body.model_dump(mode="json")
    replay = find_idempotent(
        db, tenant_id=auth.tenant_id, key=idempotency_key, operation="createTask", payload=payload
    )
    if replay:
        return JSONResponse(status_code=replay[0], content=replay[1])
    if body.owner_id:
        _check_member(db, auth, body.owner_id)
    _check_ref(db, auth, Contact, body.contact_id, "contact_id")
    task = Task(tenant_id=auth.tenant_id, **body.model_dump())
    db.add(task)
    db.flush()
    now = utcnow()
    (t, c, u) = _rows(db, auth, select(Task).where(Task.id == task.id))[0]
    out = _out(t, c, u, now)
    record_audit(
        db, tenant_id=auth.tenant_id, actor_user_id=auth.user_id, obj=task, action="create", after=out
    )
    if task.owner_id:
        enqueue(db, tenant_id=auth.tenant_id, topic="task.assigned", payload={"task_id": str(task.id)})
    store_idempotent(
        db,
        tenant_id=auth.tenant_id,
        key=idempotency_key,
        operation="createTask",
        payload=payload,
        status=201,
        body={"data": out},
    )
    db.commit()
    return {"data": out, "trace_id": trace_id_var.get()}


@router.patch("/tasks/{task_id}")
def update_task(
    task_id: uuid.UUID,
    body: TaskPatch,
    auth: Writer,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
):
    if if_match is None:
        raise ApiError(428, "IF_MATCH_REQUIRED", "Cần header If-Match với version hiện tại")
    task = _get(db, auth, task_id)
    if str(task.version) != if_match.strip('"'):
        raise ApiError(409, "VERSION_CONFLICT", "Công việc vừa được người khác cập nhật, tải lại để tiếp tục")

    changes = body.model_dump(exclude_unset=True)
    # staff work on their own or unassigned tasks and may only assign to themselves
    if ROLE_RANK[auth.role] < ROLE_RANK["manager"]:
        if task.owner_id not in (None, auth.user_id):
            raise ApiError(403, "NOT_TASK_OWNER", "Công việc đang do người khác phụ trách")
        if "owner_id" in changes and changes["owner_id"] not in (None, auth.user_id):
            raise ApiError(403, "FORBIDDEN", "Nhân viên chỉ có thể tự nhận việc")

    new_status = changes.get("status", task.status)
    if new_status not in ALLOWED[task.status]:
        raise ApiError(409, "INVALID_TRANSITION", "Công việc đã đóng, không thể đổi trạng thái")
    owner = changes.get("owner_id", task.owner_id)
    note = changes.get("resolution_note", task.resolution_note)
    errors: dict[str, list[str]] = {}
    if new_status == "in_progress" and owner is None:
        errors["owner_id"] = ["Cần người phụ trách trước khi bắt đầu xử lý"]
    if new_status == "resolved":
        if owner is None:
            errors["owner_id"] = ["Cần người phụ trách trước khi hoàn thành"]
        if not (note or "").strip():
            errors["resolution_note"] = ["Cần ghi kết quả xử lý trước khi hoàn thành"]
    if errors:
        raise ApiError(422, "TASK_RULES", "Chưa đủ điều kiện cập nhật công việc", field_errors=errors)
    if "owner_id" in changes and changes["owner_id"]:
        _check_member(db, auth, changes["owner_id"])

    now = utcnow()
    (t, c, u) = _rows(db, auth, select(Task).where(Task.id == task.id))[0]
    before = _out(t, c, u, now)
    owner_changed = "owner_id" in changes and changes["owner_id"] != task.owner_id
    for field, value in changes.items():
        setattr(task, field, value)
    if new_status == "resolved" and task.resolved_at is None:
        task.resolved_at = now
    task.version += 1
    db.flush()
    db.expire(task)
    (t, c, u) = _rows(db, auth, select(Task).where(Task.id == task.id))[0]
    after = _out(t, c, u, now)
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=task,
        action="update",
        before=before,
        after=after,
    )
    if owner_changed and task.owner_id:
        enqueue(db, tenant_id=auth.tenant_id, topic="task.assigned", payload={"task_id": str(task.id)})
    db.commit()
    return {"data": after, "trace_id": trace_id_var.get()}


@router.get("/members")
def list_members(auth: Reader, db: DbSession):
    """Minimal directory for assignment pickers: names and roles, no contact details."""
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == auth.tenant_id)
        .order_by(User.display_name)
    ).all()
    return {
        "items": [{"user_id": str(u.id), "name": u.display_name, "role": m.role} for m, u in rows],
        "trace_id": trace_id_var.get(),
    }
