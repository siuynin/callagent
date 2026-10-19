"""OIDC ID token verification (ADR 0008).

The web app (BFF) completes the authorization code + PKCE flow and forwards the ID token; the backend
verifies signature, issuer, audience and expiry against the provider's published keys. Only asymmetric
algorithms are accepted, so a token signed with "none" or a shared secret can never pass.
"""

import time
from dataclasses import dataclass
from functools import lru_cache

import httpx
import jwt

ALGORITHMS = ["RS256", "RS384", "RS512", "ES256", "ES384", "PS256"]
LEEWAY_S = 30


class TokenError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Identity:
    issuer: str
    subject: str
    email: str | None
    email_verified: bool
    name: str | None


@lru_cache(maxsize=8)
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    try:
        meta = httpx.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration", timeout=5).json()
        return jwt.PyJWKClient(meta["jwks_uri"], cache_keys=True, lifespan=600)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise TokenError(
            "OIDC_UNAVAILABLE", f"Không đọc được cấu hình nhà cung cấp đăng nhập: {exc}"
        ) from exc


def signing_key(issuer: str, token: str):
    """Separate function so tests can swap in a local key."""
    try:
        return _jwks_client(issuer).get_signing_key_from_jwt(token).key
    except jwt.PyJWKClientError as exc:
        raise TokenError("INVALID_TOKEN", f"Không tìm thấy khóa ký: {exc}") from exc


def verify_id_token(token: str, *, issuer: str, audience: str) -> Identity:
    if not issuer or not audience:
        raise TokenError("OIDC_DISABLED", "Chưa cấu hình đăng nhập OIDC")
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise TokenError("INVALID_TOKEN", "Token không hợp lệ") from exc
    if header.get("alg") not in ALGORITHMS:
        raise TokenError("INVALID_TOKEN", "Thuật toán ký không được chấp nhận")
    try:
        claims = jwt.decode(
            token,
            signing_key(issuer, token),
            algorithms=ALGORITHMS,
            audience=audience,
            issuer=issuer,
            leeway=LEEWAY_S,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("TOKEN_EXPIRED", "Phiên đăng nhập đã hết hạn") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("INVALID_TOKEN", f"Token không hợp lệ: {exc}") from exc
    if claims["iat"] > time.time() + LEEWAY_S:
        raise TokenError("INVALID_TOKEN", "Token phát hành trong tương lai")
    return Identity(
        issuer=claims["iss"],
        subject=str(claims["sub"]),
        email=(claims.get("email") or "").lower() or None,
        email_verified=claims.get("email_verified") is True,
        name=claims.get("name"),
    )
