from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    # independent of the working directory: repo .env first, backend/.env overrides
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"), extra="ignore", env_ignore_empty=True
    )

    app_env: str = "dev"
    default_timezone: str = "Asia/Ho_Chi_Minh"
    database_url: str = "sqlite+pysqlite:///./voiceos-dev.db"
    redis_url: str = "redis://localhost:6379/0"
    dev_auth: bool = False

    call_provider: str = "mock"
    connector_mode: str = "mock"
    notify_provider: str = "mock"
    outbound_enabled: bool = False

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite(cls, v: str) -> str:
        # relative SQLite paths resolve against backend/, not the process working directory
        prefix = "sqlite+pysqlite:///./"
        return (
            f"sqlite+pysqlite:///{(BACKEND_DIR / v[len(prefix) :]).as_posix()}" if v.startswith(prefix) else v
        )

    def check_safety(self) -> None:
        if self.dev_auth and self.app_env != "dev":
            raise RuntimeError("DEV_AUTH is only allowed when APP_ENV=dev")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check_safety()
    return settings
