"""Password hashing (Argon2id) and policy."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()
# Verified against when the account doesn't exist, so timing doesn't reveal it.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")
MIN_PASSWORD_LENGTH = 12


class PasswordPolicyError(ValueError):
    pass


def check_policy(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
    if password.strip() != password or len(set(password)) < 4:
        raise PasswordPolicyError("password is too simple")


def hash_password(password: str) -> str:
    check_policy(password)
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
