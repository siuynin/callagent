from gateway.config import Settings
from gateway.providers.base import LiveProvider, SessionSpec


def make_provider(settings: Settings) -> LiveProvider:
    if settings.ai_provider == "gemini":
        from gateway.providers.gemini import GeminiLiveProvider

        if not settings.gemini_api_key:
            raise RuntimeError("AI_PROVIDER=gemini but GEMINI_API_KEY is empty (set it in voiceos/.env)")
        return GeminiLiveProvider(settings)
    from gateway.providers.mock import MockLiveProvider

    return MockLiveProvider()


__all__ = ["LiveProvider", "SessionSpec", "make_provider"]
