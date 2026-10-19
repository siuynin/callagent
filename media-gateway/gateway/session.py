"""Call orchestration: transport <-> live model, tools and measurements.

A transport is anything that delivers caller audio and plays agent audio: the browser WebSocket in the
spike, a WAV file in the eval runner, a SIP/RTP leg later (ADR 0004). One CallSession per call; no
state is shared between calls (plan/docs/02 Isolation).
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo

from gateway.audio import phone_channel_sim
from gateway.config import ROOT, Settings
from gateway.metrics import CallRecorder
from gateway.providers.base import (
    AudioOut,
    InputTranscript,
    Interrupted,
    LiveProvider,
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
from gateway.tools import TOOL_SPECS, Toolbox

log = logging.getLogger("gateway.session")

TOOL_TIMEOUT_S = 5.0
WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]


class Transport(Protocol):
    async def recv_audio(self) -> bytes | None: ...  # PCM16 16 kHz, None = caller hung up

    async def play(self, pcm: bytes, rate: int) -> None: ...

    async def clear_playback(self) -> None: ...

    async def notify(self, message: dict) -> None: ...


def build_spec(settings: Settings, now: datetime | None = None) -> SessionSpec:
    tz = ZoneInfo(settings.default_timezone)
    now = now or datetime.now(tz)
    template = Path(ROOT / "agents" / "receptionist.vi.md").read_text(encoding="utf-8")
    prompt = template.format(
        business_name=settings.business_name,
        today=now.strftime("%d/%m/%Y"),
        weekday=WEEKDAYS_VI[now.weekday()],
        now_time=now.strftime("%H:%M"),
        timezone=settings.default_timezone,
    )
    return SessionSpec(system_instruction=prompt, tools=TOOL_SPECS)


class CallSession:
    def __init__(
        self,
        provider: LiveProvider,
        transport: Transport,
        settings: Settings,
        *,
        mode: str = "browser",
        phone_sim: str | None = None,
        toolbox: Toolbox | None = None,
    ):
        self.provider = provider
        self.transport = transport
        self.settings = settings
        self.phone_sim = phone_sim
        self.toolbox = toolbox or Toolbox(tz=ZoneInfo(settings.default_timezone))
        self.recorder = CallRecorder(
            settings=settings, mode=mode, provider=provider.name, model=getattr(provider, "model", "mock")
        )
        self._cancelled_tools: set[str] = set()
        self.turn_complete = asyncio.Event()

    async def run(self) -> dict:
        live = await self.provider.open(build_spec(self.settings))
        self.recorder.log("session_open", provider=self.provider.name)
        await self.transport.notify(
            {
                "type": "ready",
                "call_id": self.recorder.call_id,
                "provider": self.provider.name,
                "model": self.recorder.model,
                "phone_sim": self.phone_sim,
            }
        )
        pump_in = asyncio.create_task(self._pump_in(live))
        pump_out = asyncio.create_task(self._pump_out(live))
        try:
            done, _ = await asyncio.wait({pump_in, pump_out}, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                if task.exception():
                    log.error("call task failed: %r", task.exception())
        finally:
            for task in (pump_in, pump_out):
                task.cancel()
            await live.close()
            self.recorder.log("session_closed")
        summary = self.recorder.summary()
        path = self.recorder.write()
        summary["report_path"] = str(path)
        await self._safe_notify({"type": "summary", "summary": summary})
        return summary

    async def _safe_notify(self, message: dict) -> None:
        try:
            await self.transport.notify(message)
        except Exception:  # noqa: BLE001 - transport may already be gone
            pass

    async def _pump_in(self, live) -> None:
        while True:
            chunk = await self.transport.recv_audio()
            if chunk is None:
                return
            if self.phone_sim:
                chunk = phone_channel_sim(chunk, self.phone_sim)
            self.recorder.on_caller_audio(chunk)
            await live.send_audio(chunk)

    async def _pump_out(self, live) -> None:
        rec = self.recorder
        async for ev in live.events():
            match ev:
                case AudioOut(data=data):
                    rec.on_agent_audio()
                    await self.transport.play(data, live.output_rate)
                case Interrupted():
                    rec.on_interrupted()
                    await self.transport.clear_playback()
                    await self.transport.notify({"type": "interrupted"})
                case SpeechStarted():
                    rec.log("provider_speech_start")
                case SpeechEnded():
                    rec.on_speech_ended()
                case InputTranscript(text=text):
                    rec.on_input_transcript(text)
                    await self.transport.notify({"type": "transcript", "role": "caller", "text": text})
                case OutputTranscript(text=text):
                    rec.on_output_transcript(text)
                    await self.transport.notify({"type": "transcript", "role": "agent", "text": text})
                case ToolCall():
                    asyncio.create_task(self._run_tool(live, ev))
                case ToolCallCancelled(call_ids=ids):
                    self._cancelled_tools.update(ids)
                    rec.log("tool_cancelled", ids=ids)
                case TurnComplete():
                    rec.on_turn_complete()
                    self.turn_complete.set()
                    await self.transport.notify(
                        {"type": "turn_complete", "latency_ms": rec.latencies_ms[-1:]}
                    )
                case Usage():
                    rec.on_usage(
                        ev.total_tokens, ev.prompt_tokens, ev.response_tokens, ev.by_modality, ev.per_response
                    )
                case Reconnected(reason=reason):
                    rec.log("reconnected", reason=reason)
                    await self.transport.notify({"type": "reconnected", "reason": reason})
                case SessionError(message=message, fatal=fatal):
                    rec.log("session_error", message=message)
                    await self.transport.notify({"type": "error", "message": message})
                    if fatal:
                        return

    async def _run_tool(self, live, call: ToolCall) -> None:
        self.recorder.on_tool_call(call.call_id, call.name, call.args)
        await self.transport.notify({"type": "tool_call", "name": call.name, "args": call.args})
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.toolbox.execute, call.name, call.args), TOOL_TIMEOUT_S
            )
        except TimeoutError:
            result = {"status": "timeout", "message": "Hệ thống chưa phản hồi, chưa thực hiện được"}
        self.recorder.on_tool_result(call.call_id, call.name, result)
        await self.transport.notify({"type": "tool_result", "name": call.name, "result": result})
        if call.call_id in self._cancelled_tools:
            return  # the model already moved on (barge-in); do not resend
        await live.send_tool_results([ToolResult(call.call_id, call.name, result)])
