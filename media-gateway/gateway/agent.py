"""Which agent version a call runs (ADR 0006/0007).

Live calls use the backend's *published active* version, never a draft (AC04). Eval runs use the draft config
sent by the backend. If the backend is unreachable the gateway falls back to the bundled prompt so the line
still answers; such calls are stored without an agent version and flagged in the report.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from gateway.config import ROOT, Settings
from gateway.providers.base import SessionSpec
from gateway.tools import TOOL_SPECS

log = logging.getLogger("gateway.agent")

WEEKDAYS_VI = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ nhật"]
FALLBACK_GREETING = (
    "Dạ, {business_name} xin nghe. Em là trợ lý AI, cuộc gọi được ghi âm để phục vụ anh/chị tốt hơn. "
    "Em có thể giúp gì ạ?"
)


@dataclass(frozen=True)
class AgentRuntime:
    config: dict
    version_id: str | None = None
    number: int | None = None
    source: str = "backend"  # backend | draft | file

    @property
    def tools(self) -> set[str]:
        return set(self.config.get("tools") or [t.name for t in TOOL_SPECS])


def file_agent(settings: Settings) -> AgentRuntime:
    return AgentRuntime(
        source="file",
        config={
            "instructions": (ROOT / "agents" / "receptionist.vi.md").read_text(encoding="utf-8"),
            "greeting": FALLBACK_GREETING,
            "business_name": settings.business_name,
            "tools": [t.name for t in TOOL_SPECS],
        },
    )


async def fetch_active_agent(settings: Settings) -> AgentRuntime | None:
    if not (settings.gateway_service_token and settings.gateway_tenant_id):
        return None
    params = (
        {"agent_id": settings.gateway_agent_id} if settings.gateway_agent_id else {"purpose": "receptionist"}
    )
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            r = await client.get(
                f"{settings.backend_url.rstrip('/')}/api/v1/internal/agents/active",
                params=params,
                headers={
                    "X-Service-Token": settings.gateway_service_token,
                    "X-Tenant-Id": settings.gateway_tenant_id,
                },
            )
        r.raise_for_status()
        data = r.json()
        return AgentRuntime(config=data["config"], version_id=data["version_id"], number=data["number"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("active agent unavailable, using bundled prompt: %s", exc)
        return None


def build_spec(
    settings: Settings, agent: AgentRuntime | None = None, now: datetime | None = None
) -> SessionSpec:
    agent = agent or file_agent(settings)
    cfg = agent.config
    tz = ZoneInfo(settings.default_timezone)
    now = now or datetime.now(tz)
    business = cfg.get("business_name") or settings.business_name
    greeting = cfg.get("greeting", FALLBACK_GREETING).format(business_name=business)
    prompt = cfg["instructions"].format(
        business_name=business,
        greeting=greeting,
        today=now.strftime("%d/%m/%Y"),
        weekday=WEEKDAYS_VI[now.weekday()],
        now_time=now.strftime("%H:%M"),
        timezone=settings.default_timezone,
    )
    # the model only sees the tools this version allows (AC04); execution re-checks the same list
    tools = [t for t in TOOL_SPECS if t.name in agent.tools]
    return SessionSpec(system_instruction=prompt, tools=tools)


def settings_for(settings: Settings, agent: AgentRuntime | None, provider: str) -> Settings:
    """Per-call settings: VAD from the version; voice only when the call uses the version's own provider
    (voice names differ between providers, the A/B page may pick the other one)."""
    if agent is None or agent.source == "file":
        return settings
    cfg = agent.config
    update: dict = {}
    if cfg.get("vad_silence_ms"):
        update["vad_silence_ms"] = cfg["vad_silence_ms"]
    if cfg.get("business_name"):
        update["business_name"] = cfg["business_name"]
    if cfg.get("voice") and cfg.get("provider") == provider:
        update["openai_voice" if provider == "openai" else "ai_voice"] = cfg["voice"]
    return settings.model_copy(update=update)


def scenario_paths(settings: Settings) -> list[Path]:
    """Eval suite for publish gating: every scenario except templates (files starting with "_")."""
    return sorted(p for p in Path(settings.eval_scenarios_dir).glob("*.json") if not p.name.startswith("_"))
