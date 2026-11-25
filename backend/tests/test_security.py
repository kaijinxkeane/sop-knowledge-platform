"""Passwords, TOTP (incl. replay), signed tokens and secret handling."""

import time
import uuid

import pyotp
import pytest

from app.security import passwords, totp
from app.security.keys import SecretKeyError, master_key
from app.security.tokens import (
    ACCESS,
    MFA,
    TokenError,
    create_access_token,
    create_purpose_token,
    decode,
    hash_opaque,
    new_opaque_token,
)


def test_password_hash_and_verify():
    h = passwords.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "correct horse battery")
    assert not passwords.verify_password(h, "wrong horse battery")
    assert not passwords.verify_password(None, "anything at all")  # unknown user path


@pytest.mark.parametrize("pw", ["short", "aaaaaaaaaaaaaaaa", " leading-space-password"])
def test_password_policy(pw):
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.hash_password(pw)


def test_totp_accepts_drift_and_rejects_replay():
    secret = totp.new_secret()
    now = time.time()
    code = pyotp.TOTP(secret).at(now)
    step = totp.verify_code(secret, code, None, now=now)
    assert step == int(now // 30)
    assert totp.verify_code(secret, code, step, now=now) is None  # replay
    nxt = pyotp.TOTP(secret).at(now + 30)
    assert totp.verify_code(secret, nxt, step, now=now) == step + 1  # one step of drift
    assert totp.verify_code(secret, pyotp.TOTP(secret).at(now + 120), None, now=now) is None
    assert totp.verify_code(secret, "12345", None, now=now) is None
    assert totp.verify_code(secret, "abcdef", None, now=now) is None


def test_totp_secret_encrypted_at_rest():
    secret = totp.new_secret()
    enc = totp.encrypt_secret(secret)
    assert secret not in enc and totp.decrypt_secret(enc) == secret


def test_tokens_are_typed_and_signed():
    uid = uuid.uuid4()
    access, expires_in = create_access_token(uid)
    assert decode(access, ACCESS) == uid and expires_in == 15 * 60
    with pytest.raises(TokenError):
        decode(access, MFA)  # an access token can't stand in for a sign-in step
    with pytest.raises(TokenError):
        decode(create_purpose_token(uid, MFA), ACCESS)
    with pytest.raises(TokenError):
        decode(access[:-2] + ("A" if access[-1] != "A" else "B") + access[-1], ACCESS)


def test_opaque_tokens_store_only_a_hash():
    token, digest = new_opaque_token()
    assert len(token) >= 40 and digest == hash_opaque(token) and token not in digest


def test_secret_key_required_outside_development(monkeypatch):
    from app.config import get_settings

    monkeypatch.delenv("SOP_SECRET_KEY", raising=False)
    monkeypatch.setenv("SOP_ENV", "production")
    get_settings.cache_clear()
    monkeypatch.setattr(get_settings(), "secret_key", None)
    with pytest.raises(SecretKeyError):
        master_key()


def test_short_secret_key_rejected(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("SOP_SECRET_KEY", "too-short")
    get_settings.cache_clear()
    with pytest.raises(SecretKeyError, match="at least"):
        master_key()


@pytest.mark.parametrize("env", ["production", "staging", "test"])
def test_demo_sign_in_without_codes_is_refused_outside_development(monkeypatch, env):
    from app.config import get_settings

    monkeypatch.setenv("SOP_ENV", env)
    monkeypatch.setenv("SOP_DEMO_SKIP_2FA", "true")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="only allowed with SOP_ENV=development"):
        get_settings()


def test_demo_switch_never_covers_other_accounts(monkeypatch):
    from app.config import get_settings
    from app.demo import skips_two_factor

    monkeypatch.setenv("SOP_ENV", "development")
    monkeypatch.setenv("SOP_DEMO_SKIP_2FA", "true")
    get_settings.cache_clear()
    assert skips_two_factor("Sam.Lee@staff.example.com")
    assert not skips_two_factor("chiangkaijin@gmail.com")
    assert not skips_two_factor("someone@staff.example.com")
