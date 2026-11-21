"""TOTP two-factor codes (RFC 6238), with replay protection."""

from __future__ import annotations

import time

import pyotp

from app.security.keys import totp_cipher

ISSUER = "SOP Platform"
STEP_SECONDS = 30


def new_secret() -> str:
    return pyotp.random_base32()


def encrypt_secret(secret: str) -> str:
    return totp_cipher().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    return totp_cipher().decrypt(token.encode()).decode()


def provisioning_uri(secret: str, account_name: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account_name, issuer_name=ISSUER)


def verify_code(
    secret: str, code: str, last_used_step: int | None, *, now: float | None = None
) -> int | None:
    """Return the matched time step, or None.

    Accepts the current step and one step either side (clock drift). A step at
    or before `last_used_step` is rejected, so a code can't be replayed.
    """
    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return None
    now = time.time() if now is None else now
    totp = pyotp.TOTP(secret)
    current = int(now // STEP_SECONDS)
    for step in (current - 1, current, current + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if pyotp.utils.strings_equal(totp.at(step * STEP_SECONDS), code):
            return step
    return None
