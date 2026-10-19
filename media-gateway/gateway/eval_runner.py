"""Voice evaluation runner (plan/docs/02 "Bộ đánh giá voice tiếng Việt", gate G-V).

Streams recorded caller turns (WAV) in real time through the same CallSession used for live calls,
then checks expectations. Usage:

  python -m gateway.eval_runner ../eval/scenarios/*.json [--provider gemini|openai] [--out ../eval/results]

Scenario format: see ../eval/README.md.
"""

import argparse
import asyncio
import glob
import json
import time
import wave
from pathlib import Path

from gateway.audio import resample
from gateway.config import get_settings
from gateway.providers import make_provider
from gateway.session import CallSession

CHUNK_MS = 40
CHUNK_BYTES = 16000 * 2 * CHUNK_MS // 1000
SILENCE = b"\x00" * CHUNK_BYTES


def load_wav_16k_mono(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: cần WAV PCM 16-bit")
        frames = w.readframes(w.getnframes())
        channels, rate = w.getnchannels(), w.getframerate()
    if channels == 2:  # downmix
        import numpy as np

        s = np.frombuffer(frames, dtype="<i2").reshape(-1, 2).astype(np.int32)
        frames = ((s[:, 0] + s[:, 1]) // 2).astype("<i2").tobytes()
    elif channels != 1:
        raise ValueError(f"{path}: chỉ hỗ trợ mono/stereo")
    return resample(frames, rate, 16000)


class FileTransport:
    """Plays caller turns in real time; between turns waits until the agent has finished speaking."""

    def __init__(self, turns: list[bytes], *, quiet_after_s: float = 1.5, turn_timeout_s: float = 25.0):
        self.turns = turns
        self.quiet_after_s = quiet_after_s
        self.turn_timeout_s = turn_timeout_s
        self.session: CallSession | None = None
        # models stream audio faster than real time: track when the caller would actually stop hearing it
        self.playing_until = 0.0
        self.heard_any = False
        self._gen = self._frames()
        self.agent_audio_ms = 0.0

    async def _frames(self):
        await asyncio.sleep(1.0)  # let the agent greet first if it wants to
        for audio in self.turns:
            await self._wait_agent_quiet()
            for i in range(0, len(audio), CHUNK_BYTES):
                yield audio[i : i + CHUNK_BYTES].ljust(CHUNK_BYTES, b"\x00")
                await asyncio.sleep(CHUNK_MS / 1000)
            if self.session:
                self.session.turn_complete.clear()
            started = time.monotonic()
            # keep the line open with silence (a real phone line never stops sending frames)
            while time.monotonic() - started < self.turn_timeout_s:
                yield SILENCE
                await asyncio.sleep(CHUNK_MS / 1000)
                if self._agent_done():
                    break
        for _ in range(int(1000 / CHUNK_MS)):
            yield SILENCE
            await asyncio.sleep(CHUNK_MS / 1000)

    def _agent_done(self) -> bool:
        quiet = time.monotonic() >= self.playing_until + self.quiet_after_s
        return bool(self.session and self.session.turn_complete.is_set() and quiet)

    async def _wait_agent_quiet(self):
        started = time.monotonic()
        while time.monotonic() - started < 30:
            if self.heard_any and time.monotonic() >= self.playing_until + self.quiet_after_s:
                return
            if not self.heard_any and time.monotonic() - started > 4:
                return  # agent did not greet
            await asyncio.sleep(0.05)

    async def recv_audio(self) -> bytes | None:
        try:
            return await self._gen.__anext__()
        except StopAsyncIteration:
            return None

    async def play(self, pcm: bytes, rate: int) -> None:
        duration = len(pcm) / 2 / rate
        now = time.monotonic()
        self.playing_until = max(now, self.playing_until) + duration
        self.heard_any = True
        self.agent_audio_ms += duration * 1000

    async def clear_playback(self) -> None:
        self.playing_until = time.monotonic()  # barge-in: the caller stops hearing the agent now

    async def notify(self, message: dict) -> None:
        pass


def check(scenario: dict, summary: dict, events: list[dict]) -> list[dict]:
    exp = scenario.get("expect", {})
    results = []
    calls = [e for e in events if e["kind"] == "tool_call"]
    for want in exp.get("tools", []):
        matched = [
            c
            for c in calls
            if c["name"] == want["name"]
            and all(_norm(c["args"].get(k)) == _norm(v) for k, v in want.get("args_subset", {}).items())
        ]
        results.append(
            {
                "check": f"tool {want['name']} {want.get('args_subset', {})}",
                "passed": bool(matched),
                "got": [c["args"] for c in calls if c["name"] == want["name"]],
            }
        )
    for name in exp.get("tools_absent", []):
        results.append({"check": f"không gọi {name}", "passed": not any(c["name"] == name for c in calls)})
    if exp.get("no_false_confirm", True):
        results.append({"check": "không xác nhận sai (AC21)", "passed": summary["false_confirmations"] == 0})
    if "max_p95_latency_ms" in exp and summary["latency_ms"]["p95"] is not None:
        results.append(
            {
                "check": f"p95 <= {exp['max_p95_latency_ms']} ms",
                "passed": summary["latency_ms"]["p95"] <= exp["max_p95_latency_ms"],
                "got": summary["latency_ms"]["p95"],
            }
        )
    agent_text = " ".join(e.get("text", "") for e in events if e["kind"] == "agent_turn").lower()
    for phrase in exp.get("agent_says_any", []):
        results.append({"check": f"AI nói '{phrase}'", "passed": phrase.lower() in agent_text})
    return results


def _norm(v):
    if isinstance(v, str):
        return "".join(ch for ch in v.lower() if ch.isalnum())
    return v


async def run_scenario(path: Path, provider_name: str | None) -> dict:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    settings = get_settings()
    base = path.parent
    turns = [load_wav_16k_mono((base / t["audio"]).resolve()) for t in scenario["turns"]]
    transport = FileTransport(turns)
    session = CallSession(
        make_provider(settings, provider_name),
        transport,
        settings,
        mode="eval",
        phone_sim=scenario.get("phone_sim"),
    )
    transport.session = session
    summary = await session.run()
    results = check(scenario, summary, session.recorder.events)
    return {
        "scenario": scenario["id"],
        "description": scenario.get("description", ""),
        "passed": all(r["passed"] for r in results),
        "checks": results,
        "summary": summary,
    }


async def main_async(args) -> int:
    paths = sorted({Path(p) for pattern in args.scenarios for p in glob.glob(pattern)})
    if not paths:
        print("Không tìm thấy scenario")
        return 2
    report = []
    for p in paths:
        print(f"▶ {p.name}")
        try:
            r = await run_scenario(p, args.provider)
        except Exception as exc:  # noqa: BLE001 - one broken scenario must not stop the run
            r = {"scenario": p.stem, "passed": False, "error": str(exc), "checks": []}
        report.append(r)
        for c in r["checks"]:
            print(f"   {'✓' if c['passed'] else '✗'} {c['check']}")
        if "error" in r:
            print(f"   ✗ lỗi: {r['error']}")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"eval-{time.strftime('%Y%m%d-%H%M%S')}.json"
    passed = sum(r["passed"] for r in report)
    latencies = [
        r["summary"]["latency_ms"]["p95"]
        for r in report
        if r.get("summary") and r["summary"]["latency_ms"]["p95"] is not None
    ]
    total = {
        "scenarios": len(report),
        "passed": passed,
        "false_confirmations": sum(r.get("summary", {}).get("false_confirmations", 0) for r in report),
        "worst_p95_latency_ms": max(latencies) if latencies else None,
    }
    out.write_text(
        json.dumps({"total": total, "results": report}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{passed}/{len(report)} scenario đạt · báo cáo: {out}")
    return 0 if passed == len(report) else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="VoiceOS voice eval runner")
    ap.add_argument("scenarios", nargs="+")
    ap.add_argument("--provider", choices=["mock", "gemini", "openai"])
    ap.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "eval" / "results"))
    raise SystemExit(asyncio.run(main_async(ap.parse_args())))


if __name__ == "__main__":
    main()
