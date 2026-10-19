import os

# must be set before voiceos.config is imported anywhere
os.environ.setdefault("APP_ENV", "dev")
os.environ["DEV_AUTH"] = "true"
os.environ["GATEWAY_SERVICE_TOKEN"] = "test-service-token"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from voiceos import db as dbmod  # noqa: E402
from voiceos.config import get_settings  # noqa: E402
from voiceos.db import Base  # noqa: E402
from voiceos.seed import TENANT_A, TENANT_B, USER_ADMIN_A, USER_ADMIN_B, USER_STAFF_A, seed, seed_agents  # noqa: E402

TEST_DB = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///./test-voiceos.db")
IS_POSTGRES = TEST_DB.startswith("postgresql")


def pytest_collection_modifyitems(items):
    if IS_POSTGRES:
        return
    skip = pytest.mark.skip(reason="needs PostgreSQL (set TEST_DATABASE_URL)")
    for item in items:
        if "postgres_only" in item.keywords:
            item.add_marker(skip)


@pytest.fixture()
def session_factory():
    get_settings.cache_clear()
    factory = dbmod.configure(TEST_DB)
    engine = dbmod.get_engine()
    import voiceos.models  # noqa: F401

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with factory() as s:
        seed(s)
        seed_agents(s)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def client(session_factory):
    from voiceos.api.main import create_app

    with TestClient(create_app()) as c:
        yield c


def auth(user, tenant=None) -> dict:
    headers = {"Authorization": f"Bearer dev:{user}"}
    if tenant:
        headers["X-Tenant-Id"] = str(tenant)
    return headers


ADMIN_A = auth(USER_ADMIN_A)
STAFF_A = auth(USER_STAFF_A)
ADMIN_B = auth(USER_ADMIN_B)
__all__ = ["ADMIN_A", "ADMIN_B", "STAFF_A", "TENANT_A", "TENANT_B", "auth"]
