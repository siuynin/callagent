import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from voiceos.api.deps import AuthContext, DbSession, require_role
from voiceos.api.errors import ApiError, trace_id_var
from voiceos.models import Call, CallTurn, ToolRun
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
        "items": [CallOut.model_validate(r).model_dump(mode="json") for r in rows],
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
        "data": CallOut.model_validate(call).model_dump(mode="json"),
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
            }
            for r in tools
        ],
        "trace_id": trace_id_var.get(),
    }
