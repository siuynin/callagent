import asyncio
import json

from conftest import chunks, silence, tone, write_wav
from fastapi.testclient import TestClient

from gateway.eval_runner import run_scenario
from gateway.providers.mock import MockLiveProvider
from gateway.session import CallSession, build_spec


class ScriptedTransport:
    def __init__(self, frames: list[bytes]):
        self.frames = list(frames)
        self.played: list[bytes] = []
        self.messages: list[dict] = []
        self.cleared = 0

    async def recv_audio(self):
        if not self.frames:
            return None
        await asyncio.sleep(0.04)
        return self.frames.pop(0)

    async def play(self, pcm, rate):
        assert rate == 24000
        self.played.append(pcm)

    async def clear_playback(self):
        self.cleared += 1

    async def notify(self, message):
        self.messages.append(message)


def caller_turn(ms=500):
    return chunks(tone(ms)) + chunks(silence(1500))


def test_spec_contains_vietnamese_rules_and_tools(settings):
    spec = build_spec(settings)
    assert "KHÔNG BAO GIỜ nói" in spec.system_instruction
    assert "Asia/Ho_Chi_Minh" in spec.system_instruction
    assert {t.name for t in spec.tools} == {"check_available_slots", "create_appointment", "request_handoff"}


async def test_two_turns_with_tool_call(settings):
    transport = ScriptedTransport(caller_turn() + caller_turn())
    session = CallSession(MockLiveProvider(), transport, settings, mode="test")
    summary = await session.run()
    kinds = [m["type"] for m in transport.messages]
    assert kinds[0] == "ready" and kinds[-1] == "summary"
    assert "tool_call" in kinds and "tool_result" in kinds
    assert transport.played, "agent audio should be played"
    assert summary["turns_measured"] == 2
    assert summary["tool_calls"] == 1 and summary["false_confirmations"] == 0
    assert summary["latency_ms"]["p50"] is not None
    report = json.loads(open(summary["report_path"], encoding="utf-8").read())
    assert report["summary"]["call_id"] == summary["call_id"]


async def test_barge_in_clears_playback(settings):
    # caller starts talking again 300 ms after finishing, while the mock is still "speaking"
    frames = chunks(tone(500)) + chunks(silence(900)) + chunks(tone(400)) + chunks(silence(1500))
    transport = ScriptedTransport(frames)
    summary = await CallSession(MockLiveProvider(), transport, settings, mode="test").run()
    assert transport.cleared >= 1
    assert summary["interruptions"] >= 1


async def test_phone_sim_path_runs(settings):
    transport = ScriptedTransport(caller_turn())
    summary = await CallSession(MockLiveProvider(), transport, settings, mode="test", phone_sim="alaw").run()
    assert summary["turns_measured"] == 1


def test_websocket_protocol(settings, monkeypatch):
    from gateway import main

    monkeypatch.setattr(main, "get_settings", lambda: settings)
    client = TestClient(main.app)
    info = client.get("/api/info").json()
    assert info["default_provider"] == "mock" and info["providers"] == [{"name": "mock", "model": "mock"}]
    assert "Voice spike" in client.get("/").text
    with client.websocket_connect("/ws/spike?phone_sim=alaw&provider=mock") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready" and ready["phone_sim"] == "alaw"
        for frame in caller_turn():
            ws.send_bytes(frame)
        got_audio = False
        for _ in range(200):
            msg = ws.receive()
            if msg.get("bytes"):
                got_audio = True
            elif msg.get("text") and json.loads(msg["text"])["type"] == "turn_complete":
                break
        assert got_audio
        ws.send_text(json.dumps({"type": "hangup"}))
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] == "summary":
                assert m["summary"]["mode"] == "browser_phone_sim"
                break


async def test_eval_runner_with_mock(settings, tmp_path, monkeypatch):
    import gateway.eval_runner as er

    monkeypatch.setattr(er, "get_settings", lambda: settings)
    write_wav(tmp_path / "t1.wav", tone(600))
    write_wav(tmp_path / "t2.wav", tone(600))
    scenario = {
        "id": "mock-two-turns",
        "turns": [{"audio": "t1.wav"}, {"audio": "t2.wav"}],
        "expect": {
            "tools": [{"name": "check_available_slots"}],
            "tools_absent": ["create_appointment"],
            "max_p95_latency_ms": 3000,
        },
    }
    path = tmp_path / "s.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    result = await run_scenario(path, "mock")
    assert result["passed"], result["checks"]
