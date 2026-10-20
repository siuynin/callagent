"""Working calendar, holidays and inbound routing (plan/docs/06 catalog, AC23, AC24)."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from voiceos.api.deps import AuthContext, DbSession, require_role, require_writer
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.db import utcnow
from voiceos.domain.calendar import (
    EXCEPTION_KINDS,
    WEEKDAY_KEYS,
    status_at,
    timezone_problem,
    weekly_problems,
    window_problems,
)
from voiceos.models import BusinessCalendar, CalendarException, InboundRoute, Membership, User
from voiceos.models.scheduling import ROUTE_TARGETS
from voiceos.scheduling import ensure_defaults, exceptions_of, to_domain
from voiceos.services import record_audit

router = APIRouter(tags=["calendars"])

Manager = Annotated[AuthContext, Depends(require_role("manager"))]
Admin = Annotated[AuthContext, Depends(require_writer("admin"))]

MAX_EXCEPTION_DAYS = 31


def _check_if_match(obj, if_match: str | None, what: str) -> None:
    if if_match is None:
        raise ApiError(428, "IF_MATCH_REQUIRED", f"Cần header If-Match với version của {what}")
    if str(obj.version) != if_match.strip('"'):
        raise ApiError(
            409, "VERSION_CONFLICT", f"{what.capitalize()} vừa được người khác sửa, tải lại rồi thử lại"
        )


def _invalid(problems: list[str], field: str) -> ApiError:
    return ApiError(422, "INVALID_REQUEST", problems[0], field_errors={field: problems})


def _exception_out(e: CalendarException) -> dict:
    return {
        "id": str(e.id),
        "date_from": e.date_from.isoformat(),
        "date_to": e.date_to.isoformat(),
        "kind": e.kind,
        "hours": e.hours or [],
        "label": e.label,
    }


def _calendar_out(db, cal: BusinessCalendar) -> dict:
    exceptions = exceptions_of(db, cal)
    st = status_at(to_domain(cal, exceptions), utcnow())
    return {
        "id": str(cal.id),
        "name": cal.name,
        "timezone": cal.timezone,
        "weekly_hours": {k: cal.weekly_hours.get(k, []) for k in WEEKDAY_KEYS},
        "version": cal.version,
        "exceptions": [_exception_out(e) for e in exceptions],
        "status": {
            "open": st.open,
            "closes_at": st.closes_at.isoformat() if st.closes_at else None,
            "opens_at": st.opens_at.isoformat() if st.opens_at else None,
            "reason": st.reason,
        },
    }


def _calendar(db, auth: AuthContext, calendar_id: uuid.UUID) -> BusinessCalendar:
    cal = db.scalar(
        select(BusinessCalendar).where(
            BusinessCalendar.id == calendar_id, BusinessCalendar.tenant_id == auth.tenant_id
        )
    )
    if cal is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy lịch làm việc")
    return cal


@router.get("/business-calendars")
def list_calendars(auth: Manager, db: DbSession):
    ensure_defaults(db, auth.tenant_id)
    db.commit()
    cals = db.scalars(
        select(BusinessCalendar)
        .where(BusinessCalendar.tenant_id == auth.tenant_id)
        .order_by(BusinessCalendar.created_at)
    )
    return {"items": [_calendar_out(db, c) for c in cals], "trace_id": trace_id_var.get()}


class CalendarIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=64)
    weekly_hours: dict[str, list[list[str]]]


@router.put("/business-calendars/{calendar_id}")
def update_calendar(
    calendar_id: uuid.UUID,
    body: CalendarIn,
    auth: Admin,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
):
    cal = _calendar(db, auth, calendar_id)
    _check_if_match(cal, if_match, "lịch làm việc")
    if problem := timezone_problem(body.timezone):
        raise _invalid([problem], "timezone")
    if problems := weekly_problems(body.weekly_hours):
        raise _invalid(problems, "weekly_hours")
    before = {"timezone": cal.timezone, "weekly_hours": cal.weekly_hours}
    cal.name = body.name
    cal.timezone = body.timezone
    cal.weekly_hours = {k: body.weekly_hours.get(k, []) for k in WEEKDAY_KEYS}
    cal.version += 1
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=cal,
        action="update",
        before=before,
        after={"timezone": cal.timezone, "weekly_hours": cal.weekly_hours},
    )
    db.commit()
    return {"data": _calendar_out(db, cal), "trace_id": trace_id_var.get()}


class ExceptionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date_from: date
    date_to: date
    kind: Literal[EXCEPTION_KINDS]  # type: ignore[valid-type]
    hours: list[list[str]] = Field(default_factory=list)
    label: str = Field(min_length=1, max_length=200)


@router.post("/business-calendars/{calendar_id}/exceptions", status_code=201)
def add_exception(calendar_id: uuid.UUID, body: ExceptionIn, auth: Admin, db: DbSession):
    cal = _calendar(db, auth, calendar_id)
    if body.date_to < body.date_from:
        raise _invalid(["Ngày kết thúc phải từ ngày bắt đầu trở đi"], "date_to")
    if (body.date_to - body.date_from).days >= MAX_EXCEPTION_DAYS:
        raise _invalid([f"Mỗi lần nghỉ tối đa {MAX_EXCEPTION_DAYS} ngày"], "date_to")
    if body.kind == "special_hours":
        problems = window_problems(body.hours, "Giờ đặc biệt") or ([] if body.hours else ["Nhập giờ mở cửa"])
        if problems:
            raise _invalid(problems, "hours")
    exc = CalendarException(
        tenant_id=auth.tenant_id,
        calendar_id=cal.id,
        date_from=body.date_from,
        date_to=body.date_to,
        kind=body.kind,
        hours=body.hours if body.kind == "special_hours" else None,
        label=body.label.strip(),
    )
    db.add(exc)
    db.flush()
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=exc,
        action="create",
        after=_exception_out(exc),
    )
    db.commit()
    return {"data": _exception_out(exc), "trace_id": trace_id_var.get()}


@router.delete("/business-calendars/{calendar_id}/exceptions/{exception_id}")
def delete_exception(calendar_id: uuid.UUID, exception_id: uuid.UUID, auth: Admin, db: DbSession):
    cal = _calendar(db, auth, calendar_id)
    exc = db.scalar(
        select(CalendarException).where(
            CalendarException.id == exception_id, CalendarException.calendar_id == cal.id
        )
    )
    if exc is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy ngày nghỉ")
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=exc,
        action="delete",
        before=_exception_out(exc),
    )
    db.delete(exc)
    db.commit()
    return {"deleted": True, "trace_id": trace_id_var.get()}


def _route_out(db, r: InboundRoute) -> dict:
    owner = db.get(User, r.after_hours_owner_id) if r.after_hours_owner_id else None
    return {
        "id": str(r.id),
        "number": r.number,
        "calendar_id": str(r.calendar_id),
        "in_hours_target": r.in_hours_target,
        "after_hours_target": r.after_hours_target,
        "ai_failure_target": r.ai_failure_target,
        "after_hours_owner": {"user_id": str(owner.id), "name": owner.display_name} if owner else None,
        "announcement": r.announcement,
        "version": r.version,
    }


@router.get("/inbound-routes")
def list_routes(auth: Manager, db: DbSession):
    ensure_defaults(db, auth.tenant_id)
    db.commit()
    routes = db.scalars(
        select(InboundRoute).where(InboundRoute.tenant_id == auth.tenant_id).order_by(InboundRoute.number)
    )
    return {"items": [_route_out(db, r) for r in routes], "trace_id": trace_id_var.get()}


class RouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    in_hours_target: Literal[ROUTE_TARGETS]  # type: ignore[valid-type]
    after_hours_target: Literal[ROUTE_TARGETS]  # type: ignore[valid-type]
    ai_failure_target: Literal["announcement"] = "announcement"
    after_hours_owner_id: uuid.UUID | None = None
    announcement: str = Field(default="", max_length=1000)


@router.put("/inbound-routes/{route_id}")
def update_route(
    route_id: uuid.UUID,
    body: RouteIn,
    auth: Admin,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
):
    route = db.scalar(
        select(InboundRoute).where(InboundRoute.id == route_id, InboundRoute.tenant_id == auth.tenant_id)
    )
    if route is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy định tuyến")
    _check_if_match(route, if_match, "định tuyến")
    announcement = body.announcement.strip()
    if (
        "announcement" in (body.in_hours_target, body.after_hours_target, body.ai_failure_target)
        and not announcement
    ):
        raise _invalid(["Nhập nội dung thông báo"], "announcement")
    if body.after_hours_owner_id and not db.scalar(
        select(Membership.id).where(
            Membership.tenant_id == auth.tenant_id,
            Membership.user_id == body.after_hours_owner_id,
            Membership.role != "auditor",
        )
    ):
        raise _invalid(["Người nhận việc phải là thành viên có quyền xử lý việc"], "after_hours_owner_id")
    before = _route_out(db, route)
    route.in_hours_target = body.in_hours_target
    route.after_hours_target = body.after_hours_target
    route.ai_failure_target = body.ai_failure_target
    route.after_hours_owner_id = body.after_hours_owner_id
    route.announcement = announcement
    route.version += 1
    db.flush()
    after = _route_out(db, route)
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=route,
        action="update",
        before=before,
        after=after,
    )
    db.commit()
    return {"data": after, "trace_id": trace_id_var.get()}
