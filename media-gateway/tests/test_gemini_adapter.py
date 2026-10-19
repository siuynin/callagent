"""Message mapping of the Gemini adapter, using SDK types only (no network)."""

from google.genai import types

from gateway.providers.base import (
    AudioOut,
    InputTranscript,
    Interrupted,
    OutputTranscript,
    SpeechEnded,
    ToolCall,
    ToolCallCancelled,
    TurnComplete,
    Usage,
)
from gateway.providers.gemini import GeminiLiveSession
from gateway.session import build_spec


def make_session(settings):
    s = settings.model_copy(update={"ai_provider": "gemini", "gemini_api_key": "test-key-not-used"})
    return GeminiLiveSession(s, build_spec(s))


async def drain(session, msg) -> list:
    await session._handle_message(msg)
    out = []
    while not session._queue.empty():
        out.append(session._queue.get_nowait())
    return out


def test_config_matches_adr(settings):
    cfg = make_session(settings)._config()
    assert cfg.response_modalities == [types.Modality.AUDIO]
    assert cfg.input_audio_transcription is not None and cfg.output_audio_transcription is not None
    assert cfg.context_window_compression.sliding_window is not None
    assert cfg.realtime_input_config.automatic_activity_detection.silence_duration_ms == 600
    names = {f.name for f in cfg.tools[0].function_declarations}
    assert names == {"check_available_slots", "create_appointment", "request_handoff"}
    assert cfg.speech_config is None  # provider default voice unless AI_VOICE is set


async def test_server_content_mapping(settings):
    s = make_session(settings)
    msg = types.LiveServerMessage(
        server_content=types.LiveServerContent(
            model_turn=types.Content(
                parts=[types.Part(inline_data=types.Blob(data=b"\x01\x00", mime_type="audio/pcm"))]
            ),
            input_transcription=types.Transcription(text="cho em hỏi"),
            output_transcription=types.Transcription(text="Dạ"),
            turn_complete=True,
        )
    )
    evs = await drain(s, msg)
    assert [type(e) for e in evs] == [InputTranscript, AudioOut, OutputTranscript, TurnComplete]
    assert evs[1].data == b"\x01\x00"


async def test_interrupt_tool_usage_and_vad(settings):
    s = make_session(settings)
    evs = await drain(s, types.LiveServerMessage(server_content=types.LiveServerContent(interrupted=True)))
    assert isinstance(evs[0], Interrupted)

    call = types.LiveServerMessage(
        tool_call=types.LiveServerToolCall(
            function_calls=[
                types.FunctionCall(id="c1", name="check_available_slots", args={"date": "2026-10-20"})
            ]
        )
    )
    (tc,) = await drain(s, call)
    assert isinstance(tc, ToolCall) and tc.args == {"date": "2026-10-20"}

    (cancel,) = await drain(
        s, types.LiveServerMessage(tool_call_cancellation=types.LiveServerToolCallCancellation(ids=["c1"]))
    )
    assert isinstance(cancel, ToolCallCancelled) and cancel.call_ids == ["c1"]

    usage = types.LiveServerMessage(
        usage_metadata=types.UsageMetadata(
            total_token_count=30,
            prompt_token_count=20,
            response_token_count=10,
            response_tokens_details=[
                types.ModalityTokenCount(modality=types.MediaModality.AUDIO, token_count=10)
            ],
        )
    )
    (u,) = await drain(s, usage)
    assert isinstance(u, Usage) and u.by_modality["response"] == {"AUDIO": 10}

    (eos,) = await drain(
        s,
        types.LiveServerMessage(
            voice_activity=types.VoiceActivity(voice_activity_type=types.VoiceActivityType.ACTIVITY_END)
        ),
    )
    assert isinstance(eos, SpeechEnded)


async def test_resumption_handle_kept(settings):
    s = make_session(settings)
    await drain(
        s,
        types.LiveServerMessage(
            session_resumption_update=types.LiveServerSessionResumptionUpdate(new_handle="h1", resumable=True)
        ),
    )
    assert s._handle == "h1"
    assert s._config().session_resumption.handle == "h1"
    await drain(
        s,
        types.LiveServerMessage(
            session_resumption_update=types.LiveServerSessionResumptionUpdate(
                new_handle="h2", resumable=False
            )
        ),
    )
    assert s._handle == "h1"  # non-resumable points are ignored


async def test_audio_buffered_while_disconnected(settings):
    s = make_session(settings)
    for _ in range(100):
        await s.send_audio(b"\x00" * 1280)
    assert s._pending_bytes <= 16000 * 2 * 2  # bounded, oldest dropped
