"""OpenAI Realtime adapter: config shape and event handling, using the SDK's own types (no network)."""

import asyncio
import base64
import time

import pytest
from conftest import tone
from openai.types import realtime as rt

from gateway.metrics import CallRecorder
from gateway.providers import make_provider
from gateway.providers.base import (
    AudioOut,
    InputTranscript,
    Interrupted,
    OutputTranscript,
    SpeechEnded,
    SpeechStarted,
    ToolCall,
    ToolResult,
    TurnComplete,
    Usage,
)
from gateway.providers.openai_realtime import OpenAIRealtimeSession, build_session_config
from gateway.session import build_spec


class _Recorder:
    def __init__(self, log, prefix):
        self._log, self._prefix = log, prefix

    def __getattr__(self, name):
        async def call(**kwargs):
            self._log.append((f"{self._prefix}.{name}", kwargs))

        return call


class FakeConn:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.conversation = type("C", (), {})()
        self.conversation.item = _Recorder(self.sent, "conversation.item")
        self.response = _Recorder(self.sent, "response")
        self.input_audio_buffer = _Recorder(self.sent, "input_audio_buffer")
        self.session = _Recorder(self.sent, "session")


def make(settings):
    s = settings.model_copy(update={"openai_api_key": "sk-test-not-used"})
    sess = OpenAIRealtimeSession(s, build_spec(s), client=object())
    sess._conn = FakeConn()
    sess._ready.set()
    return sess


async def run(sess, event) -> list:
    await sess.handle(event)
    out = []
    while not sess._queue.empty():
        out.append(sess._queue.get_nowait())
    return out


def ev(model, **fields):
    return model.model_validate({"event_id": "e1", **fields})


def audio_delta(ms: int, item="item_1"):
    pcm = b"\x00\x00" * int(24000 * ms / 1000)
    return ev(
        rt.ResponseAudioDeltaEvent,
        type="response.output_audio.delta",
        delta=base64.b64encode(pcm).decode(),
        item_id=item,
        output_index=0,
        content_index=0,
        response_id="r1",
    )


def done(output_tokens=40):
    usage = {
        "total_tokens": 100 + output_tokens,
        "input_tokens": 100,
        "output_tokens": output_tokens,
        "input_token_details": {"audio_tokens": 80, "text_tokens": 20, "cached_tokens": 64},
        "output_token_details": {"audio_tokens": output_tokens, "text_tokens": 0},
    }
    return ev(
        rt.ResponseDoneEvent,
        type="response.done",
        response={"id": "r1", "status": "completed", "usage": usage},
    )


def created():
    return ev(
        rt.ResponseCreatedEvent, type="response.created", response={"id": "r1", "status": "in_progress"}
    )


def fn_done(call_id, name="check_available_slots", args='{"date": "2026-10-20"}'):
    return ev(
        rt.ResponseFunctionCallArgumentsDoneEvent,
        type="response.function_call_arguments.done",
        arguments=args,
        call_id=call_id,
        name=name,
        item_id=f"fc_{call_id}",
        output_index=0,
        response_id="r1",
    )


def test_session_config_is_valid_for_sdk(settings):
    cfg = build_session_config(settings, build_spec(settings))
    model = rt.RealtimeSessionCreateRequest.model_validate(cfg)  # raises if a field name/shape is wrong
    assert model.audio.input.format.rate == 24000
    assert model.audio.input.transcription.language == "vi"
    assert model.audio.input.turn_detection.type == "server_vad"
    assert model.audio.input.turn_detection.interrupt_response is True
    assert {t.name for t in model.tools} == {"check_available_slots", "create_appointment", "request_handoff"}
    semantic = settings.model_copy(update={"openai_vad": "semantic_vad"})
    assert (
        build_session_config(semantic, build_spec(semantic))["audio"]["input"]["turn_detection"]["type"]
        == "semantic_vad"
    )


async def test_basic_event_mapping(settings):
    s = make(settings)
    assert [
        type(e)
        for e in await run(
            s,
            ev(
                rt.InputAudioBufferSpeechStartedEvent,
                type="input_audio_buffer.speech_started",
                audio_start_ms=0,
                item_id="u1",
            ),
        )
    ] == [SpeechStarted]
    assert [
        type(e)
        for e in await run(
            s,
            ev(
                rt.InputAudioBufferSpeechStoppedEvent,
                type="input_audio_buffer.speech_stopped",
                audio_end_ms=900,
                item_id="u1",
            ),
        )
    ] == [SpeechEnded]
    (tr,) = await run(
        s,
        ev(
            rt.ConversationItemInputAudioTranscriptionCompletedEvent,
            type="conversation.item.input_audio_transcription.completed",
            item_id="u1",
            content_index=0,
            transcript="cho em hỏi giá xe",
            usage={"type": "duration", "seconds": 1.2},
        ),
    )
    assert isinstance(tr, InputTranscript) and tr.text == "cho em hỏi giá xe"
    await run(s, created())
    (a,) = await run(s, audio_delta(100))
    assert isinstance(a, AudioOut) and len(a.data) == 24000 * 2 // 10
    (o,) = await run(
        s,
        ev(
            rt.ResponseAudioTranscriptDeltaEvent,
            type="response.output_audio_transcript.delta",
            delta="Dạ",
            item_id="item_1",
            output_index=0,
            content_index=0,
            response_id="r1",
        ),
    )
    assert isinstance(o, OutputTranscript)
    out = await run(s, done())
    assert [type(e) for e in out] == [Usage, TurnComplete]
    assert out[0].per_response and out[0].by_modality["prompt"]["AUDIO"] == 80
    assert out[0].by_modality["prompt"]["CACHED"] == 64


async def test_function_only_response_is_not_a_turn(settings):
    s = make(settings)
    await run(s, created())
    (call,) = await run(s, fn_done("c1"))
    assert isinstance(call, ToolCall) and call.args == {"date": "2026-10-20"}
    out = await run(s, done(output_tokens=5))
    assert TurnComplete not in [type(e) for e in out]  # no audio yet: the agent has not answered


async def test_tool_results_wait_for_response_done_and_all_calls(settings):
    s = make(settings)
    await run(s, created())
    await run(s, fn_done("c1"))
    await run(s, fn_done("c2", name="request_handoff", args='{"reason": "x", "summary": "y"}'))
    await s.send_tool_results([ToolResult("c1", "check_available_slots", {"status": "ok"})])
    assert s._conn.sent == []  # response still active
    await run(s, done())
    assert s._conn.sent == []  # c2 still pending
    await s.send_tool_results([ToolResult("c2", "request_handoff", {"status": "ok"})])
    kinds = [k for k, _ in s._conn.sent]
    assert kinds == ["conversation.item.create", "conversation.item.create", "response.create"]
    item = s._conn.sent[0][1]["item"]
    assert item["type"] == "function_call_output" and item["call_id"] == "c1"


async def test_barge_in_truncates_to_heard_audio(settings):
    s = make(settings)
    await run(s, created())
    await run(s, audio_delta(2000))
    await asyncio.sleep(0.15)
    out = await run(
        s,
        ev(
            rt.InputAudioBufferSpeechStartedEvent,
            type="input_audio_buffer.speech_started",
            audio_start_ms=0,
            item_id="u2",
        ),
    )
    assert [type(e) for e in out] == [SpeechStarted, Interrupted]
    name, kwargs = s._conn.sent[-1]
    assert name == "conversation.item.truncate" and kwargs["item_id"] == "item_1"
    assert 100 <= kwargs["audio_end_ms"] < 1000


async def test_no_truncate_after_playback_finished(settings):
    s = make(settings)
    await run(s, audio_delta(100))
    s._item_started = time.monotonic() - 1.0  # caller already heard all 100 ms
    out = await run(
        s,
        ev(
            rt.InputAudioBufferSpeechStartedEvent,
            type="input_audio_buffer.speech_started",
            audio_start_ms=0,
            item_id="u2",
        ),
    )
    assert [type(e) for e in out] == [SpeechStarted]
    assert s._conn.sent == []


async def test_audio_is_resampled_to_24k(settings):
    s = make(settings)
    await s.send_audio(tone(100))  # 100 ms @ 16 kHz
    name, kwargs = s._conn.sent[0]
    assert name == "input_audio_buffer.append"
    assert len(base64.b64decode(kwargs["audio"])) == 2400 * 2


def test_per_response_usage_is_summed(settings):
    priced = settings.model_copy(
        update={
            "openai_price_audio_in_per_mtok": 10.0,
            "openai_price_audio_out_per_mtok": 20.0,
            "openai_price_text_in_per_mtok": 1.0,
            "openai_price_text_out_per_mtok": 2.0,
        }
    )
    rec = CallRecorder(settings=priced, mode="test", provider="openai", model="gpt-realtime-2.1")
    for _ in range(3):  # context re-billed on each response
        rec.on_usage(140, 100, 40, {"prompt": {"AUDIO": 80, "TEXT": 20}, "response": {"AUDIO": 40}}, True)
    totals = rec.usage_totals()
    assert totals["prompt"] == 300 and totals["responses"] == 3
    cost = rec.summary()["cost_estimate"]
    assert cost["usd_total"] == round((240 * 10 + 60 * 1 + 120 * 20) / 1e6, 6)
    assert rec.summary()["provider"] == "openai"


def test_provider_selection_requires_keys(settings):
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        make_provider(settings, "openai")
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        make_provider(settings, "gemini")
    with pytest.raises(ValueError):
        make_provider(settings, "other")
    keyed = settings.model_copy(update={"openai_api_key": "sk-x"})
    assert keyed.available_providers() == ["mock", "openai"]
    assert make_provider(keyed, "openai").model == "gpt-realtime-2.1"
