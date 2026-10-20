import json
from datetime import datetime

import httpx
import pytest
from conftest import tone, write_wav
from fastapi.testclient import TestClient

from gateway import agent as agent_mod
from gateway import evals
from gateway.agent import AgentRuntime, Routing, build_spec, fetch_active_agent, fetch_routing, settings_for
from gateway.providers.base import ToolCall
from gateway.providers.mock import MockLiveProvider
from gateway.session import CallSession

CONFIG = {
    "instructions": 'Bạn là lễ tân của {business_name}. Hôm nay {today}. Câu đầu: "{greeting}". ' + "x" * 60,
    "greeting": "Dạ, {business_name} xin nghe, em là trợ lý AI, cuộc gọi được ghi âm.",
    "business_name": "Showroom Thử",
    "provider": "openai",
    "voice": "cedar",
    "tools": ["check_available_slots", "request_handoff"],
    "vad_silence_ms": 750,
    "eval_max_p95_ms": 2000,
}


@pytest.fixture()
def wired(settings):
    return settings.model_copy(update={"gateway_service_token": "svc", "gateway_tenant_id": "tenant-a"})


def test_spec_uses_version_config_and_tool_allowlist(settings):
    spec = build_spec(settings, AgentRuntime(config=CONFIG, version_id="v2", number=2))
    assert "Showroom Thử" in spec.system_instruction
    assert "Dạ, Showroom Thử xin nghe" in spec.system_instruction  # greeting rendered inside the prompt
    assert {t.name for t in spec.tools} == {"check_available_slots", "request_handoff"}


def test_bundled_prompt_fallback(settings):
    spec = build_spec(settings)
    assert "trợ lý AI" in spec.system_instruction and "{greeting}" not in spec.system_instruction
    assert len(spec.tools) == 3


def test_settings_for_applies_voice_only_for_its_provider(settings):
    agent = AgentRuntime(config=CONFIG, version_id="v2")
    same = settings_for(settings, agent, "openai")
    assert (
        same.openai_voice == "cedar" and same.vad_silence_ms == 750 and same.business_name == "Showroom Thử"
    )
    other = settings_for(settings, agent, "gemini")
    assert other.ai_voice == settings.ai_voice  # "cedar" is not a Gemini voice
    assert settings_for(settings, None, "openai") is settings


async def test_disallowed_tool_is_refused(settings):
    session = CallSession(MockLiveProvider(), None, settings, agent=AgentRuntime(config=CONFIG))
    r = await session._execute(ToolCall(call_id="c", name="create_appointment", args={}))
    assert r["status"] == "unavailable"
    ok = await session._execute(
        ToolCall(call_id="c", name="check_available_slots", args={"date": "2099-01-05"})
    )
    assert ok["status"] == "ok"


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _mock_client(handler):
    real = _REAL_ASYNC_CLIENT  # not the possibly already patched attribute

    def factory(*a, **k):
        k["transport"] = httpx.MockTransport(handler)
        return real(*a, **k)

    return factory


async def test_fetch_active_agent_and_fallback(wired, monkeypatch):
    seen = {}

    def ok(request):
        seen["headers"] = dict(request.headers)
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"version_id": "v3", "number": 3, "config": CONFIG, "agent_id": "a"})

    monkeypatch.setattr(agent_mod.httpx, "AsyncClient", _mock_client(ok))
    got = await fetch_active_agent(wired)
    assert got.version_id == "v3" and got.number == 3 and got.source == "backend"
    assert seen["headers"]["x-service-token"] == "svc" and seen["params"] == {"purpose": "receptionist"}

    monkeypatch.setattr(agent_mod.httpx, "AsyncClient", _mock_client(lambda r: httpx.Response(404, json={})))
    assert await fetch_active_agent(wired) is None
    assert await fetch_active_agent(wired.model_copy(update={"gateway_service_token": ""})) is None


def test_eval_endpoint_auth_and_busy(wired, monkeypatch):
    from gateway import main

    monkeypatch.setattr(main, "get_settings", lambda: wired)
    started = []

    async def fake_suite(settings, req):
        started.append(req.version_id)

    monkeypatch.setattr(main.evals, "run_suite", fake_suite)
    client = TestClient(main.app)
    body = {
        "tenant_id": "tenant-a",
        "agent_id": "a",
        "version_id": "v9",
        "config": CONFIG,
        "config_hash": "h",
    }
    assert client.post("/internal/eval", json=body).status_code == 401
    assert client.post("/internal/eval", json=body, headers={"X-Service-Token": "bad"}).status_code == 401
    other = {**body, "tenant_id": "tenant-b"}
    assert client.post("/internal/eval", json=other, headers={"X-Service-Token": "svc"}).status_code == 401
    assert client.post("/internal/eval", json=body, headers={"X-Service-Token": "svc"}).status_code == 202


def test_verdict_rules():
    good = {
        "scenario": "a",
        "passed": True,
        "summary": {"false_confirmations": 0, "latency_ms": {"p95": 900}},
    }
    slow = {
        "scenario": "b",
        "passed": True,
        "summary": {"false_confirmations": 0, "latency_ms": {"p95": 2600}},
    }
    bad = {
        "scenario": "c",
        "passed": False,
        "checks": [{"check": "x", "passed": False}],
        "summary": {"false_confirmations": 1, "latency_ms": {"p95": 800}},
    }
    assert evals.verdict([good], 2000)[0] is True
    assert evals.verdict([good, slow], 2000)[0] is False
    passed, summary = evals.verdict([good, bad], 2000)
    assert not passed and summary["failed"] == ["c"] and summary["false_confirmations"] == 1
    assert evals.verdict([], 2000)[0] is False  # no scenarios never unlocks publishing


async def test_suite_runs_with_draft_config_and_reports(wired, tmp_path, monkeypatch):
    write_wav(tmp_path / "t1.wav", tone(600))
    scenario = {"id": "mock-1", "turns": [{"audio": "t1.wav"}], "expect": {"no_false_confirm": True}}
    (tmp_path / "s.json").write_text(json.dumps(scenario), encoding="utf-8")
    reported = []

    def backend(request):
        reported.append((request.url.path, json.loads(request.content), dict(request.headers)))
        return httpx.Response(200, json={"accepted": True})

    monkeypatch.setattr(evals.httpx, "AsyncClient", _mock_client(backend))
    cfg = {**CONFIG, "provider": "mock"}
    req = evals.EvalRequest(tenant_id="tenant-a", agent_id="a", version_id="v9", config=cfg, config_hash="h1")
    await evals.run_suite(wired, req, paths=[tmp_path / "s.json"])
    path, body, headers = reported[0]
    assert path.endswith("/agent-versions/v9/eval-result")
    assert body["config_hash"] == "h1" and body["passed"] is True and body["summary"]["scenarios"] == 1
    assert headers["x-tenant-id"] == "tenant-a"


# --- routing by working hours (AC24) ---

ICT = agent_mod.ZoneInfo("Asia/Ho_Chi_Minh")
NIGHT = datetime(2026, 10, 19, 21, 0, tzinfo=ICT)  # Monday evening
NEXT_MORNING = datetime(2026, 10, 20, 8, 30, tzinfo=ICT)


def test_in_hours_prompt_has_no_after_hours_block(settings):
    routing = Routing(after_hours=False, target="agent")
    spec = build_spec(settings, AgentRuntime(config=CONFIG), now=NIGHT, routing=routing)
    assert "Ngoài giờ làm việc" not in spec.system_instruction


def test_after_hours_prompt_names_next_window(settings):
    routing = Routing(after_hours=True, target="agent", opens_at=NEXT_MORNING, reason="outside_hours")
    spec = build_spec(settings, AgentRuntime(config=CONFIG), now=NIGHT, routing=routing)
    assert "## Ngoài giờ làm việc" in spec.system_instruction
    assert "8 giờ 30 sáng mai" in spec.system_instruction
    assert {t.name for t in spec.tools} == {"check_available_slots", "request_handoff"}


def test_holiday_reason_and_far_date(settings):
    opens = datetime(2027, 2, 11, 8, 0, tzinfo=ICT)
    routing = Routing(after_hours=True, target="agent", opens_at=opens, reason="Tết Nguyên đán")
    spec = build_spec(
        settings, AgentRuntime(config=CONFIG), now=datetime(2027, 2, 6, 9, tzinfo=ICT), routing=routing
    )
    assert "nghỉ: Tết Nguyên đán" in spec.system_instruction
    assert "8 giờ Thứ Năm 11/02" in spec.system_instruction


def test_announcement_route_has_no_tools(settings):
    routing = Routing(
        after_hours=True, target="announcement", announcement="Đã hết giờ.", opens_at=NEXT_MORNING
    )
    spec = build_spec(settings, AgentRuntime(config=CONFIG), now=NIGHT, routing=routing)
    assert spec.tools == []
    assert "Đã hết giờ." in spec.system_instruction and "lời nhắn tự động" in spec.system_instruction
    assert "ghi âm" in spec.system_instruction  # disclosure even for a recorded message


async def test_fetch_routing_and_fallback(wired, monkeypatch):
    def ok(request):
        assert request.url.path.endswith("/internal/routing")
        return httpx.Response(
            200,
            json={
                "after_hours": True,
                "target": "agent",
                "announcement": "x",
                "opens_at": NEXT_MORNING.isoformat(),
                "reason": "outside_hours",
            },
        )

    monkeypatch.setattr(agent_mod.httpx, "AsyncClient", _mock_client(ok))
    got = await fetch_routing(wired)
    assert got.after_hours and got.opens_at == NEXT_MORNING
    monkeypatch.setattr(agent_mod.httpx, "AsyncClient", _mock_client(lambda r: httpx.Response(500)))
    assert await fetch_routing(wired) is None  # unknown -> answered as in hours, never stranded
    assert await fetch_routing(wired.model_copy(update={"gateway_tenant_id": ""})) is None
