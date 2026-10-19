import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from voiceos.api.deps import AuthContext, DbSession, require_role
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.models import Call, CallTurn, Contact, Task, ToolRun
from voiceos.services import paginate

router = APIRouter(prefix="/calls", tags=["calls"])

Reader = Annotated[AuthContext, Depends(require_role("auditor"))]


class CallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    direction: str
    contact_id: uuid.UUID | None
    agent_version_id: uuid.UUID | None
    provider: str
    started_at: datetime
    answered_at: datetime | None
    ended_at: datetime | None
    technical_status: str
    business_outcome: str | None
    after_hours: bool


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)  # SQLite returns naive UTC


def _enrich(db, auth: AuthContext, calls: list[Call]) -> list[dict]:
    """Add contact name and duration; names are looked up inside the tenant only."""
    ids = {c.contact_id for c in calls if c.contact_id}
    names = (
        dict(
            db.execute(
                select(Contact.id, Contact.name).where(
                    Contact.tenant_id == auth.tenant_id, Contact.id.in_(ids)
                )
            ).all()
        )
        if ids
        else {}
    )
    out = []
    for c in calls:
        d = CallOut.model_validate(c).model_dump(mode="json")
        d["contact_name"] = names.get(c.contact_id)
        start = c.answered_at or c.started_at
        d["duration_s"] = int((c.ended_at - start).total_seconds()) if c.ended_at and c.answered_at else 0
        out.append(d)
    return out


@router.get("")
def list_calls(
    auth: Reader,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    cursor: str | None = None,
    direction: Annotated[str | None, Query(pattern="^(inbound|outbound)$")] = None,
):
    stmt = select(Call).where(Call.tenant_id == auth.tenant_id)
    if direction:
        stmt = stmt.where(Call.direction == direction)
    rows, next_cursor = paginate(db, stmt, Call, limit=limit, cursor=cursor)
    return {
        "items": _enrich(db, auth, rows),
        "next_cursor": next_cursor,
        "trace_id": trace_id_var.get(),
    }


@router.get("/{call_id}")
def get_call(call_id: uuid.UUID, auth: Reader, db: DbSession):
    call = db.scalar(select(Call).where(Call.id == call_id, Call.tenant_id == auth.tenant_id))
    if call is None:
        raise ApiError(404, "NOT_FOUND", "Không tìm thấy cuộc gọi")
    turns = db.scalars(
        select(CallTurn)
        .where(CallTurn.call_id == call.id, CallTurn.tenant_id == auth.tenant_id)
        .order_by(CallTurn.seq)
    ).all()
    tools = db.scalars(
        select(ToolRun)
        .where(ToolRun.call_id == call.id, ToolRun.tenant_id == auth.tenant_id)
        .order_by(ToolRun.seq)
    ).all()
    return {
        "data": _enrich(db, auth, [call])[0],
        "tasks": [
            {"id": str(t.id), "type": t.type, "title": t.title, "status": t.status}
            for t in db.scalars(select(Task).where(Task.call_id == call.id, Task.tenant_id == auth.tenant_id))
        ],
        "turns": [
            {
                "seq": t.seq,
                "speaker": t.speaker,
                "text": t.text,
                "started_ms": t.started_ms,
                "played_until_ms": t.played_until_ms,
            }
            for t in turns
        ],
        "tool_runs": [
            {
                "seq": r.seq,
                "tool": r.tool_name,
                "args": r.args_redacted,
                "status": r.status,
                "result": r.result,
                # offset from call start so the UI can place tool events inside the transcript
                "started_ms": int((_utc(r.started_at) - _utc(call.started_at)).total_seconds() * 1000),
            }
            for r in tools
        ],
        "trace_id": trace_id_var.get(),
    }
