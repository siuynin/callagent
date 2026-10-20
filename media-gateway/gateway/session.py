"""Call orchestration: transport <-> live model, tools and measurements.

A transport is anything that delivers caller audio and plays agent audio: the browser WebSocket in the
spike, a WAV file in the eval runner, a SIP/RTP leg later (ADR 0004). One CallSession per call; no
state is shared between calls (plan/docs/02 Isolation).
"""

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from gateway.agent import AgentRuntime, Routing, build_spec, file_agent
from gateway.audio import phone_channel_sim
from gateway.backend import BackendSink
from gateway.config import Settings
from gateway.metrics import CallRecorder
from gateway.providers.base import (
    AudioOut,
    InputTranscript,
    Interrupted,
    LiveProvider,
    OutputTranscript,
    Reconnected,
    SessionError,
    SpeechEnded,
    SpeechStarted,
    ToolCall,
    ToolCallCancelled,
    ToolResult,
    TurnComplete,
    Usage,
)
from gateway.tools import Toolbox

log = logging.getLogger("gateway.session")

TOOL_TIMEOUT_S = 5.0


class Transport(Protocol):
    async def recv_audio(self) -> bytes | None: ...  # PCM16 16 kHz, None = caller hung up

    async def play(self, pcm: bytes, rate: int) -> None: ...

    async def clear_playback(self) -> None: ...

    async def notify(self, message: dict) -> None: ...


class TurnAssembler:
    """Turns provider transcript fragments into stored call turns.

    Each turn keeps the time its speaker STARTED, not when the text arrived: OpenAI delivers the caller's
    transcript after the agent has already started answering, and arrival order would put it after the reply.
    """

    def __init__(self, sink: BackendSink, clock: Callable[[], int]):
        self.sink, self.clock = sink, clock
        self.caller_text, self.caller_start, self.caller_speech_start = "", None, None
        self.agent_text, self.agent_start = "", None

    @staticmethod
    def _join(a: str, b: str) -> str:
        if a and b and not a.endswith(" ") and not b.startswith(" ") and a[-1] in ".?!,;:":
            return f"{a} {b}"
        return a + b

    def speech_started(self) -> None:
        self.flush_caller()
        self.caller_speech_start = self.clock()

    def caller(self, text: str) -> None:
        if self.caller_start is None:
            self.caller_start = (
                self.caller_speech_start if self.caller_speech_start is not None else self.clock()
            )
        self.caller_text = self._join(self.caller_text, text)

    def agent_audio(self) -> None:
        if self.agent_start is None:
            self.agent_start = self.clock()

    def agent(self, text: str) -> None:
        self.agent_audio()
        self.agent_text = self._join(self.agent_text, text)

    def flush_caller(self) -> None:
        if self.caller_text.strip():
            self.sink.add_turn("customer", self.caller_text, self.caller_start or 0)
            self.caller_text, self.caller_start, self.caller_speech_start = "", None, None

    def flush_agent(self) -> None:
        if self.agent_text.strip():
            self.sink.add_turn("agent", self.agent_text, self.agent_start or 0)
        self.agent_text, self.agent_start = "", None

    def turn_complete(self) -> None:
        self.flush_caller()  # keeps caller_speech_start when the caller transcript has not arrived yet
        self.flush_agent()

    def close(self) -> None:
        self.flush_caller()
        self.flush_agent()


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
        persist: bool = False,
        caller_number: str | None = None,
        agent: AgentRuntime | None = None,
        routing: Routing | None = None,
    ):
        self.provider = provider
        self.transport = transport
        self.settings = settings
        self.phone_sim = phone_sim
        self.toolbox = toolbox or Toolbox(tz=ZoneInfo(settings.default_timezone))
        self.agent = agent or file_agent(settings)
        self.routing = routing
        self.recorder = CallRecorder(
            settings=settings, mode=mode, provider=provider.name, model=getattr(provider, "model", "mock")
        )
        self._cancelled_tools: set[str] = set()
        self.turn_complete = asyncio.Event()
        # persistence is opt-in per call (browser spike: on; eval/smoke: off) and needs ADR 0006 config
        self.sink = BackendSink(
            settings=settings,
            provider=f"gateway-{provider.name}"[:32],
            provider_call_id=f"{mode}-{self.recorder.call_id}",
        )
        self.persist = persist and self.sink.enabled
        self.caller_number = caller_number
        self.turns = TurnAssembler(self.sink, lambda: int(self.recorder.now_ms()))
        self._booked = False
        self._handoff = False

    async def run(self) -> dict:
        if self.persist:
            self.sink.start(datetime.now(UTC), self.caller_number, self.agent.version_id)
        live = await self.provider.open(build_spec(self.settings, self.agent, routing=self.routing))
        self.recorder.log(
            "session_open",
            provider=self.provider.name,
            agent_source=self.agent.source,
            agent_version=self.agent.number,
        )
        await self.transport.notify(
            {
                "type": "ready",
                "call_id": self.recorder.call_id,
                "provider": self.provider.name,
                "model": self.recorder.model,
                "phone_sim": self.phone_sim,
                "persist": self.persist,
                "agent_version": self.agent.number,
                "agent_source": self.agent.source,
                "after_hours": bool(self.routing and self.routing.after_hours),
                "route_target": self.routing.target if self.routing else "agent",
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
        persistence = {"enabled": False}
        if self.persist:
            self.turns.close()
            outcome = "booked" if self._booked else "handoff" if self._handoff else None
            persistence = await self.sink.close(outcome=outcome)
        summary = self.recorder.summary()
        summary["persistence"] = persistence
        summary["routing"] = {
            "known": self.routing is not None,
            "after_hours": bool(self.routing and self.routing.after_hours),
            "target": self.routing.target if self.routing else "agent",
        }
        summary["agent"] = {
            "source": self.agent.source,
            "version": self.agent.number,
            "version_id": self.agent.version_id,
        }
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
                    self.turns.agent_audio()
                    await self.transport.play(data, live.output_rate)
                case Interrupted():
                    rec.on_interrupted()
                    self.turns.flush_agent()
                    await self.transport.clear_playback()
                    await self.transport.notify({"type": "interrupted"})
                case SpeechStarted():
                    rec.log("provider_speech_start")
                    self.turns.speech_started()
                case SpeechEnded():
                    rec.on_speech_ended()
                case InputTranscript(text=text):
                    rec.on_input_transcript(text)
                    self.turns.caller(text)
                    await self.transport.notify({"type": "transcript", "role": "caller", "text": text})
                case OutputTranscript(text=text):
                    rec.on_output_transcript(text)
                    self.turns.agent(text)
                    await self.transport.notify({"type": "transcript", "role": "agent", "text": text})
                case ToolCall():
                    asyncio.create_task(self._run_tool(live, ev))
                case ToolCallCancelled(call_ids=ids):
                    self._cancelled_tools.update(ids)
                    rec.log("tool_cancelled", ids=ids)
                case TurnComplete():
                    rec.on_turn_complete()
                    self.turns.turn_complete()
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

    async def _execute(self, call: ToolCall) -> dict:
        if call.name not in self.agent.tools:
            # the model asked for a tool this agent version does not allow (AC04)
            return {"status": "unavailable", "message": "Công cụ này không được cấp cho agent"}
        if call.name == "request_handoff" and self.persist:
            # a real inbox task, or an honest failure the agent must relay (never "đã chuyển" without it)
            created = await self.sink.request_handoff(
                str(call.args.get("reason", "")), str(call.args.get("summary", ""))
            )
            if created is None:
                return {
                    "status": "unavailable",
                    "message": (
                        "Chưa ghi nhận được yêu cầu chuyển nhân viên. Xin số điện thoại và hẹn gọi lại."
                    ),
                }
            return {
                "status": "ok",
                "source_provider": "voiceos",
                "data": {
                    "handoff_status": "queued",
                    "task_id": created["task_id"],
                    # after hours: a callback in the next working window, not a live transfer (AC24)
                    "after_hours": bool(created.get("after_hours")),
                    "callback_after": created.get("callback_after"),
                },
            }
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self.toolbox.execute, call.name, call.args), TOOL_TIMEOUT_S
            )
        except TimeoutError:
            return {"status": "timeout", "message": "Hệ thống chưa phản hồi, chưa thực hiện được"}

    async def _run_tool(self, live, call: ToolCall) -> None:
        self.recorder.on_tool_call(call.call_id, call.name, call.args)
        await self.transport.notify({"type": "tool_call", "name": call.name, "args": call.args})
        started_ms, t0 = int(self.recorder.now_ms()), time.monotonic()
        result = await self._execute(call)
        self.recorder.on_tool_result(call.call_id, call.name, result)
        if result.get("status") == "ok":
            self._booked |= call.name == "create_appointment"
            self._handoff |= call.name == "request_handoff"
        if self.persist:
            self.sink.add_tool_run(
                tool=call.name,
                call_key=call.call_id or f"{call.name}-{started_ms}",
                args=call.args,
                result=result,
                started_ms=started_ms,
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        await self.transport.notify({"type": "tool_result", "name": call.name, "result": result})
        if call.call_id in self._cancelled_tools:
            return  # the model already moved on (barge-in); do not resend
        await live.send_tool_results([ToolResult(call.call_id, call.name, result)])
