"""Voice agents: versioned config, eval-gated publish, rollback (plan/docs/01 Agents, AC04, AC25)."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select

from voiceos.agents.config import AgentConfig, compliance_problems, config_hash, default_config
from voiceos.api.deps import AuthContext, DbSession, require_role, require_writer
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.config import get_settings
from voiceos.db import utcnow
from voiceos.models import Agent, AgentVersion, Call, Tenant
from voiceos.services import enqueue, record_audit

router = APIRouter(prefix="/agents", tags=["agents"])

Reader = Annotated[AuthContext, Depends(require_role("auditor"))]
Manager = Annotated[AuthContext, Depends(require_writer("manager"))]
Admin = Annotated[AuthContext, Depends(require_writer("admin"))]

EVAL_STALE_AFTER = timedelta(minutes=30)


def _eval_view(v: AgentVersion) -> dict | None:
    tr = v.test_result or None
    if not tr:
        return None
    status = tr.get("status")
    requested = tr.get("requested_at")
    # an eval the gateway never reported back is shown as stale instead of spinning forever
    if status == "running" and requested and datetime.fromisoformat(requested) < utcnow() - EVAL_STALE_AFTER:
        status = "stale"
    return {
        "status": status,
        "passed": tr.get("passed"),
        "valid_for_current_config": tr.get("config_hash") == config_hash(v.config),
        "summary": tr.get("summary"),
        "requested_at": tr.get("requested_at"),
        "finished_at": tr.get("finished_at"),
        "rolled_back_from": tr.get("rolled_back_from"),
        "error": tr.get("error"),
    }


def _version_out(v: AgentVersion, active_id) -> dict:
    return {
        "id": str(v.id),
        "number": v.number,
        "status": v.status,
        "active": v.id == active_id,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "created_at": v.created_at.isoformat(),
        "eval": _eval_view(v),
    }


def _agent(db, auth: AuthContext, agent_id: uuid.UUID) -> Agent:
    agent = db.scalar(select(Agent).where(Agent.id == agent_id, Agent.tenant_id == auth.tenant_id))
    if agent is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy agent")
    return agent


def _versions(db, agent: Agent) -> list[AgentVersion]:
    return list(
        db.scalars(
            select(AgentVersion).where(AgentVersion.agent_id == agent.id).order_by(AgentVersion.number.desc())
        )
    )


def _draft(versions: list[AgentVersion]) -> AgentVersion | None:
    return next((v for v in versions if v.status == "draft"), None)


def _agent_out(db, agent: Agent, *, detail: bool) -> dict:
    versions = _versions(db, agent)
    active = next((v for v in versions if v.id == agent.active_version_id), None)
    draft = _draft(versions)
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    calls_today = db.scalar(
        select(func.count())
        .select_from(Call)
        .join(AgentVersion, AgentVersion.id == Call.agent_version_id)
        .where(AgentVersion.agent_id == agent.id, Call.started_at >= today)
    )
    out = {
        "id": str(agent.id),
        "name": agent.name,
        "purpose": agent.purpose,
        "description": agent.description,
        "version": agent.version,
        "active_version": _version_out(active, agent.active_version_id) if active else None,
        "draft": _version_out(draft, agent.active_version_id) if draft else None,
        "provider": (active or draft).config.get("provider") if (active or draft) else None,
        "calls_today": calls_today,
    }
    if detail:
        out["versions"] = [_version_out(v, agent.active_version_id) for v in versions]
        out["active_config"] = active.config if active else None
        out["draft_config"] = draft.config if draft else None
    return out


@router.get("")
def list_agents(auth: Reader, db: DbSession):
    agents = db.scalars(
        select(Agent).where(Agent.tenant_id == auth.tenant_id).order_by(Agent.created_at)
    ).all()
    return {"items": [_agent_out(db, a, detail=False) for a in agents], "trace_id": trace_id_var.get()}


@router.get("/{agent_id}")
def get_agent(agent_id: uuid.UUID, auth: Reader, db: DbSession):
    return {"data": _agent_out(db, _agent(db, auth, agent_id), detail=True), "trace_id": trace_id_var.get()}


class AgentIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    purpose: str = Field(default="receptionist", max_length=64)
    description: str | None = Field(default=None, max_length=300)


@router.post("", status_code=201)
def create_agent(body: AgentIn, auth: Manager, db: DbSession):
    tenant = db.get(Tenant, auth.tenant_id)
    agent = Agent(tenant_id=auth.tenant_id, **body.model_dump())
    db.add(agent)
    db.flush()
    db.add(
        AgentVersion(
            tenant_id=auth.tenant_id,
            agent_id=agent.id,
            number=1,
            status="draft",
            config=default_config(tenant.name),
        )
    )
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=agent,
        action="create",
        after=body.model_dump(),
    )
    db.commit()
    return {"data": _agent_out(db, agent, detail=True), "trace_id": trace_id_var.get()}


def _parse_config(raw: dict) -> dict:
    try:
        return AgentConfig.model_validate(raw).model_dump()
    except ValidationError as exc:
        fields: dict[str, list[str]] = {}
        for err in exc.errors():
            fields.setdefault(".".join(str(p) for p in err["loc"]) or "_", []).append(
                err["msg"].removeprefix("Value error, ")
            )
        raise ApiError(400, "INVALID_CONFIG", "Cấu hình agent không hợp lệ", field_errors=fields) from exc


class DraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: dict


@router.put("/{agent_id}/draft")
def save_draft(
    agent_id: uuid.UUID,
    body: DraftIn,
    auth: Manager,
    db: DbSession,
    if_match: Annotated[str | None, Header()] = None,
):
    """Create or update the single draft. Editing invalidates any earlier eval (hash no longer matches)."""
    agent = _agent(db, auth, agent_id)
    if if_match is None:
        raise ApiError(428, "IF_MATCH_REQUIRED", "Cần header If-Match với version của agent")
    if str(agent.version) != if_match.strip('"'):
        raise ApiError(409, "VERSION_CONFLICT", "Agent vừa được người khác chỉnh sửa, tải lại để tiếp tục")
    config = _parse_config(body.config)
    versions = _versions(db, agent)
    draft = _draft(versions)
    if draft is None:
        draft = AgentVersion(
            tenant_id=auth.tenant_id,
            agent_id=agent.id,
            number=(versions[0].number + 1) if versions else 1,
            status="draft",
            config=config,
        )
        db.add(draft)
    else:
        if (_eval_view(draft) or {}).get("status") == "running":
            raise ApiError(409, "EVAL_RUNNING", "Đang chạy đánh giá bản nháp này, đợi xong rồi sửa tiếp")
        draft.config = config
    agent.version += 1
    db.flush()
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=draft,
        action="save_draft",
        after={"number": draft.number, "config_hash": config_hash(config)},
    )
    db.commit()
    return {"data": _agent_out(db, agent, detail=True), "trace_id": trace_id_var.get()}


@router.post("/{agent_id}/draft/eval", status_code=202)
def run_draft_eval(agent_id: uuid.UUID, auth: Manager, db: DbSession):
    """Ask the media gateway to run the voice eval suite on the draft; results return via internal API."""
    agent = _agent(db, auth, agent_id)
    draft = _draft(_versions(db, agent))
    if draft is None:
        raise ApiError(409, "NO_DRAFT", "Chưa có bản nháp để đánh giá")
    if (_eval_view(draft) or {}).get("status") == "running":
        raise ApiError(409, "EVAL_RUNNING", "Đánh giá đang chạy")
    s = get_settings()
    if not s.gateway_service_token:
        raise ApiError(503, "GATEWAY_NOT_CONFIGURED", "Chưa cấu hình kết nối tới media gateway")
    payload = {
        "tenant_id": str(auth.tenant_id),
        "agent_id": str(agent.id),
        "version_id": str(draft.id),
        "config": draft.config,
        "config_hash": config_hash(draft.config),
    }
    try:
        r = httpx.post(
            f"{s.gateway_url.rstrip('/')}/internal/eval",
            json=payload,
            headers={"X-Service-Token": s.gateway_service_token},
            timeout=5,
        )
        r.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(
            503, "GATEWAY_UNAVAILABLE", "Không gọi được media gateway để chạy đánh giá", retryable=True
        ) from exc
    draft.test_result = {
        "status": "running",
        "config_hash": payload["config_hash"],
        "requested_at": utcnow().isoformat(),
        "requested_by": str(auth.user_id),
    }
    db.commit()
    return {"data": _version_out(draft, agent.active_version_id), "trace_id": trace_id_var.get()}


class PublishIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: uuid.UUID


@router.post("/{agent_id}/publish")
def publish(agent_id: uuid.UUID, body: PublishIn, auth: Admin, db: DbSession):
    agent = _agent(db, auth, agent_id)
    version = db.scalar(
        select(AgentVersion).where(AgentVersion.id == body.version_id, AgentVersion.agent_id == agent.id)
    )
    if version is None or version.status != "draft":
        raise ApiError(409, "NOT_A_DRAFT", "Chỉ xuất bản được bản nháp")
    problems = compliance_problems(AgentConfig.model_validate(version.config))
    if problems:
        raise ApiError(422, "COMPLIANCE_GREETING", "; ".join(problems), field_errors={"greeting": problems})
    tr = version.test_result or {}
    # AC25: only a passing eval of exactly this config unlocks publishing
    if not (
        tr.get("status") == "finished"
        and tr.get("passed") is True
        and tr.get("config_hash") == config_hash(version.config)
    ):
        raise ApiError(422, "EVAL_REQUIRED", "Bản nháp phải đạt bộ đánh giá voice trước khi xuất bản")
    previous = agent.active_version_id
    version.status = "published"
    version.published_at = utcnow()
    agent.active_version_id = version.id
    agent.version += 1
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=agent,
        action="publish",
        before={"active_version_id": str(previous) if previous else None},
        after={"active_version_id": str(version.id), "number": version.number},
    )
    enqueue(
        db,
        tenant_id=auth.tenant_id,
        topic="agent.published",
        payload={"agent_id": str(agent.id), "version_id": str(version.id)},
    )
    db.commit()
    return {"data": _agent_out(db, agent, detail=True), "trace_id": trace_id_var.get()}


class RollbackIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version_id: uuid.UUID


@router.post("/{agent_id}/rollback")
def rollback(agent_id: uuid.UUID, body: RollbackIn, auth: Admin, db: DbSession):
    """Publish a NEW version copied from an earlier published one; history stays immutable."""
    agent = _agent(db, auth, agent_id)
    target = db.scalar(
        select(AgentVersion).where(AgentVersion.id == body.version_id, AgentVersion.agent_id == agent.id)
    )
    if target is None or target.status != "published":
        raise ApiError(409, "NOT_PUBLISHED", "Chỉ quay lại được phiên bản đã từng xuất bản")
    if target.id == agent.active_version_id:
        raise ApiError(409, "ALREADY_ACTIVE", "Phiên bản này đang hoạt động")
    top = db.scalar(select(func.max(AgentVersion.number)).where(AgentVersion.agent_id == agent.id)) or 0
    new = AgentVersion(
        tenant_id=auth.tenant_id,
        agent_id=agent.id,
        number=top + 1,
        status="published",
        config=dict(target.config),
        test_result={**(target.test_result or {}), "rolled_back_from": target.number},
        published_at=utcnow(),
    )
    db.add(new)
    db.flush()
    previous = agent.active_version_id
    agent.active_version_id = new.id
    agent.version += 1
    record_audit(
        db,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        obj=agent,
        action="rollback",
        before={"active_version_id": str(previous) if previous else None},
        after={"active_version_id": str(new.id), "copied_from": target.number},
    )
    enqueue(
        db,
        tenant_id=auth.tenant_id,
        topic="agent.published",
        payload={"agent_id": str(agent.id), "version_id": str(new.id)},
    )
    db.commit()
    return {"data": _agent_out(db, agent, detail=True), "trace_id": trace_id_var.get()}
