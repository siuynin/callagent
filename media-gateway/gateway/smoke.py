"""Live smoke test without a microphone: open a real session, let the agent greet, report, close.

  python -m gateway.smoke --provider openai|gemini

Checks the key, model name and session config against the real API and measures time to first audio.
Costs a few seconds of model usage. Never runs in CI.
"""

import argparse
import asyncio
import json
import time

from gateway.config import get_settings
from gateway.eval_runner import CHUNK_MS, SILENCE, FileTransport
from gateway.providers import make_provider
from gateway.session import CallSession


class GreetingTransport(FileTransport):
    """Keeps a silent line open until the agent has finished its greeting (or a timeout)."""

    def __init__(self, timeout_s: float = 30.0):
        super().__init__([], quiet_after_s=1.0)
        self.deadline = time.monotonic() + timeout_s

    async def recv_audio(self) -> bytes | None:
        await asyncio.sleep(CHUNK_MS / 1000)
        if time.monotonic() > self.deadline or self._agent_done():
            return None
        return SILENCE


async def smoke(provider_name: str) -> int:
    settings = get_settings()
    transport = GreetingTransport()
    session = CallSession(make_provider(settings, provider_name), transport, settings, mode="smoke")
    transport.session = session
    try:
        summary = await asyncio.wait_for(session.run(), timeout=45)
    except Exception as exc:  # noqa: BLE001 - report in plain words
        print(f"✗ {provider_name}: {type(exc).__name__}: {exc}")
        return 1
    events = session.recorder.events
    first = next((e["t_ms"] for e in events if e["kind"] == "first_agent_audio"), None)
    opened = next((e["t_ms"] for e in events if e["kind"] == "session_open"), 0.0)
    turn_done = any(e["kind"] == "agent_turn" for e in events)
    greeting = " ".join(e.get("text", "") for e in events if e["kind"] == "agent_turn").strip()
    errors = [e["message"] for e in events if e["kind"] == "session_error"]
    ok = first is not None and turn_done and not errors
    print(
        json.dumps(
            {
                "provider": summary["provider"],
                "model": summary["model"],
                "ok": ok,
                "session_open_ms": opened,
                "first_audio_ms_after_open": round(first - opened, 1) if first is not None else None,
                "agent_audio_s": round(transport.agent_audio_ms / 1000, 1),
                "greeting_transcript": greeting or None,
                "errors": errors,
                "usage": summary["usage"],
                "report": summary["report_path"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="VoiceOS live provider smoke test")
    ap.add_argument("--provider", choices=["mock", "gemini", "openai"], required=True)
    raise SystemExit(asyncio.run(smoke(ap.parse_args().provider)))


if __name__ == "__main__":
    main()
