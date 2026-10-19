"""Gateway -> backend persistence with an in-process fake backend (httpx.MockTransport)."""

import asyncio
import json

import httpx
import pytest
from conftest import chunks, silence, tone

from gateway.backend import BackendSink, redact_args
from gateway.providers.base import ToolCall
from gateway.providers.mock import MockLiveProvider
from gateway.session import CallSession, TurnAssembler


class FakeBackend:
    """Records internal API calls; can fail the first N requests to exercise retries."""

    def __init__(self, fail_first: int = 0, down: bool = False):
        self.fail_first, self.down = fail_first, down
        self.requests: list[tuple[str, dict, dict]] = []
        self.turns: dict[int, dict] = {}
        self.tool_keys: set[str] = set()
        self.handoffs = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/api/v1/internal")
        body = json.loads(request.content or b"{}")
        self.requests.append((path, body, dict(request.headers)))
        if self.down or self.fail_first > 0:
            self.fail_first -= 1
            return httpx.Response(503, json={"error": {"code": "UNAVAILABLE"}})
        if path == "/calls":
            return httpx.Response(200, json={"id": "call-1", "created": True})
        if path.endswith("/turns"):
            for t in body["turns"]:
                self.turns.setdefault(t["seq"], t)
            return httpx.Response(200, json={"accepted": len(body["turns"])})
        if path.endswith("/tool-runs"):
            self.tool_keys.update(r["idempotency_key"] for r in body["runs"])
            return httpx.Response(200, json={"accepted": len(body["runs"])})
        if path.endswith("/handoff"):
            self.handoffs += 1
            return httpx.Response(200, json={"task_id": "task-1", "created": True, "status": "queued"})
        if path.endswith("/end"):
            return httpx.Response(200, json={"updated": True})
        return httpx.Response(404)


@pytest.fixture()
def persisted(settings):
    return settings.model_copy(update={"gateway_service_token": "svc", "gateway_tenant_id": "tenant-a"})


def make_sink(settings, backend: FakeBackend) -> BackendSink:
    client = httpx.AsyncClient(transport=httpx.MockTransport(backend.handler))
    return BackendSink(
        settings=settings, provider="gateway-openai", provider_call_id="browser-abc", client=client
    )


def test_disabled_without_config(settings):
    sink = BackendSink(settings=settings, provider="p", provider_call_id="x")
    assert not sink.enabled
    sink.add_turn("agent", "xin chào", 0)  # no-op, no error
    assert sink._queue == []


def test_phone_is_redacted():
    assert redact_args({"phone": "0901 234 567", "customer_name": "An"}) == {
        "phone": "***4567",
        "customer_name": "An",
    }


async def test_sends_turns_tools_and_end_with_service_headers(persisted):
    backend = FakeBackend()
    sink = make_sink(persisted, backend)
    sink.start()
    sink.add_turn("agent", "Dạ, showroom xin nghe", 0)
    sink.add_turn("customer", "Cho hỏi giá", 3000)
    sink.add_tool_run(
        tool="create_appointment",
        call_key="call_1",
        args={"phone": "0901234567"},
        result={"status": "ok"},
        started_ms=5000,
        duration_ms=12,
    )
    summary = await sink.close(outcome="booked")
    assert summary["unsent"] == 0 and summary["ended"] is True
    assert [t["text"] for _, t in sorted(backend.turns.items())] == ["Dạ, showroom xin nghe", "Cho hỏi giá"]
    assert backend.tool_keys == {"browser-abc:call_1"}
    end = [b for p, b, _ in backend.requests if p.endswith("/end")][0]
    assert end["business_outcome"] == "booked"
    headers = backend.requests[0][2]
    assert headers["x-service-token"] == "svc" and headers["x-tenant-id"] == "tenant-a"
    tool_body = [b for p, b, _ in backend.requests if p.endswith("/tool-runs")][0]["runs"][0]
    assert tool_body["args"]["phone"] == "***4567"


async def test_retries_after_backend_errors(persisted):
    backend = FakeBackend(fail_first=2)
    sink = make_sink(persisted, backend)
    sink.start()
    sink.add_turn("agent", "xin chào", 0)
    summary = await sink.close(outcome=None)
    assert summary["unsent"] == 0 and backend.turns and summary["errors"]


async def test_backend_down_never_breaks_the_call(persisted):
    backend = FakeBackend(down=True)
    sink = make_sink(persisted, backend)
    sink.start()
    sink.add_turn("agent", "xin chào", 0)
    summary = await asyncio.wait_for(sink.close(outcome=None), timeout=10)
    assert summary["unsent"] == 1 and summary["ended"] is False
    assert await make_sink(persisted, backend).request_handoff("x", "y") is None


def test_late_caller_transcript_keeps_speech_start_order():
    class Rec:
        def __init__(self):
            self.turns = []

        def add_turn(self, speaker, text, started_ms, ended_ms=None):
            self.turns.append((speaker, text, started_ms))

    clock = {"t": 0}
    rec = Rec()
    a = TurnAssembler(rec, lambda: clock["t"])
    clock["t"] = 1000
    a.speech_started()  # caller starts talking at 1.0 s
    clock["t"] = 2500
    a.agent("Dạ em nghe ạ")  # agent answers at 2.5 s
    clock["t"] = 3500
    a.turn_complete()  # agent done; caller transcript not here yet (OpenAI delivers it late)
    clock["t"] = 3800
    a.caller("Cho hỏi giá xe")
    a.close()
    assert rec.turns == [("agent", "Dạ em nghe ạ", 2500), ("customer", "Cho hỏi giá xe", 1000)]
    # the UI sorts by started_ms, so the caller turn is shown before the answer


async def test_handoff_tool_creates_task_or_reports_failure(persisted):
    backend = FakeBackend()
    session = CallSession(MockLiveProvider(), None, persisted, mode="test", persist=True)
    session.sink = make_sink(persisted, backend)
    session.sink.start()
    call = ToolCall(
        call_id="c1", name="request_handoff", args={"reason": "Hỏi trả góp", "summary": "lãi suất"}
    )
    ok = await session._execute(call)
    assert ok["status"] == "ok" and ok["data"] == {"handoff_status": "queued", "task_id": "task-1"}
    session.sink = make_sink(persisted, FakeBackend(down=True))
    session.sink.start()
    failed = await session._execute(call)
    assert failed["status"] == "unavailable"  # agent must not say the request was registered


async def test_full_mock_call_is_persisted(persisted):
    from test_session import ScriptedTransport

    backend = FakeBackend()
    frames = chunks(tone(500)) + chunks(silence(1500)) + chunks(tone(500)) + chunks(silence(1500))
    session = CallSession(MockLiveProvider(), ScriptedTransport(frames), persisted, mode="test", persist=True)
    session.sink.client = httpx.AsyncClient(transport=httpx.MockTransport(backend.handler))
    summary = await session.run()
    p = summary["persistence"]
    assert p["enabled"] and p["ended"] and p["unsent"] == 0
    speakers = [t["speaker"] for _, t in sorted(backend.turns.items())]
    assert "agent" in speakers and "customer" in speakers
    assert any(k.startswith("test-") for k in backend.tool_keys)  # mock calls check_available_slots on turn 2
