"""Outbox dispatcher: at-least-once delivery with per-row leases (plan/docs/02 Durable execution).

Claiming uses a conditional UPDATE so it is correct on both SQLite and PostgreSQL:
only the worker whose UPDATE matched the row (rowcount == 1) owns it until the lease expires.
Handlers must be idempotent because a crashed worker's message is redelivered.
"""

import logging
import socket
import time
import uuid
from collections.abc import Callable
from datetime import timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from voiceos.db import utcnow
from voiceos.models import OutboxMessage

log = logging.getLogger("voiceos.worker")

Handler = Callable[[Session, OutboxMessage], None]
HANDLERS: dict[str, Handler] = {
    # M1 adds real handlers (notifications, CRM writeback, post-call processing)
    "contact.created": lambda db, msg: None,
}

LEASE = timedelta(seconds=60)
MAX_ATTEMPTS = 8


def claim(db: Session, owner: str, batch: int = 20) -> list[OutboxMessage]:
    now = utcnow()
    candidates = db.scalars(
        select(OutboxMessage.id)
        .where(
            OutboxMessage.dispatched_at.is_(None),
            OutboxMessage.available_at <= now,
            OutboxMessage.attempts < MAX_ATTEMPTS,
            or_(OutboxMessage.locked_until.is_(None), OutboxMessage.locked_until < now),
        )
        .order_by(OutboxMessage.available_at)
        .limit(batch)
    ).all()
    claimed: list[uuid.UUID] = []
    for msg_id in candidates:
        result = db.execute(
            update(OutboxMessage)
            .where(
                OutboxMessage.id == msg_id,
                OutboxMessage.dispatched_at.is_(None),
                or_(OutboxMessage.locked_until.is_(None), OutboxMessage.locked_until < now),
            )
            .values(lock_owner=owner, locked_until=now + LEASE, attempts=OutboxMessage.attempts + 1)
        )
        if result.rowcount == 1:
            claimed.append(msg_id)
    db.commit()
    if not claimed:
        return []
    return list(db.scalars(select(OutboxMessage).where(OutboxMessage.id.in_(claimed))))


def process(db: Session, msg: OutboxMessage) -> None:
    handler = HANDLERS.get(msg.topic)
    try:
        if handler is None:
            raise LookupError(f"no handler for topic {msg.topic}")
        handler(db, msg)
        msg.dispatched_at = utcnow()
        msg.last_error = None
    except Exception as exc:  # noqa: BLE001 - recorded and retried with backoff
        backoff = timedelta(seconds=min(2**msg.attempts, 600))
        msg.available_at = utcnow() + backoff
        msg.last_error = f"{type(exc).__name__}: {exc}"[:2000]
        log.warning("outbox %s failed (attempt %s): %s", msg.id, msg.attempts, msg.last_error)
    msg.lock_owner = None
    msg.locked_until = None
    db.commit()


def run_forever(factory: sessionmaker[Session], poll_seconds: float = 1.0) -> None:
    owner = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"
    log.info("worker %s started", owner)
    while True:
        with factory() as db:
            batch = claim(db, owner)
            for msg in batch:
                process(db, msg)
        if not batch:
            time.sleep(poll_seconds)
