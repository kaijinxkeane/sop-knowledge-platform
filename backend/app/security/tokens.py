"""Short-lived signed tokens (JWT) and opaque refresh tokens.

Access tokens carry only the user id: permissions are looked up per request.
Purpose tokens bridge the sign-in steps (password -> TOTP) and expire quickly.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from app.security.keys import jwt_key

ALGORITHM = "HS256"
ACCESS = "access"
MFA = "mfa"  # password ok, TOTP code still needed
ENROLL = "totp_enroll"  # password ok, TOTP not set up yet
PURPOSE_MINUTES = 10


class TokenError(Exception):
    pass


def _encode(user_id: uuid.UUID, typ: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": str(user_id),
        "typ": typ,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, jwt_key(), algorithm=ALGORITHM)


def create_access_token(user_id: uuid.UUID) -> tuple[str, int]:
    minutes = get_settings().access_token_minutes
    return _encode(user_id, ACCESS, timedelta(minutes=minutes)), minutes * 60


def create_purpose_token(user_id: uuid.UUID, typ: str) -> str:
    return _encode(user_id, typ, timedelta(minutes=PURPOSE_MINUTES))


def decode(token: str, expected_typ: str) -> uuid.UUID:
    try:
        claims = jwt.decode(
            token, jwt_key(), algorithms=[ALGORITHM], options={"require": ["exp", "sub", "typ"]}
        )
    except jwt.PyJWTError as exc:
        raise TokenError(type(exc).__name__) from None
    if claims.get("typ") != expected_typ:
        raise TokenError("wrong token type")
    try:
        return uuid.UUID(claims["sub"])
    except ValueError:
        raise TokenError("bad subject") from None


def new_opaque_token() -> tuple[str, str]:
    """(token for the client, sha256 hash to store). Only the hash is kept."""
    token = secrets.token_urlsafe(32)
    return token, hash_opaque(token)


def hash_opaque(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
