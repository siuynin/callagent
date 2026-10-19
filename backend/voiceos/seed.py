"""Synthetic dev data only (plan/examples). Never load production customer data here.

python -m voiceos.seed  -> prints dev bearer tokens for the two demo tenants.
"""

import uuid

from sqlalchemy import select

from voiceos import db
from voiceos.domain.phone import normalize_vn_phone
from voiceos.models import Contact, Membership, Tenant, User

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


if __name__ == "__main__":
    factory = db.configure()
    with factory() as s:
        seed(s)
    print("Dev tokens (APP_ENV=dev, DEV_AUTH=true):")
    print(f"  admin A : Bearer dev:{USER_ADMIN_A}")
    print(f"  staff A : Bearer dev:{USER_STAFF_A}")
    print(f"  admin B : Bearer dev:{USER_ADMIN_B}")
