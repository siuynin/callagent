"""Per-call measurements for gate G-V (plan/docs/02, plan/docs/07 M0.5).

Latency of a turn = first agent audio chunk - end of customer speech. End of speech comes from the
provider VAD when it emits one, else from a local energy detector (marked `eos_source=local`).
Reports contain transcripts (personal data): they stay in media-gateway/reports, which is gitignored.
"""

import json
import re
import statistics
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from gateway.audio import rms_dbfs
from gateway.config import Settings

SPEECH_DBFS = -45.0
LOCAL_SILENCE_MS = 300

# phrases that claim a completed action; they must not appear before a successful tool result (AC21)
CONFIRM_PATTERNS = {
    "create_appointment": re.compile(
        r"(đã|vừa)\s+(đặt|tạo|chốt|xác nhận|giữ)(\s+xong)?(\s+(lịch|hẹn|chỗ))?|đặt\s+xong|đặt\s+thành\s+công",
        re.IGNORECASE,
    ),
    "request_handoff": re.compile(r"đã\s+(kết nối|nối máy)|nhân viên\s+đã\s+nhận", re.IGNORECASE),
}


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 1)
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(p) - 1], 1)


@dataclass
class CallRecorder:
    settings: Settings
    mode: str  # browser | browser_phone_sim | eval
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    t0: float = field(default_factory=time.monotonic)
    events: list[dict] = field(default_factory=list)
    latencies_ms: list[float] = field(default_factory=list)
    interrupt_ms: list[float] = field(default_factory=list)
    tool_ms: list[float] = field(default_factory=list)
    false_confirms: list[dict] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    successful_tools: set[str] = field(default_factory=set)
    _speaking: bool = False
    _last_loud: float | None = None
    _speech_start: float | None = None
    _eos: float | None = None
    _eos_source: str | None = None
    _await_first_audio: bool = False
    _agent_text: str = ""
    _tool_started: dict[str, float] = field(default_factory=dict)
    _agent_audio_active: bool = False
    _flagged_this_turn: set[str] = field(default_factory=set)

    def now_ms(self) -> float:
        return round((time.monotonic() - self.t0) * 1000, 1)

    def log(self, kind: str, **data) -> None:
        self.events.append({"t_ms": self.now_ms(), "kind": kind, **data})

    # --- caller audio (local energy VAD, measurement only) ---

    def on_caller_audio(self, pcm16_16k: bytes) -> None:
        now = time.monotonic()
        if rms_dbfs(pcm16_16k) > SPEECH_DBFS:
            if not self._speaking:
                self._speaking = True
                self._speech_start = now
                if self._agent_audio_active:
                    self.log("barge_in_start")
            self._last_loud = now
        elif self._speaking and self._last_loud and (now - self._last_loud) * 1000 >= LOCAL_SILENCE_MS:
            self._speaking = False
            if self._eos_source != "provider":
                self._eos, self._eos_source = self._last_loud, "local"
                self._await_first_audio = True

    # --- provider events ---

    def on_speech_ended(self) -> None:
        self._eos, self._eos_source = time.monotonic(), "provider"
        self._await_first_audio = True

    def on_agent_audio(self) -> None:
        self._agent_audio_active = True
        if self._await_first_audio and self._eos is not None:
            latency = (time.monotonic() - self._eos) * 1000
            self.latencies_ms.append(latency)
            self.log("turn_latency", ms=round(latency, 1), eos_source=self._eos_source)
            self._await_first_audio = False
            self._eos_source = None

    def on_interrupted(self) -> None:
        self._agent_audio_active = False
        if self._speech_start is not None:
            ms = (time.monotonic() - self._speech_start) * 1000
            if ms < 5000:
                self.interrupt_ms.append(ms)
            self.log("interrupted", ms_after_speech_start=round(ms, 1))
        else:
            self.log("interrupted")

    def on_turn_complete(self) -> None:
        self._agent_audio_active = False
        self.log("agent_turn", text=self._agent_text.strip())
        self._agent_text = ""
        self._flagged_this_turn.clear()

    def on_input_transcript(self, text: str) -> None:
        self.log("caller_text", text=text)

    def on_output_transcript(self, text: str) -> None:
        self._agent_text += text
        for tool, pattern in CONFIRM_PATTERNS.items():
            # transcripts stream in fragments: count at most one violation per tool per agent turn
            if tool in self.successful_tools or tool in self._flagged_this_turn:
                continue
            if pattern.search(self._agent_text):
                self._flagged_this_turn.add(tool)
                self.false_confirms.append({"t_ms": self.now_ms(), "tool": tool, "text": self._agent_text})
                self.log("false_confirm", tool=tool, text=self._agent_text)

    def on_tool_call(self, call_id: str, name: str, args: dict) -> None:
        self._tool_started[call_id] = time.monotonic()
        self.log("tool_call", id=call_id, name=name, args=args)

    def on_tool_result(self, call_id: str, name: str, result: dict) -> None:
        started = self._tool_started.pop(call_id, None)
        if started is not None:
            self.tool_ms.append((time.monotonic() - started) * 1000)
        if result.get("status") == "ok":
            self.successful_tools.add(name)
        self.log("tool_result", id=call_id, name=name, status=result.get("status"))

    def on_usage(self, total: int, prompt: int, response: int, by_modality: dict) -> None:
        self.usage.append(
            {"total": total, "prompt": prompt, "response": response, "by_modality": by_modality}
        )

    # --- report ---

    def _cost(self) -> dict | None:
        s = self.settings
        prices = [
            s.price_audio_in_per_mtok,
            s.price_audio_out_per_mtok,
            s.price_text_in_per_mtok,
            s.price_text_out_per_mtok,
        ]
        if not self.usage or any(p is None for p in prices):
            return None
        # usage messages may be cumulative or per turn depending on the provider: we take the
        # snapshot with the largest total and flag it so the number is checked against billing
        last = max(self.usage, key=lambda u: u["total"])
        pm, rm = last["by_modality"].get("prompt", {}), last["by_modality"].get("response", {})
        usd = (
            pm.get("AUDIO", 0) * s.price_audio_in_per_mtok
            + pm.get("TEXT", 0) * s.price_text_in_per_mtok
            + rm.get("AUDIO", 0) * s.price_audio_out_per_mtok
            + rm.get("TEXT", 0) * s.price_text_out_per_mtok
        ) / 1_000_000
        minutes = max(self.now_ms() / 60000, 1e-9)
        out = {
            "usd_total": round(usd, 6),
            "usd_per_minute": round(usd / minutes, 6),
            "basis": "max usage snapshot; verify against billing console",
        }
        if s.usd_to_vnd:
            out["vnd_per_minute"] = round(usd / minutes * s.usd_to_vnd)
        return out

    def summary(self) -> dict:
        return {
            "call_id": self.call_id,
            "mode": self.mode,
            "provider": self.settings.ai_provider,
            "model": self.settings.ai_model if self.settings.ai_provider == "gemini" else "mock",
            "duration_s": round(self.now_ms() / 1000, 1),
            "turns_measured": len(self.latencies_ms),
            "latency_ms": {
                "p50": _pct(self.latencies_ms, 50),
                "p95": _pct(self.latencies_ms, 95),
                "max": round(max(self.latencies_ms), 1) if self.latencies_ms else None,
            },
            "interruptions": len(self.interrupt_ms),
            "interrupt_ms": {"p50": _pct(self.interrupt_ms, 50), "p95": _pct(self.interrupt_ms, 95)},
            "tool_calls": sum(1 for e in self.events if e["kind"] == "tool_call"),
            "tool_ms_p95": _pct(self.tool_ms, 95),
            "false_confirmations": len(self.false_confirms),
            "reconnects": sum(1 for e in self.events if e["kind"] == "reconnected"),
            "usage_last": max(self.usage, key=lambda u: u["total"]) if self.usage else None,
            "cost_estimate": self._cost(),
        }

    def write(self, directory: Path | None = None) -> Path:
        directory = directory or self.settings.reports_dir
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        path = directory / f"{stamp}-{self.call_id}.json"
        path.write_text(
            json.dumps({"summary": self.summary(), "events": self.events}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path
