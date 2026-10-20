"""Synthetic dev data only (plan/examples). Never load production customer data here.

python -m voiceos.seed  -> prints dev bearer tokens for the two demo tenants.
"""

import uuid

from sqlalchemy import select

from voiceos import db
from voiceos.agents.config import config_hash, default_config
from voiceos.db import utcnow
from voiceos.domain.phone import normalize_vn_phone
from voiceos.models import Agent, AgentVersion, Contact, Membership, Tenant, User

# fixed ids so dev tokens stay stable across reseeds
TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
USER_ADMIN_A = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
USER_STAFF_A = uuid.UUID("00000000-0000-4000-8000-0000000000a2")
USER_ADMIN_B = uuid.UUID("00000000-0000-4000-8000-0000000000b1")

SAMPLE_CONTACTS = [
    ("Khách mẫu A", "0900000001", "Tư vấn"),
    ("Khách mẫu B", "0900000002", "Lái thử"),
    ("Khách mẫu C", "12345", "Bảo dưỡng"),
]


def seed_agents(session) -> bool:
    """One published receptionist per demo tenant (idempotent). v1 = the prompt that passed the TTS eval."""
    created = False
    for tenant in session.scalars(select(Tenant).where(Tenant.id.in_([TENANT_A, TENANT_B]))):
        if session.scalar(select(Agent.id).where(Agent.tenant_id == tenant.id)):
            continue
        agent = Agent(
            tenant_id=tenant.id,
            name="Lễ tân AI",
            purpose="receptionist",
            description="Tiếp nhận cuộc gọi đến, đặt lịch, chuyển nhân viên khi cần.",
        )
        session.add(agent)
        session.flush()
        config = default_config(tenant.name)
        version = AgentVersion(
            tenant_id=tenant.id,
            agent_id=agent.id,
            number=1,
            status="published",
            config=config,
            published_at=utcnow(),
            test_result={
                "status": "finished",
                "passed": True,
                "bootstrap": True,
                "config_hash": config_hash(config),
                "summary": {"note": "Khởi tạo từ prompt đã đạt 2/2 kịch bản TTS với OpenAI ngày 19/10/2026"},
            },
        )
        session.add(version)
        session.flush()
        agent.active_version_id = version.id
        created = True
    session.commit()
    return created


def seed_calendars(session) -> None:
    """Working calendar, sample holidays and default inbound route per demo tenant (idempotent)."""
    from voiceos.scheduling import ensure_defaults

    for tenant_id, owner in ((TENANT_A, USER_ADMIN_A), (TENANT_B, USER_ADMIN_B)):
        if session.get(Tenant, tenant_id) is None:
            continue
        _, route = ensure_defaults(session, tenant_id)
        route.after_hours_owner_id = route.after_hours_owner_id or owner
    session.commit()


def seed(session) -> None:
    if session.scalar(select(Tenant).where(Tenant.id == TENANT_A)):
        return
    session.add_all(
        [
            Tenant(id=TENANT_A, name="Showroom mẫu A"),
            Tenant(id=TENANT_B, name="Doanh nghiệp mẫu B"),
            User(id=USER_ADMIN_A, email="admin-a@example.invalid", display_name="Quản trị A"),
            User(id=USER_STAFF_A, email="staff-a@example.invalid", display_name="Nhân viên A"),
            User(id=USER_ADMIN_B, email="admin-b@example.invalid", display_name="Quản trị B"),
        ]
    )
    session.flush()
    session.add_all(
        [
            Membership(tenant_id=TENANT_A, user_id=USER_ADMIN_A, role="admin"),
            Membership(tenant_id=TENANT_A, user_id=USER_STAFF_A, role="staff"),
            Membership(tenant_id=TENANT_B, user_id=USER_ADMIN_B, role="admin"),
        ]
    )
    for name, phone, need in SAMPLE_CONTACTS:
        n = normalize_vn_phone(phone)
        session.add(
            Contact(
                tenant_id=TENANT_A,
                name=name,
                phone_raw=phone,
                normalized_phone=n.e164,
                phone_status=n.status,
                need=need,
            )
        )
    session.commit()
    seed_agents(session)
    seed_calendars(session)


if __name__ == "__main__":
    factory = db.configure()
    with factory() as s:
        seed(s)
        seed_agents(s)
        seed_calendars(s)
    print("Dev tokens (APP_ENV=dev, DEV_AUTH=true):")
    print(f"  admin A : Bearer dev:{USER_ADMIN_A}")
    print(f"  staff A : Bearer dev:{USER_STAFF_A}")
    print(f"  admin B : Bearer dev:{USER_ADMIN_B}")
