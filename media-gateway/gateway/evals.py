"""Eval suite run on request from the backend, gating agent publishing (AC25, ADR 0007).

The backend sends the draft config; the gateway runs every scenario in eval/scenarios (except templates)
with that config and posts one verdict back. Only one suite runs at a time.
"""

import asyncio
import hmac
import json
import logging
import time
from pathlib import Path

import httpx
from pydantic import BaseModel

from gateway.agent import AgentRuntime, scenario_paths, settings_for

__all__ = ["EvalRequest", "authorized", "busy", "run_suite", "scenario_paths", "verdict"]
from gateway.config import Settings

log = logging.getLogger("gateway.evals")
_lock = asyncio.Lock()


class EvalRequest(BaseModel):
    tenant_id: str
    agent_id: str
    version_id: str
    config: dict
    config_hash: str


def authorized(settings: Settings, token: str | None, tenant_id: str) -> bool:
    expected = settings.gateway_service_token
    if not expected or not token or not hmac.compare_digest(token.encode(), expected.encode()):
        return False
    # this gateway serves one tenant; refuse work for another
    return tenant_id == settings.gateway_tenant_id


def busy() -> bool:
    return _lock.locked()


def verdict(results: list[dict], max_p95_ms: int) -> tuple[bool, dict]:
    ok = [r for r in results if r.get("passed")]
    false_confirms = sum(r.get("summary", {}).get("false_confirmations", 0) for r in results)
    p95s = [
        r["summary"]["latency_ms"]["p95"]
        for r in results
        if r.get("summary") and r["summary"]["latency_ms"]["p95"]
    ]
    worst = max(p95s) if p95s else None
    passed = (
        bool(results)
        and len(ok) == len(results)
        and false_confirms == 0
        and (worst is None or worst <= max_p95_ms)
    )
    summary = {
        "scenarios": len(results),
        "passed": len(ok),
        "failed": [r["scenario"] for r in results if not r.get("passed")],
        "false_confirmations": false_confirms,
        "worst_p95_ms": worst,
        "max_p95_ms": max_p95_ms,
        "checks": {r["scenario"]: [c for c in r.get("checks", []) if not c["passed"]] for r in results},
        "errors": {r["scenario"]: r["error"] for r in results if r.get("error")},
    }
    return passed, summary


async def run_suite(settings: Settings, req: EvalRequest, paths: list[Path] | None = None) -> None:
    from gateway.eval_runner import run_scenario  # heavy import, keep app startup light

    async with _lock:
        agent = AgentRuntime(config=req.config, version_id=req.version_id, source="draft")
        provider = req.config.get("provider", "openai")
        call_settings = settings_for(settings, agent, provider)
        paths = paths if paths is not None else scenario_paths(settings)
        started = time.monotonic()
        results, error = [], None
        if not paths:
            error = "Chưa có kịch bản đánh giá nào (eval/scenarios)"
        for p in paths:
            try:
                results.append(
                    await run_scenario(p, provider, persist=False, agent=agent, settings=call_settings)
                )
            except Exception as exc:  # noqa: BLE001 - one broken scenario fails the suite, not the gateway
                log.warning("eval scenario %s failed: %s", p.name, exc)
                results.append({"scenario": p.stem, "passed": False, "error": str(exc)[:300], "checks": []})
        passed, summary = verdict(results, int(req.config.get("eval_max_p95_ms", 2000)))
        summary.update(provider=provider, duration_s=round(time.monotonic() - started, 1))
        await _report(settings, req, passed and error is None, summary, error)


async def _report(
    settings: Settings, req: EvalRequest, passed: bool, summary: dict, error: str | None
) -> None:
    body = {
        "config_hash": req.config_hash,
        "passed": passed,
        "summary": json.loads(json.dumps(summary, default=str)),
        "error": error,
    }
    headers = {"X-Service-Token": settings.gateway_service_token, "X-Tenant-Id": req.tenant_id}
    url = f"{settings.backend_url.rstrip('/')}/api/v1/internal/agent-versions/{req.version_id}/eval-result"
    for attempt in range(5):
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            return
        except httpx.HTTPError as exc:
            log.warning("eval result not delivered (attempt %s): %s", attempt + 1, exc)
            await asyncio.sleep(2**attempt)
