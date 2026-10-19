from fastapi import APIRouter
from sqlalchemy import select, text

from voiceos.api.deps import Auth, DbSession
from voiceos.config import get_settings
from voiceos.models import Tenant

router = APIRouter()


@router.get("/health")
def health(db: DbSession):
    db.execute(text("SELECT 1"))
    s = get_settings()
    return {
        "status": "ok",
        "env": s.app_env,
        # surfaced so the UI can label simulated behaviour (plan/START_HERE)
        "modes": {
            "call_provider": s.call_provider,
            "connector_mode": s.connector_mode,
            "notify_provider": s.notify_provider,
            "outbound_enabled": s.outbound_enabled,
        },
    }


@router.get("/me")
def me(auth: Auth, db: DbSession):
    tenant = db.scalar(select(Tenant).where(Tenant.id == auth.tenant_id))
    return {
        "user_id": str(auth.user_id),
        "tenant": {"id": str(tenant.id), "name": tenant.name, "timezone": tenant.timezone},
        "role": auth.role,
    }
