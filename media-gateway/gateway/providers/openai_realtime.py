"""OpenAI Realtime adapter (official `openai` SDK, WebSocket). Facts used here are recorded in ADR 0005.

Differences from Gemini that this adapter hides from CallSession:
- Audio is PCM16 24 kHz both ways (the SDK type only allows rate 24000), so caller audio is resampled up.
- Server VAD cancels the in-flight response on barge-in, but over WebSocket the client must truncate the
  assistant item to what was actually heard (`conversation.item.truncate`), otherwise the model believes
  the caller heard the whole answer.
- Function results are conversation items followed by `response.create`; sending `response.create` while a
  response is active is an error, so results are held until `response.done` and all calls are answered.
- `usage` arrives per response and each response re-bills the context: events are marked per_response.
"""

import asyncio
import base64
import json
import logging
import time
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from gateway.audio import duration_ms, resample
from gateway.config import Settings
from gateway.providers.base import (
    AudioOut,
    Event,
    InputTranscript,
    Interrupted,
    OutputTranscript,
    SessionError,
    SessionSpec,
    SpeechEnded,
    SpeechStarted,
    ToolCall,
    ToolResult,
    TurnComplete,
    Usage,
)

log = logging.getLogger("gateway.openai")

RATE = 24000
GREETING_TRIGGER = "Cuộc gọi vừa được kết nối. Hãy chào khách theo câu chào đầu tiên trong hướng dẫn."


def build_session_config(settings: Settings, spec: SessionSpec) -> dict:
    if settings.openai_vad == "semantic_vad":
        turn = {
            "type": "semantic_vad",
            "eagerness": "auto",
            "create_response": True,
            "interrupt_response": True,
        }
    else:
        turn = {
            "type": "server_vad",
            "silence_duration_ms": settings.vad_silence_ms,
            "prefix_padding_ms": settings.vad_prefix_padding_ms,
            "create_response": True,
            "interrupt_response": True,
        }
    return {
        "type": "realtime",
        "instructions": spec.system_instruction,
        "output_modalities": ["audio"],
        "audio": {
            "input": {
                "format": {"type": "audio/pcm", "rate": RATE},
                "transcription": {"model": settings.openai_transcribe_model, "language": "vi"},
                "turn_detection": turn,
            },
            "output": {"format": {"type": "audio/pcm", "rate": RATE}, "voice": settings.openai_voice},
        },
        "tools": [
            {"type": "function", "name": t.name, "description": t.description, "parameters": t.parameters}
            for t in spec.tools
        ],
        "tool_choice": "auto",
    }


def _usage(response) -> Usage | None:
    u = getattr(response, "usage", None)
    if u is None:
        return None
    ind, outd = u.input_token_details, u.output_token_details
    return Usage(
        total_tokens=u.total_tokens or 0,
        prompt_tokens=u.input_tokens or 0,
        response_tokens=u.output_tokens or 0,
        by_modality={
            "prompt": {
                "AUDIO": (ind.audio_tokens or 0) if ind else 0,
                "TEXT": (ind.text_tokens or 0) if ind else 0,
                # subset of AUDIO+TEXT billed at the cached rate; reported, not yet priced (ADR 0005)
                "CACHED": (ind.cached_tokens or 0) if ind else 0,
            },
            "response": {
                "AUDIO": (outd.audio_tokens or 0) if outd else 0,
                "TEXT": (outd.text_tokens or 0) if outd else 0,
            },
        },
        per_response=True,
    )


class OpenAIRealtimeSession:
    output_rate = RATE

    def __init__(self, settings: Settings, spec: SessionSpec, *, client: AsyncOpenAI | None = None):
        self._settings = settings
        self._spec = spec
        self._client = client or AsyncOpenAI(api_key=settings.openai_api_key)
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._manager = None
        self._conn = None
        self._runner: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._closing = False
        # what the caller has heard of the current assistant item (for truncation)
        self._item_id: str | None = None
        self._item_started: float | None = None
        self._item_sent_ms = 0.0
        # tool round-trip coordination
        self._response_active = False
        self._response_has_message = False
        self._pending_calls: set[str] = set()
        self._results: list[ToolResult] = []

    # --- lifecycle ---

    async def start(self, greet: bool = True) -> None:
        self._manager = self._client.realtime.connect(model=self._settings.openai_realtime_model)
        self._conn = await self._manager.__aenter__()
        await self._conn.session.update(session=build_session_config(self._settings, self._spec))
        self._runner = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=15)
        except TimeoutError as exc:
            await self.close()
            raise RuntimeError("Không mở được phiên OpenAI Realtime (kiểm tra model, API key, mạng)") from exc
        if greet:  # inbound receptionist speaks first, like a real switchboard
            await self._conn.conversation.item.create(
                item={
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": GREETING_TRIGGER}],
                }
            )
            await self._conn.response.create()

    async def _run(self) -> None:
        try:
            async for event in self._conn:
                await self.handle(event)
        except Exception as exc:  # noqa: BLE001 - surface to the call instead of hanging
            if not self._closing:
                log.warning("openai realtime connection ended: %s", exc)
                await self._queue.put(SessionError(f"Mất kết nối model: {exc}", fatal=True))
        finally:
            await self._queue.put(None)

    # --- server events ---

    async def handle(self, event) -> None:
        q = self._queue
        t = event.type
        if t in ("session.updated", "session.created"):
            if t == "session.updated":
                self._ready.set()
        elif t == "input_audio_buffer.speech_started":
            await q.put(SpeechStarted())
            await self._maybe_truncate()
        elif t == "input_audio_buffer.speech_stopped":
            await q.put(SpeechEnded())
        elif t == "conversation.item.input_audio_transcription.completed":
            if event.transcript:
                await q.put(InputTranscript(event.transcript))
        elif t == "response.created":
            self._response_active = True
            self._response_has_message = False
        elif t == "response.output_audio.delta":
            data = base64.b64decode(event.delta)
            if event.item_id != self._item_id:
                self._item_id, self._item_started, self._item_sent_ms = event.item_id, time.monotonic(), 0.0
            self._item_sent_ms += duration_ms(data, RATE)
            self._response_has_message = True
            await q.put(AudioOut(data))
        elif t == "response.output_audio_transcript.delta":
            self._response_has_message = True
            if event.delta:
                await q.put(OutputTranscript(event.delta))
        elif t == "response.function_call_arguments.done":
            try:
                args = json.loads(event.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": event.arguments}
            self._pending_calls.add(event.call_id)
            await q.put(ToolCall(call_id=event.call_id, name=event.name, args=args))
        elif t == "response.done":
            self._response_active = False
            usage = _usage(event.response)
            if usage:
                await q.put(usage)
            if self._response_has_message:
                await q.put(TurnComplete())
            await self._maybe_continue()
        elif t == "error":
            err = getattr(event, "error", None)
            message = getattr(err, "message", None) or str(err)
            log.warning("openai realtime error: %s", message)
            await q.put(SessionError(f"OpenAI: {message}", fatal=False))

    async def _maybe_truncate(self) -> None:
        """Caller started talking: cut the assistant item at the point they actually heard."""
        if not self._item_id or self._item_started is None:
            return
        heard = (time.monotonic() - self._item_started) * 1000
        if heard < self._item_sent_ms - 50:  # audio still queued at the caller's side
            await self._conn.conversation.item.truncate(
                item_id=self._item_id, content_index=0, audio_end_ms=max(0, int(heard))
            )
            await self._queue.put(Interrupted())
        self._item_id = None

    async def _maybe_continue(self) -> None:
        if self._response_active or self._pending_calls or not self._results:
            return
        results, self._results = self._results, []
        for r in results:
            await self._conn.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": r.call_id,
                    "output": json.dumps(r.response, ensure_ascii=False),
                }
            )
        await self._conn.response.create()

    # --- client io ---

    async def send_audio(self, pcm16_16k: bytes) -> None:
        if self._conn is None or not self._ready.is_set():
            return
        audio = base64.b64encode(resample(pcm16_16k, 16000, RATE)).decode("ascii")
        await self._conn.input_audio_buffer.append(audio=audio)

    async def send_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self._pending_calls.discard(r.call_id)
        self._results.extend(results)
        await self._maybe_continue()

    async def events(self) -> AsyncIterator[Event]:
        while True:
            ev = await self._queue.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        self._closing = True
        if self._manager is not None:
            try:
                await self._manager.__aexit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass
        if self._runner is not None:
            try:
                await asyncio.wait_for(self._runner, timeout=3)
            except (TimeoutError, asyncio.CancelledError):
                self._runner.cancel()


class OpenAIRealtimeProvider:
    name = "openai"

    def __init__(self, settings: Settings):
        self._settings = settings
        self.model = settings.openai_realtime_model

    async def open(self, spec: SessionSpec) -> OpenAIRealtimeSession:
        session = OpenAIRealtimeSession(self._settings, spec)
        await session.start()
        return session
