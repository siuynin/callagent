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
class Routing:
    """Backend routing decision for a call arriving now (AC24). None when the backend is unreachable:
    the call is then answered by the agent as if in hours, which never strands a caller."""

    after_hours: bool
    target: str  # agent | announcement
    announcement: str = ""
    opens_at: datetime | None = None
    reason: str = ""


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
                headers=_service_headers(settings),
            )
        r.raise_for_status()
        data = r.json()
        return AgentRuntime(config=data["config"], version_id=data["version_id"], number=data["number"])
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("active agent unavailable, using bundled prompt: %s", exc)
        return None


def _service_headers(settings: Settings) -> dict:
    return {"X-Service-Token": settings.gateway_service_token, "X-Tenant-Id": settings.gateway_tenant_id}


async def fetch_routing(settings: Settings, number: str | None = None) -> Routing | None:
    if not (settings.gateway_service_token and settings.gateway_tenant_id):
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            r = await client.get(
                f"{settings.backend_url.rstrip('/')}/api/v1/internal/routing",
                params={"number": number} if number else None,
                headers=_service_headers(settings),
            )
        r.raise_for_status()
        d = r.json()
        return Routing(
            after_hours=bool(d["after_hours"]),
            target=d["target"],
            announcement=d.get("announcement") or "",
            opens_at=datetime.fromisoformat(d["opens_at"]) if d.get("opens_at") else None,
            reason=d.get("reason") or "",
        )
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("routing unavailable, answering as in hours: %s", exc)
        return None


def _when_vi(dt: datetime | None, tz: ZoneInfo, now: datetime) -> str:
    if dt is None:
        return "khi có lịch làm việc mới"
    local = dt.astimezone(tz)
    day = (local.date() - now.astimezone(tz).date()).days
    rel = {0: "hôm nay", 1: "sáng mai" if local.hour < 12 else "ngày mai"}.get(day)
    date_part = rel or f"{WEEKDAYS_VI[local.weekday()]} {local.strftime('%d/%m')}"
    clock = f"{local.hour} giờ" + (f" {local.minute:02d}" if local.minute else "")
    return f"{clock} {date_part}"


def _after_hours_block(routing: Routing, tz: ZoneInfo, now: datetime) -> str:
    reason = "" if routing.reason in ("", "outside_hours") else f" (nghỉ: {routing.reason})"
    when = _when_vi(routing.opens_at, tz, now)
    return (
        "\n\n## Ngoài giờ làm việc\n"
        f"- Bây giờ là ngoài giờ làm việc{reason}. Giờ làm việc tiếp theo bắt đầu lúc {when}.\n"
        "- Không nói sẽ chuyển máy hoặc nhân viên gọi lại ngay. Không có nhân viên trực lúc này.\n"
        "- Vẫn tư vấn và đặt lịch bình thường nếu công cụ cho phép.\n"
        "- Khách cần gặp người thật: gọi request_handoff để ghi nhận, rồi nói nhân viên sẽ gọi lại "
        f"từ {when}. Chỉ nói vậy khi công cụ trả về thành công."
    )


def _announcement_spec(settings: Settings, routing: Routing, business: str, tz: ZoneInfo, now: datetime):
    text = routing.announcement.strip()
    if routing.opens_at:
        text += f" Giờ làm việc tiếp theo bắt đầu lúc {_when_vi(routing.opens_at, tz, now)}."
    prompt = (
        f"Bạn là hệ thống trả lời tự động của {business}. Ngay khi cuộc gọi bắt đầu, nói đúng một lần: "
        f'"Dạ, đây là lời nhắn tự động của {business}, cuộc gọi được ghi âm. {text}" '
        "rồi chào tạm biệt. Không trả lời câu hỏi khác, không hứa hẹn gì thêm. Nếu khách nói tiếp, "
        "lặp lại ngắn gọn giờ làm việc tiếp theo và chào tạm biệt."
    )
    return SessionSpec(system_instruction=prompt, tools=[])


def build_spec(
    settings: Settings,
    agent: AgentRuntime | None = None,
    now: datetime | None = None,
    routing: Routing | None = None,
) -> SessionSpec:
    agent = agent or file_agent(settings)
    cfg = agent.config
    tz = ZoneInfo(settings.default_timezone)
    now = now or datetime.now(tz)
    business = cfg.get("business_name") or settings.business_name
    if routing and routing.target == "announcement":
        return _announcement_spec(settings, routing, business, tz, now)
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
    if routing and routing.after_hours:
        prompt += _after_hours_block(routing, tz, now)
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
