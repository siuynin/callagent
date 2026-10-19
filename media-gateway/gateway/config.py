from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent
GATEWAY_DIR = ROOT.parent


class Settings(BaseSettings):
    # independent of the working directory: repo .env first, media-gateway/.env overrides
    model_config = SettingsConfigDict(
        env_file=(GATEWAY_DIR.parent / ".env", GATEWAY_DIR / ".env"), extra="ignore", env_ignore_empty=True
    )

    app_env: str = "dev"
    default_timezone: str = "Asia/Ho_Chi_Minh"
    ai_provider: str = "mock"  # mock | gemini
    ai_model: str = "gemini-3.8-live"
    ai_voice: str = ""
    gemini_api_key: str = ""
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8100
    reports_dir: Path = ROOT.parent / "reports"
    business_name: str = "Showroom mẫu"

    # VAD handed to the model (single source of turn-taking, ADR 0003)
    vad_silence_ms: int = 600
    vad_prefix_padding_ms: int = 120

    # optional cost estimate; empty = not computed (prices must come from the official page)
    price_audio_in_per_mtok: float | None = None
    price_audio_out_per_mtok: float | None = None
    price_text_in_per_mtok: float | None = None
    price_text_out_per_mtok: float | None = None
    usd_to_vnd: float | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
