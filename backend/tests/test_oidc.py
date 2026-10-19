"""OIDC sign-in and member management with locally signed tokens (no network)."""

import time

import jwt
import pytest
from conftest import ADMIN_A, STAFF_A, TENANT_A
from cryptography.hazmat.primitives.asymmetric import rsa

from voiceos.config import get_settings
from voiceos.models import Membership, Task, User
from voiceos.seed import USER_ADMIN_A, USER_STAFF_A

ISSUER = "https://login.example.test"
CLIENT = "voiceos-web"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def oidc(monkeypatch, session_factory):  # after session_factory, which resets the settings cache
    s = get_settings()
    monkeypatch.setattr(s, "oidc_issuer", ISSUER)
    monkeypatch.setattr(s, "oidc_audience", CLIENT)
    monkeypatch.setattr("voiceos.auth.oidc.signing_key", lambda issuer, token: KEY.public_key())


def token(sub="google-123", email="staff-a@example.invalid", verified=True, key=KEY, **over):
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": CLIENT,
        "sub": sub,
        "email": email,
        "email_verified": verified,
        "iat": now,
        "exp": now + 600,
        "name": "Nhân viên A",
        **over,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def bearer(t):
    return {"Authorization": f"Bearer {t}"}


def test_invited_email_binds_identity_on_first_login(client, session_factory):
    r = client.get("/api/v1/me", headers=bearer(token()))
    assert r.status_code == 200 and r.json()["display_name"] == "Nhân viên A" and r.json()["role"] == "staff"
    with session_factory() as s:
        u = s.get(User, USER_STAFF_A)
        assert (u.oidc_issuer, u.oidc_subject) == (ISSUER, "google-123") and u.last_login_at
    # later logins match on (issuer, subject), even if the provider email changes
    assert client.get("/api/v1/me", headers=bearer(token(email="new@example.com"))).status_code == 200


def test_rejections(client):
    cases = {
        "wrong audience": token(aud="someone-else"),
        "expired": token(exp=int(time.time()) - 120, iat=int(time.time()) - 900),
        "other key": token(key=OTHER_KEY),
        "wrong issuer": token(iss="https://evil.example"),
    }
    for name, t in cases.items():
        assert client.get("/api/v1/me", headers=bearer(t)).status_code == 401, name
    unsigned = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT, "sub": "x", "iat": int(time.time()), "exp": int(time.time()) + 60},
        key=None,
        algorithm="none",
    )
    assert client.get("/api/v1/me", headers=bearer(unsigned)).status_code == 401
    shared_secret = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT, "sub": "x", "iat": int(time.time()), "exp": int(time.time()) + 60},
        "secret",
        algorithm="HS256",
    )
    assert client.get("/api/v1/me", headers=bearer(shared_secret)).status_code == 401


def test_unverified_or_uninvited_email(client):
    r = client.get("/api/v1/me", headers=bearer(token(verified=False)))
    assert r.status_code == 403 and r.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    r = client.get("/api/v1/me", headers=bearer(token(sub="x", email="stranger@example.com")))
    assert r.status_code == 403 and r.json()["error"]["code"] == "NOT_INVITED"


def test_bound_email_cannot_be_claimed_by_another_identity(client):
    assert client.get("/api/v1/me", headers=bearer(token(sub="google-123"))).status_code == 200
    r = client.get("/api/v1/me", headers=bearer(token(sub="attacker-999")))
    assert r.status_code == 403 and r.json()["error"]["code"] == "IDENTITY_MISMATCH"


def test_dev_token_refused_outside_dev(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    assert client.get("/api/v1/me", headers=ADMIN_A).status_code == 401


# --- member management ---


def test_invite_then_login(client):
    r = client.post(
        "/api/v1/admin/members",
        json={"email": "Moi@Example.com", "display_name": "Người mới", "role": "manager"},
        headers=ADMIN_A,
    )
    assert r.status_code == 201 and r.json()["data"]["status"] == "invited"
    assert (
        client.post(
            "/api/v1/admin/members",
            json={"email": "moi@example.com", "display_name": "x"},
            headers=ADMIN_A,
        ).status_code
        == 409
    )
    me = client.get("/api/v1/me", headers=bearer(token(sub="ms-1", email="moi@example.com")))
    assert me.status_code == 200 and me.json()["role"] == "manager"
    listed = {m["email"]: m for m in client.get("/api/v1/admin/members", headers=ADMIN_A).json()["items"]}
    assert listed["moi@example.com"]["status"] == "active"


def test_only_admins_manage_members(client):
    assert client.get("/api/v1/admin/members", headers=STAFF_A).status_code == 403
    r = client.post(
        "/api/v1/admin/members", json={"email": "x@example.com", "display_name": "x"}, headers=STAFF_A
    )
    assert r.status_code == 403


def test_owner_grants_are_owner_only(client):
    r = client.post(
        "/api/v1/admin/members",
        json={"email": "o@example.com", "display_name": "o", "role": "owner"},
        headers=ADMIN_A,
    )
    assert r.status_code == 403 and r.json()["error"]["code"] == "OWNER_ONLY"


def test_last_admin_and_self_guards(client):
    assert (
        client.patch(
            f"/api/v1/admin/members/{USER_ADMIN_A}", json={"role": "staff"}, headers=ADMIN_A
        ).status_code
        == 409
    )  # self change
    assert client.delete(f"/api/v1/admin/members/{USER_ADMIN_A}", headers=ADMIN_A).status_code == 409
    # promote staff to admin, then demoting the other admin is allowed but not the last one
    assert (
        client.patch(
            f"/api/v1/admin/members/{USER_STAFF_A}", json={"role": "admin"}, headers=ADMIN_A
        ).status_code
        == 200
    )
    staff_as_admin = {"Authorization": f"Bearer dev:{USER_STAFF_A}"}
    assert (
        client.patch(
            f"/api/v1/admin/members/{USER_ADMIN_A}", json={"role": "manager"}, headers=staff_as_admin
        ).status_code
        == 200
    )
    r = client.patch(
        f"/api/v1/admin/members/{USER_STAFF_A}",
        json={"role": "staff"},
        headers={"Authorization": f"Bearer dev:{USER_ADMIN_A}"},
    )
    assert r.status_code == 403  # USER_ADMIN_A is now a manager


def test_remove_member_releases_open_tasks(client, session_factory):
    t = client.post(
        "/api/v1/tasks",
        json={"type": "callback", "title": "gọi lại", "owner_id": str(USER_STAFF_A)},
        headers={**ADMIN_A, "Idempotency-Key": "rm"},
    ).json()["data"]
    r = client.delete(f"/api/v1/admin/members/{USER_STAFF_A}", headers=ADMIN_A)
    assert r.status_code == 200 and r.json()["released_tasks"] == 1
    with session_factory() as s:
        assert s.query(Membership).filter_by(tenant_id=TENANT_A, user_id=USER_STAFF_A).count() == 0
        task = s.get(Task, __import__("uuid").UUID(t["id"]))
        assert task.owner_id is None and task.status == "new"
    assert client.get("/api/v1/me", headers=STAFF_A).status_code == 403  # no membership left
