"""Gateway -> backend persistence (ADR 0006).

The call must never depend on the backend being up: writes go to an in-memory queue drained by a
background task with retries. Every write is idempotent on the backend (turn seq, tool idempotency key,
provider_call_id), so retrying after a timeout cannot duplicate data. Only request_handoff waits for the
backend, because the agent must not tell the caller a request was registered when it was not (AC21).
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from gateway.config import Settings

log = logging.getLogger("gateway.backend")

TIMEOUT = httpx.Timeout(3.0, connect=2.0)
FLUSH_DEADLINE_S = 5.0
_PHONE_RE = re.compile(r"\d")


def redact_args(args: dict) -> dict:
    """Keep what staff need, mask phone numbers to the last 4 digits."""
    out = {}
    for k, v in args.items():
        if "phone" in k and isinstance(v, str):
            digits = "".join(_PHONE_RE.findall(v))
            out[k] = f"***{digits[-4:]}" if digits else "***"
        else:
            out[k] = v
    return out


@dataclass
class BackendSink:
    settings: Settings
    provider: str
    provider_call_id: str
    client: httpx.AsyncClient | None = None
    call_id: str | None = None
    sent: int = 0
    errors: list[str] = field(default_factory=list)
    _queue: list[tuple[str, dict]] = field(default_factory=list)
    _wake: asyncio.Event = field(default_factory=asyncio.Event)
    _task: asyncio.Task | None = None
    _seq: int = 0
    _tool_seq: int = 0
    _started_at: datetime | None = None
    _caller_number: str | None = None

    @property
    def enabled(self) -> bool:
        s = self.settings
        return bool(s.gateway_service_token and s.gateway_tenant_id and s.backend_url)

    def _headers(self) -> dict:
        return {
            "X-Service-Token": self.settings.gateway_service_token,
            "X-Tenant-Id": self.settings.gateway_tenant_id,
        }

    def _url(self, path: str) -> str:
        return f"{self.settings.backend_url.rstrip('/')}/api/v1/internal{path}"

    async def _post(self, path: str, body: dict) -> dict:
        if self.client is None:  # writes must work even if start() was skipped
            self.client = httpx.AsyncClient()
        r = await self.client.post(self._url(path), json=body, headers=self._headers(), timeout=TIMEOUT)
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(f"{r.status_code} {r.text[:200]}", request=r.request, response=r)
        return r.json()

    # --- lifecycle ---

    def start(self, started_at: datetime | None = None, caller_number: str | None = None) -> None:
        if not self.enabled:
            return
        self.client = self.client or httpx.AsyncClient()
        self._started_at = started_at or datetime.now(UTC)
        self._caller_number = caller_number
        self._task = asyncio.create_task(self._drain())

    async def _ensure_call(self) -> bool:
        if self.call_id:
            return True
        body = {
            "provider": self.provider,
            "provider_call_id": self.provider_call_id,
            "started_at": (self._started_at or datetime.now(UTC)).isoformat(),
        }
        if self._caller_number:
            body["caller_number"] = self._caller_number
        try:
            self.call_id = (await self._post("/calls", body))["id"]
            return True
        except (httpx.HTTPError, KeyError) as exc:
            self._note(f"create call: {exc}")
            return False

    def _note(self, msg: str) -> None:
        log.warning("backend persistence: %s", msg)
        if len(self.errors) < 20:
            self.errors.append(msg)

    async def _drain(self) -> None:
        backoff = 0.5
        while True:
            await self._wake.wait()
            self._wake.clear()
            while self._queue:
                if not await self._ensure_call() or not await self._send_batch():
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 5.0)
                    continue
                backoff = 0.5

    async def _send_batch(self) -> bool:
        kind = self._queue[0][0]
        batch = [b for k, b in self._queue if k == kind][:50]
        path, key = (
            (f"/calls/{self.call_id}/turns", "turns")
            if kind == "turn"
            else (f"/calls/{self.call_id}/tool-runs", "runs")
        )
        try:
            await self._post(path, {key: batch})
        except httpx.HTTPError as exc:
            self._note(f"send {kind}: {exc}")
            return False
        sent_ids = {id(b) for b in batch}
        self._queue = [(k, b) for k, b in self._queue if id(b) not in sent_ids]
        self.sent += len(batch)
        return True

    # --- writes ---

    def add_turn(self, speaker: str, text: str, started_ms: int, ended_ms: int | None = None) -> None:
        if not self.enabled or not text.strip():
            return
        self._seq += 1
        self._queue.append(
            (
                "turn",
                {
                    "seq": self._seq,
                    "speaker": speaker,
                    "text": text.strip(),
                    "started_ms": max(0, started_ms),
                    "ended_ms": ended_ms,
                },
            )
        )
        self._wake.set()

    def add_tool_run(
        self, *, tool: str, call_key: str, args: dict, result: dict, started_ms: int, duration_ms: int
    ) -> None:
        if not self.enabled:
            return
        self._tool_seq += 1
        self._queue.append(
            (
                "tool",
                {
                    "seq": self._tool_seq,
                    "tool": tool,
                    "args": redact_args(args),
                    "status": str(result.get("status", "unknown"))[:16],
                    "result": result,
                    "idempotency_key": f"{self.provider_call_id}:{call_key}"[:128],
                    "started_ms": max(0, started_ms),
                    "duration_ms": max(0, duration_ms),
                },
            )
        )
        self._wake.set()

    async def request_handoff(self, reason: str, summary: str) -> dict | None:
        """Synchronous on purpose: the agent may only say "đã chuyển yêu cầu" when this returns a task."""
        if not self.enabled:
            return None
        for _ in range(3):
            if await self._ensure_call():
                try:
                    return await self._post(
                        f"/calls/{self.call_id}/handoff",
                        {"reason": reason[:200] or "Khách yêu cầu gặp nhân viên", "summary": summary[:2000]},
                    )
                except httpx.HTTPError as exc:
                    self._note(f"handoff: {exc}")
            await asyncio.sleep(0.3)
        return None

    async def close(self, *, outcome: str | None, technical_status: str = "ended") -> dict:
        if not self.enabled:
            return {"enabled": False}
        deadline = asyncio.get_running_loop().time() + FLUSH_DEADLINE_S
        self._wake.set()
        while self._queue and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.05)
        ended = False
        if await self._ensure_call():
            body = {"ended_at": datetime.now(UTC).isoformat(), "technical_status": technical_status}
            if outcome:
                body["business_outcome"] = outcome
            try:
                await self._post(f"/calls/{self.call_id}/end", body)
                ended = True
            except httpx.HTTPError as exc:
                self._note(f"end call: {exc}")
        if self._task:
            self._task.cancel()
        if self.client:
            await self.client.aclose()
        return {
            "enabled": True,
            "backend_call_id": self.call_id,
            "sent": self.sent,
            "unsent": len(self._queue),
            "ended": ended,
            "errors": self.errors[:5],
        }
