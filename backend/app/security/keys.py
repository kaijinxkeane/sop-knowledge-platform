"""Server secrets derived from SOP_SECRET_KEY (never from the repository)."""

from __future__ import annotations

import base64
import logging
import secrets
from functools import lru_cache

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings

log = logging.getLogger("sop.security")
_DEV_FALLBACK = secrets.token_urlsafe(48)
MIN_KEY_LENGTH = 32


class SecretKeyError(RuntimeError):
    pass


def master_key() -> str:
    settings = get_settings()
    if settings.secret_key is not None:
        key = settings.secret_key.get_secret_value()
        if len(key) < MIN_KEY_LENGTH:
            raise SecretKeyError(f"SOP_SECRET_KEY must be at least {MIN_KEY_LENGTH} characters")
        return key
    if settings.environment != "development":
        raise SecretKeyError("SOP_SECRET_KEY must be set outside development")
    _warn_dev_key()
    return _DEV_FALLBACK


@lru_cache(maxsize=1)
def _warn_dev_key() -> None:
    log.warning(
        "dev_secret_key",
        extra={
            "fields": {
                "detail": "SOP_SECRET_KEY unset; sessions and TOTP enrolments are lost on restart"
            }
        },
    )


def _derive(purpose: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=purpose).derive(
        master_key().encode()
    )


def jwt_key() -> bytes:
    return _derive(b"sop-jwt-v1")


def totp_cipher() -> Fernet:
    """Encrypts TOTP secrets at rest."""
    return Fernet(base64.urlsafe_b64encode(_derive(b"sop-totp-v1")))
