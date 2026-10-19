"""Cross-cutting write helpers: audit, outbox and idempotency. Callers own the transaction."""

import base64
import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from voiceos.api.errors import ApiError, trace_id_var
from voiceos.models import AuditEvent, IdempotencyRecord, OutboxMessage


def record_audit(db: Session, *, tenant_id, actor_user_id, obj, action: str, before=None, after=None) -> None:
    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            object_type=obj.__tablename__,
            object_id=obj.id,
            action=action,
            before=before,
            after=after,
            trace_id=trace_id_var.get() or None,
        )
    )


def enqueue(db: Session, *, tenant_id, topic: str, payload: dict) -> None:
    db.add(OutboxMessage(tenant_id=tenant_id, topic=topic, payload=payload))


def request_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def find_idempotent(db: Session, *, tenant_id, key: str | None, operation: str, payload: dict):
    """Return the stored (status, body) for a replay, raise 409 when the payload changed."""
    if not key:
        raise ApiError(400, "IDEMPOTENCY_KEY_REQUIRED", "Thiếu header Idempotency-Key")
    if len(key) > 128:
        raise ApiError(400, "INVALID_REQUEST", "Idempotency-Key quá dài")
    rec = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.tenant_id == tenant_id, IdempotencyRecord.key == key
        )
    )
    if rec is None:
        return None
    if rec.operation != operation or rec.request_hash != request_hash(payload):
        raise ApiError(409, "IDEMPOTENCY_KEY_REUSED", "Idempotency-Key đã dùng cho yêu cầu khác")
    return rec.status_code, rec.response


def store_idempotent(db: Session, *, tenant_id, key: str, operation: str, payload: dict, status: int, body):
    db.add(
        IdempotencyRecord(
            tenant_id=tenant_id,
            key=key,
            operation=operation,
            request_hash=request_hash(payload),
            status_code=status,
            response=json.loads(json.dumps(body, default=str)),
        )
    )


# --- cursor pagination over (created_at DESC, id DESC) ---


def encode_cursor(created_at: datetime, row_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{row_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, rid = base64.urlsafe_b64decode(cursor.encode()).decode().split("|")
        return datetime.fromisoformat(ts), uuid.UUID(rid)
    except Exception as exc:  # noqa: BLE001
        raise ApiError(400, "INVALID_CURSOR", "Cursor không hợp lệ") from exc


def paginate(db: Session, stmt, model, *, limit: int, cursor: str | None):
    stmt = stmt.order_by(model.created_at.desc(), model.id.desc())
    if cursor:
        ts, rid = decode_cursor(cursor)
        stmt = stmt.where(tuple_(model.created_at, model.id) < tuple_(ts, rid))
    rows = list(db.scalars(stmt.limit(limit + 1)))
    next_cursor = encode_cursor(rows[limit - 1].created_at, rows[limit - 1].id) if len(rows) > limit else None
    return rows[:limit], next_cursor
