from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from voiceos.api import errors
from voiceos.api.routers import calls, contacts, system, tasks
from voiceos.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="VoiceOS API", version="0.1.0", openapi_url="/api/v1/openapi.json", docs_url="/api/v1/docs"
    )
    errors.install(app)
    if settings.app_env == "dev":
        # dev only: Next.js dev server on another port; production is same-origin (plan/docs/02)
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["x-trace-id"],
        )
    for router in (system.router, contacts.router, calls.router, tasks.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
