"""Internal API for the media gateway (ADR 0006). Never exposed to browsers.

Auth: shared service token (X-Service-Token) + explicit X-Tenant-Id. The gateway is the only caller; user
sessions cannot reach these routes and the service token cannot reach user routes.
Every write is idempotent so the gateway can retry after timeouts without duplicating data (plan/docs/02).
"""

import hmac
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from voiceos.agents.config import config_hash
from voiceos.api.deps import DbSession
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.config import get_settings
from voiceos.db import utcnow
from voiceos.domain.phone import normalize_vn_phone
from voiceos.models import Agent, AgentVersion, Call, CallTurn, Contact, Task, Tenant, ToolRun
from voiceos.services import enqueue, record_audit

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)

TERMINAL_CALL = ("ended", "missed", "failed")
HANDOFF_DUE = timedelta(minutes=15)


@dataclass(frozen=True)
class ServiceContext:
    tenant_id: uuid.UUID


def get_service(
    db: DbSession,
    x_service_token: Annotated[str | None, Header()] = None,
    x_tenant_id: Annotated[str | None, Header()] = None,
) -> ServiceContext:
    expected = get_settings().gateway_service_token
    if not expected:
        raise ApiError(503, "INTERNAL_API_DISABLED", "Chưa cấu hình GATEWAY_SERVICE_TOKEN")
    if not x_service_token or not hmac.compare_digest(x_service_token.encode(), expected.encode()):
        raise ApiError(401, "UNAUTHENTICATED", "Service token không hợp lệ")
    try:
        tenant_id = uuid.UUID(x_tenant_id or "")
    except ValueError as exc:
        raise ApiError(400, "TENANT_REQUIRED", "Cần header X-Tenant-Id hợp lệ") from exc
    if db.get(Tenant, tenant_id) is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy workspace")
    return ServiceContext(tenant_id=tenant_id)


Service = Annotated[ServiceContext, Depends(get_service)]


def _call(db, svc: ServiceContext, call_id: uuid.UUID) -> Call:
    call = db.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == svc.tenant_id))
    if call is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy cuộc gọi")
    return call


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=utcnow().tzinfo)


def _own_version(db, svc: ServiceContext, version_id: uuid.UUID | None) -> uuid.UUID | None:
    if version_id is None:
        return None
    ok = db.scalar(
        select(AgentVersion.id).where(AgentVersion.id == version_id, AgentVersion.tenant_id == svc.tenant_id)
    )
    if ok is None:
        raise ApiError(422, "INVALID_REFERENCE", "Phiên bản agent không thuộc workspace này")
    return version_id


# --- agents ---


@router.get("/agents/active")
def active_agent(
    svc: Service, db: DbSession, agent_id: uuid.UUID | None = None, purpose: str = "receptionist"
):
    """Config live calls must use: the published active version only, never a draft (AC04)."""
    stmt = select(Agent).where(Agent.tenant_id == svc.tenant_id, Agent.active_version_id.is_not(None))
    stmt = stmt.where(Agent.id == agent_id) if agent_id else stmt.where(Agent.purpose == purpose)
    agent = db.scalar(stmt.order_by(Agent.created_at))
    version = db.get(AgentVersion, agent.active_version_id) if agent else None
    if version is None or version.status != "published" or version.tenant_id != svc.tenant_id:
        raise ApiError(404, "NO_ACTIVE_AGENT", "Chưa có agent nào được xuất bản")
    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "version_id": str(version.id),
        "number": version.number,
        "config": version.config,
        "trace_id": trace_id_var.get(),
    }


class EvalResultIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config_hash: str
    passed: bool
    summary: dict
    error: str | None = None


@router.post("/agent-versions/{version_id}/eval-result")
def eval_result(version_id: uuid.UUID, body: EvalResultIn, svc: Service, db: DbSession):
    version = db.scalar(
        select(AgentVersion).where(AgentVersion.id == version_id, AgentVersion.tenant_id == svc.tenant_id)
    )
    if version is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy phiên bản agent")
    # a result for an older config (draft edited meanwhile) or an already published version is ignored
    if version.status != "draft" or body.config_hash != config_hash(version.config):
        return {"accepted": False, "reason": "stale", "trace_id": trace_id_var.get()}
    version.test_result = {
        **(version.test_result or {}),
        "status": "finished",
        "passed": body.passed,
        "config_hash": body.config_hash,
        "summary": body.summary,
        "error": body.error,
        "finished_at": utcnow().isoformat(),
    }
    db.commit()
    return {"accepted": True, "trace_id": trace_id_var.get()}


# --- calls ---


class CallIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=32)
    provider_call_id: str = Field(min_length=1, max_length=128)
    direction: Literal["inbound", "outbound"] = "inbound"
    started_at: datetime
    caller_number: str | None = Field(default=None, max_length=32)
    after_hours: bool = False
    agent_version_id: uuid.UUID | None = None


@router.post("/calls")
def create_call(body: CallIn, svc: Service, db: DbSession):
    existing = db.scalar(
        select(Call).where(
            Call.tenant_id == svc.tenant_id,
            Call.provider == body.provider,
            Call.provider_call_id == body.provider_call_id,
        )
    )
    if existing:
        return {"id": str(existing.id), "created": False, "trace_id": trace_id_var.get()}
    contact_id = None
    if body.caller_number:
        phone = normalize_vn_phone(body.caller_number).e164
        matches = (
            db.scalars(
                select(Contact.id).where(
                    Contact.tenant_id == svc.tenant_id, Contact.normalized_phone == phone
                )
            ).all()
            if phone
            else []
        )
        # a shared family phone matches several people: never guess which one (AC03)
        contact_id = matches[0] if len(matches) == 1 else None
    call = Call(
        tenant_id=svc.tenant_id,
        direction=body.direction,
        provider=body.provider,
        provider_call_id=body.provider_call_id,
        started_at=body.started_at,
        answered_at=body.started_at,
        technical_status="in_progress",
        contact_id=contact_id,
        after_hours=body.after_hours,
        agent_version_id=_own_version(db, svc, body.agent_version_id),
    )
    db.add(call)
    try:
        db.flush()
    except IntegrityError:  # concurrent retry won the race: return its row
        db.rollback()
        return create_call(body, svc, db)
    enqueue(db, tenant_id=svc.tenant_id, topic="call.created", payload={"call_id": str(call.id)})
    db.commit()
    return {"id": str(call.id), "created": True, "trace_id": trace_id_var.get()}


class TurnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int = Field(ge=1)
    speaker: Literal["customer", "agent", "staff"]
    text: str = Field(max_length=8000)
    started_ms: int = Field(ge=0)
    ended_ms: int | None = Field(default=None, ge=0)
    played_until_ms: int | None = Field(default=None, ge=0)


class TurnsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    turns: list[TurnIn] = Field(max_length=200)


@router.post("/calls/{call_id}/turns")
def add_turns(call_id: uuid.UUID, body: TurnsIn, svc: Service, db: DbSession):
    call = _call(db, svc, call_id)
    have = set(db.scalars(select(CallTurn.seq).where(CallTurn.call_id == call.id)).all())
    accepted = 0
    for t in body.turns:
        if t.seq in have:
            continue  # retry of an already stored turn
        db.add(CallTurn(tenant_id=svc.tenant_id, call_id=call.id, **t.model_dump()))
        have.add(t.seq)
        accepted += 1
    db.commit()
    return {"accepted": accepted, "duplicates": len(body.turns) - accepted, "trace_id": trace_id_var.get()}


class ToolRunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    seq: int = Field(ge=1)
    tool: str = Field(min_length=1, max_length=64)
    args: dict
    status: str = Field(max_length=16)
    result: dict | None = None
    idempotency_key: str = Field(min_length=1, max_length=128)
    started_ms: int = Field(ge=0)
    duration_ms: int = Field(default=0, ge=0)


class ToolRunsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runs: list[ToolRunIn] = Field(max_length=100)


@router.post("/calls/{call_id}/tool-runs")
def add_tool_runs(call_id: uuid.UUID, body: ToolRunsIn, svc: Service, db: DbSession):
    call = _call(db, svc, call_id)
    keys = [r.idempotency_key for r in body.runs]
    have = set(
        db.scalars(
            select(ToolRun.idempotency_key).where(
                ToolRun.tenant_id == svc.tenant_id, ToolRun.idempotency_key.in_(keys)
            )
        ).all()
    )
    start = _aware(call.started_at)
    accepted = 0
    for r in body.runs:
        if r.idempotency_key in have:
            continue
        started = start + timedelta(milliseconds=r.started_ms)
        db.add(
            ToolRun(
                tenant_id=svc.tenant_id,
                call_id=call.id,
                seq=r.seq,
                tool_name=r.tool,
                args_redacted=r.args,
                status=r.status,
                result=r.result,
                idempotency_key=r.idempotency_key,
                started_at=started,
                finished_at=started + timedelta(milliseconds=r.duration_ms),
            )
        )
        have.add(r.idempotency_key)
        accepted += 1
    db.commit()
    return {"accepted": accepted, "duplicates": len(body.runs) - accepted, "trace_id": trace_id_var.get()}


def _system_task(db, svc: ServiceContext, call: Call, *, key: str, **fields) -> tuple[Task, bool]:
    existing = db.scalar(select(Task).where(Task.tenant_id == svc.tenant_id, Task.source_key == key))
    if existing:
        return existing, False
    task = Task(
        tenant_id=svc.tenant_id, call_id=call.id, contact_id=call.contact_id, source_key=key, **fields
    )
    db.add(task)
    db.flush()
    record_audit(
        db,
        tenant_id=svc.tenant_id,
        actor_user_id=None,
        obj=task,
        action="create",
        after={"source_key": key, "type": task.type},
    )
    enqueue(db, tenant_id=svc.tenant_id, topic="task.created", payload={"task_id": str(task.id)})
    return task, True


class HandoffIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=2000)


@router.post("/calls/{call_id}/handoff")
def request_handoff(call_id: uuid.UUID, body: HandoffIn, svc: Service, db: DbSession):
    """Caller asked for a human. Creates at most one inbox task per call; it is a request, not a transfer."""
    call = _call(db, svc, call_id)
    task, created = _system_task(
        db,
        svc,
        call,
        key=f"handoff:{call.id}",
        type="human_request",
        title=body.reason[:200],
        description=body.summary or None,
        priority="high",
        due_at=utcnow() + HANDOFF_DUE,
    )
    db.commit()
    return {"task_id": str(task.id), "created": created, "status": "queued", "trace_id": trace_id_var.get()}


class EndIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ended_at: datetime
    technical_status: Literal["ended", "missed", "failed"] = "ended"
    business_outcome: Literal["booked", "handoff", "callback", "interested", "declined"] | None = None


@router.post("/calls/{call_id}/end")
def end_call(call_id: uuid.UUID, body: EndIn, svc: Service, db: DbSession):
    call = _call(db, svc, call_id)
    if call.technical_status in TERMINAL_CALL:
        # late or repeated end event: terminal state never regresses (AC05)
        return {"id": str(call.id), "updated": False, "trace_id": trace_id_var.get()}
    call.ended_at = body.ended_at
    call.technical_status = body.technical_status
    call.business_outcome = body.business_outcome or call.business_outcome
    call.version += 1
    if call.business_outcome == "booked":
        _system_task(
            db,
            svc,
            call,
            key=f"appointment:{call.id}",
            type="appointment_confirm",
            title="Xác nhận lịch hẹn AI vừa đặt",
            due_at=utcnow() + timedelta(hours=2),
        )
    enqueue(db, tenant_id=svc.tenant_id, topic="call.ended", payload={"call_id": str(call.id)})
    db.commit()
    return {"id": str(call.id), "updated": True, "trace_id": trace_id_var.get()}
