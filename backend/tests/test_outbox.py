from datetime import timedelta

from conftest import TENANT_A

from voiceos.db import utcnow
from voiceos.models import OutboxMessage
from voiceos.worker import outbox


def _add(session_factory, topic="contact.created"):
    with session_factory() as s:
        msg = OutboxMessage(tenant_id=TENANT_A, topic=topic, payload={})
        s.add(msg)
        s.commit()
        return msg.id


def test_two_workers_never_claim_same_message(session_factory):
    msg_id = _add(session_factory)
    with session_factory() as w1, session_factory() as w2:
        got1 = outbox.claim(w1, "w1")
        got2 = outbox.claim(w2, "w2")
    assert [m.id for m in got1] == [msg_id]
    assert got2 == []


def test_expired_lease_is_reclaimed(session_factory):
    msg_id = _add(session_factory)
    with session_factory() as s:
        outbox.claim(s, "crashed")
        row = s.get(OutboxMessage, msg_id)
        row.locked_until = utcnow() - timedelta(seconds=1)
        s.commit()
    with session_factory() as s:
        assert [m.id for m in outbox.claim(s, "w2")] == [msg_id]


def test_success_marks_dispatched(session_factory):
    msg_id = _add(session_factory)
    with session_factory() as s:
        for m in outbox.claim(s, "w"):
            outbox.process(s, m)
        row = s.get(OutboxMessage, msg_id)
        assert row.dispatched_at is not None and row.lock_owner is None


def test_failure_backs_off_and_records_error(session_factory):
    msg_id = _add(session_factory, topic="unknown.topic")
    with session_factory() as s:
        for m in outbox.claim(s, "w"):
            outbox.process(s, m)
        row = s.get(OutboxMessage, msg_id)
        assert row.dispatched_at is None and "no handler" in row.last_error
        assert outbox.claim(s, "w") == []  # backoff: not available yet
