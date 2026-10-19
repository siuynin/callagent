from gateway.config import PROVIDERS, Settings
from gateway.providers.base import LiveProvider, SessionSpec


def make_provider(settings: Settings, name: str | None = None) -> LiveProvider:
    """Build the provider for one call. `name` overrides AI_PROVIDER (spike page A/B comparison)."""
    name = name or settings.ai_provider
    if name not in PROVIDERS:
        raise ValueError(f"Provider không hỗ trợ: {name}")
    if name == "gemini":
        from gateway.providers.gemini import GeminiLiveProvider

        if not settings.gemini_api_key:
            raise RuntimeError("Chưa có GEMINI_API_KEY trong voiceos/.env")
        return GeminiLiveProvider(settings)
    if name == "openai":
        from gateway.providers.openai_realtime import OpenAIRealtimeProvider

        if not settings.openai_api_key:
            raise RuntimeError("Chưa có OPENAI_API_KEY trong voiceos/.env")
        return OpenAIRealtimeProvider(settings)
    from gateway.providers.mock import MockLiveProvider

    return MockLiveProvider()


__all__ = ["LiveProvider", "SessionSpec", "make_provider"]
