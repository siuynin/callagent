from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent
GATEWAY_DIR = ROOT.parent

PROVIDERS = ("mock", "gemini", "openai")


@dataclass(frozen=True)
class Prices:
    """USD per 1M tokens. Any None means "not verified": no cost estimate is produced."""

    audio_in: float | None
    audio_out: float | None
    text_in: float | None
    text_out: float | None

    @property
    def complete(self) -> bool:
        return None not in (self.audio_in, self.audio_out, self.text_in, self.text_out)


class Settings(BaseSettings):
    # independent of the working directory: repo .env first, media-gateway/.env overrides
    model_config = SettingsConfigDict(
        env_file=(GATEWAY_DIR.parent / ".env", GATEWAY_DIR / ".env"), extra="ignore", env_ignore_empty=True
    )

    app_env: str = "dev"
    default_timezone: str = "Asia/Ho_Chi_Minh"
    ai_provider: str = "mock"  # default provider: mock | gemini | openai (the spike page can pick per call)
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8100
    reports_dir: Path = ROOT.parent / "reports"
    business_name: str = "Showroom mẫu"

    # VAD handed to the model (single source of turn-taking, ADR 0003)
    vad_silence_ms: int = 600
    vad_prefix_padding_ms: int = 120

    # persistence to the backend internal API (ADR 0006); empty token or tenant = disabled
    backend_url: str = "http://127.0.0.1:8000"
    gateway_service_token: str = ""
    gateway_tenant_id: str = ""
    gateway_agent_id: str = ""  # empty = the tenant's first published receptionist
    eval_scenarios_dir: Path = GATEWAY_DIR.parent / "eval" / "scenarios"

    # Gemini Live (ADR 0003)
    gemini_api_key: str = ""
    ai_model: str = "gemini-3.8-live"
    ai_voice: str = ""

    # OpenAI Realtime (ADR 0005)
    openai_api_key: str = ""
    openai_realtime_model: str = "gpt-realtime-2.1"
    openai_voice: str = "marin"
    openai_transcribe_model: str = "gpt-transcribe"
    openai_vad: str = "server_vad"  # server_vad | semantic_vad

    # optional cost estimate per provider; empty = not computed (prices must come from the official page)
    gemini_price_audio_in_per_mtok: float | None = None
    gemini_price_audio_out_per_mtok: float | None = None
    gemini_price_text_in_per_mtok: float | None = None
    gemini_price_text_out_per_mtok: float | None = None
    openai_price_audio_in_per_mtok: float | None = None
    openai_price_audio_out_per_mtok: float | None = None
    openai_price_text_in_per_mtok: float | None = None
    openai_price_text_out_per_mtok: float | None = None
    usd_to_vnd: float | None = None

    def prices(self, provider: str) -> Prices:
        if provider not in ("gemini", "openai"):
            return Prices(None, None, None, None)
        return Prices(
            getattr(self, f"{provider}_price_audio_in_per_mtok"),
            getattr(self, f"{provider}_price_audio_out_per_mtok"),
            getattr(self, f"{provider}_price_text_in_per_mtok"),
            getattr(self, f"{provider}_price_text_out_per_mtok"),
        )

    def model_for(self, provider: str) -> str:
        return {"gemini": self.ai_model, "openai": self.openai_realtime_model}.get(provider, "mock")

    def available_providers(self) -> list[str]:
        out = ["mock"]
        if self.gemini_api_key:
            out.append("gemini")
        if self.openai_api_key:
            out.append("openai")
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()
