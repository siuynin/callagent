"""Gemini Live adapter (google-genai SDK). Facts used here are recorded in docs/adr/0003.

- Audio in: PCM16 16 kHz (`audio/pcm;rate=16000`); audio out: PCM16 24 kHz.
- Model VAD decides turns; `server_content.interrupted` means stop playback and drop queued audio.
- Connections live ~10 min: we keep the latest resumption handle and reconnect on `go_away` or on an
  unexpected close, buffering a little caller audio meanwhile. Context window compression is enabled so
  long calls are not cut at the audio session limit.
"""

import asyncio
import logging
from collections import deque
from collections.abc import AsyncIterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from gateway.config import Settings
from gateway.providers.base import (
    AudioOut,
    Event,
    InputTranscript,
    Interrupted,
    OutputTranscript,
    Reconnected,
    SessionError,
    SessionSpec,
    SpeechEnded,
    SpeechStarted,
    ToolCall,
    ToolCallCancelled,
    ToolResult,
    TurnComplete,
    Usage,
)

log = logging.getLogger("gateway.gemini")

MAX_RECONNECTS = 3
BUFFER_LIMIT_BYTES = 16000 * 2 * 2  # keep at most ~2 s of caller audio while reconnecting


def _modality_counts(details) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in details or []:
        key = getattr(d.modality, "name", str(d.modality))
        out[key] = out.get(key, 0) + (d.token_count or 0)
    return out


class GeminiLiveSession:
    output_rate = 24000

    def __init__(self, settings: Settings, spec: SessionSpec):
        self._settings = settings
        self._spec = spec
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue()
        self._session = None
        self._ready = asyncio.Event()
        self._handle: str | None = None
        self._closing = False
        self._reconnect_reason: str | None = None
        self._pending_audio: deque[bytes] = deque()
        self._pending_bytes = 0
        self._runner: asyncio.Task | None = None

    # --- config ---

    def _config(self) -> types.LiveConnectConfig:
        s = self._settings
        tools = None
        if self._spec.tools:
            tools = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t.name, description=t.description, parameters_json_schema=t.parameters
                        )
                        for t in self._spec.tools
                    ]
                )
            ]
        speech = None
        if s.ai_voice:
            speech = types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=s.ai_voice)
                )
            )
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(parts=[types.Part(text=self._spec.system_instruction)]),
            tools=tools,
            speech_config=speech,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    silence_duration_ms=s.vad_silence_ms,
                    prefix_padding_ms=s.vad_prefix_padding_ms,
                )
            ),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            session_resumption=types.SessionResumptionConfig(handle=self._handle),
        )

    # --- lifecycle ---

    async def start(self) -> None:
        self._runner = asyncio.create_task(self._run())
        ready = asyncio.create_task(self._ready.wait())
        done, _ = await asyncio.wait({ready, self._runner}, timeout=15, return_when=asyncio.FIRST_COMPLETED)
        if ready not in done:
            ready.cancel()
            await self.close()
            raise RuntimeError("Không mở được phiên Gemini Live (kiểm tra model, API key, mạng)")

    async def _run(self) -> None:
        attempts = 0
        while not self._closing:
            try:
                async with self._client.aio.live.connect(
                    model=self._settings.ai_model, config=self._config()
                ) as session:
                    self._session = session
                    self._ready.set()
                    if attempts:
                        await self._queue.put(Reconnected(self._reconnect_reason or "connection_lost"))
                    attempts = 0
                    self._reconnect_reason = None
                    await self._flush_pending()
                    while True:
                        async for msg in session.receive():
                            await self._handle_message(msg)
            except (TimeoutError, genai_errors.APIError, OSError) as exc:
                self._session = None
                self._ready.clear()
                if self._closing:
                    break
                attempts += 1
                can_resume = self._handle is not None and attempts <= MAX_RECONNECTS
                log.warning("live connection ended (%s), resume=%s", exc, can_resume)
                if not can_resume:
                    await self._queue.put(SessionError(f"Mất kết nối model: {exc}", fatal=True))
                    break
                await asyncio.sleep(0.2 * attempts)
            except Exception as exc:  # noqa: BLE001 - surface anything unexpected to the call
                log.exception("live session crashed")
                await self._queue.put(SessionError(f"Lỗi phiên model: {exc}", fatal=True))
                break
        await self._queue.put(None)

    async def _handle_message(self, msg: types.LiveServerMessage) -> None:
        q = self._queue
        if msg.session_resumption_update and msg.session_resumption_update.resumable:
            self._handle = msg.session_resumption_update.new_handle or self._handle
        if msg.go_away is not None:
            log.info("go_away received, time_left=%s", msg.go_away.time_left)
            self._reconnect_reason = "go_away"
            if self._session is not None:
                await self._session.close()  # receive() raises; _run reconnects with the handle
            return
        va = msg.voice_activity
        if va is not None and va.voice_activity_type is not None:
            name = va.voice_activity_type.name
            await q.put(SpeechStarted() if name == "ACTIVITY_START" else SpeechEnded())
        sig = msg.voice_activity_detection_signal
        if sig is not None and sig.vad_signal_type is not None:
            name = sig.vad_signal_type.name
            if name.endswith("SOS"):
                await q.put(SpeechStarted())
            elif name.endswith("EOS"):
                await q.put(SpeechEnded())
        sc = msg.server_content
        if sc is not None:
            if sc.interrupted:
                await q.put(Interrupted())
            if sc.input_transcription and sc.input_transcription.text:
                await q.put(InputTranscript(sc.input_transcription.text))
            if sc.model_turn and sc.model_turn.parts:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        await q.put(AudioOut(part.inline_data.data))
            if sc.output_transcription and sc.output_transcription.text:
                await q.put(OutputTranscript(sc.output_transcription.text))
            if sc.turn_complete:
                await q.put(TurnComplete())
        if msg.tool_call and msg.tool_call.function_calls:
            for fc in msg.tool_call.function_calls:
                await q.put(ToolCall(call_id=fc.id or "", name=fc.name or "", args=dict(fc.args or {})))
        if msg.tool_call_cancellation and msg.tool_call_cancellation.ids:
            await q.put(ToolCallCancelled(list(msg.tool_call_cancellation.ids)))
        um = msg.usage_metadata
        if um is not None:
            await q.put(
                Usage(
                    total_tokens=um.total_token_count or 0,
                    prompt_tokens=um.prompt_token_count or 0,
                    response_tokens=um.response_token_count or 0,
                    by_modality={
                        "prompt": _modality_counts(um.prompt_tokens_details),
                        "response": _modality_counts(um.response_tokens_details),
                    },
                )
            )

    # --- io ---

    async def _flush_pending(self) -> None:
        while self._pending_audio and self._session is not None:
            chunk = self._pending_audio.popleft()
            self._pending_bytes -= len(chunk)
            await self._send(chunk)

    async def _send(self, chunk: bytes) -> None:
        await self._session.send_realtime_input(
            audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
        )

    async def send_audio(self, pcm16_16k: bytes) -> None:
        if self._session is None or not self._ready.is_set():
            self._pending_audio.append(pcm16_16k)
            self._pending_bytes += len(pcm16_16k)
            while self._pending_bytes > BUFFER_LIMIT_BYTES:
                self._pending_bytes -= len(self._pending_audio.popleft())
            return
        try:
            await self._send(pcm16_16k)
        except (genai_errors.APIError, OSError) as exc:
            log.debug("send failed during reconnect: %s", exc)

    async def send_tool_results(self, results: list[ToolResult]) -> None:
        if self._session is None:
            return  # calls are cancelled by the server on reconnect; the model asks again
        await self._session.send_tool_response(
            function_responses=[
                types.FunctionResponse(id=r.call_id, name=r.name, response=r.response) for r in results
            ]
        )

    async def events(self) -> AsyncIterator[Event]:
        while True:
            ev = await self._queue.get()
            if ev is None:
                return
            yield ev

    async def close(self) -> None:
        self._closing = True
        if self._session is not None:
            try:
                await self._session.close()
            except Exception:  # noqa: BLE001
                pass
        if self._runner is not None:
            try:
                await asyncio.wait_for(self._runner, timeout=3)
            except (TimeoutError, asyncio.CancelledError):
                self._runner.cancel()


class GeminiLiveProvider:
    name = "gemini"

    def __init__(self, settings: Settings):
        self._settings = settings

    async def open(self, spec: SessionSpec) -> GeminiLiveSession:
        session = GeminiLiveSession(self._settings, spec)
        await session.start()
        return session
