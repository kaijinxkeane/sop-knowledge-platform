"""Sign-in (plan §11): password, then a TOTP code. TOTP is required for everyone.

    POST /auth/login             email + password -> mfa_token | enrollment_token
                                 (development demo accounts with SOP_DEMO_SKIP_2FA:
                                 an access token straight away, see app/demo.py)
    POST /auth/totp/verify       mfa_token + code  -> access token (+ refresh cookie)
    POST /auth/totp/enroll       enrollment_token  -> secret + otpauth URI
    POST /auth/totp/enroll/confirm  enrollment_token + code -> access token
    POST /auth/refresh           refresh cookie    -> new access token (rotated cookie)
    POST /auth/logout            revokes the session
    POST /auth/invite/accept     invite token + new password

Failures return the same message whether the email exists or not.
Passwords, codes and tokens are never logged or audited.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import audit
from app.api.deps import get_db, limit_auth
from app.config import get_settings
from app.db.models import OneTimeToken, RefreshToken, User
from app.demo import skips_two_factor
from app.identity import get_user, get_user_by_email
from app.security import passwords, totp
from app.security.tokens import (
    ENROLL,
    MFA,
    TokenError,
    create_access_token,
    create_purpose_token,
    decode,
    hash_opaque,
    new_opaque_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILED = 5
LOCK_MINUTES = 15
REFRESH_COOKIE = "sop_refresh"
COOKIE_PATH = "/api/v1/auth"
BAD_CREDENTIALS = HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email, password or code")
LOCKED = HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts; try later")


class LoginIn(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(max_length=1024)


class StepOut(BaseModel):
    """Next sign-in step. `signed_in` (development demo accounts only): `token`
    is the access token and the refresh cookie is already set."""

    status: Literal["totp_required", "totp_enrollment_required", "signed_in"]
    token: str
    expires_in: int = 600


class CodeIn(BaseModel):
    token: str
    code: str = Field(max_length=12)


class TokenIn(BaseModel):
    token: str


class EnrollOut(BaseModel):
    secret: str
    otpauth_uri: str


class SessionOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class InviteAcceptIn(BaseModel):
    token: str
    password: str = Field(max_length=1024)


def _now() -> datetime:
    return datetime.now(UTC)


def _locked(user: User) -> bool:
    return user.locked_until is not None and user.locked_until > _now()


async def _fail(session: AsyncSession, user: User, stage: str) -> None:
    user.failed_logins += 1
    details = {"stage": stage, "failed_count": user.failed_logins}
    if user.failed_logins >= MAX_FAILED:
        user.locked_until = _now() + timedelta(minutes=LOCK_MINUTES)
        user.failed_logins = 0
        await audit.record(
            session,
            "account_locked",
            target_type="user",
            target_id=user.id,
            details={"minutes": LOCK_MINUTES},
        )
    await audit.record(
        session, "login_failed", target_type="user", target_id=user.id, details=details
    )
    await session.commit()


async def _user_for_step(session: AsyncSession, token: str, typ: str) -> User:
    try:
        user_id = decode(token, typ)
    except TokenError:
        raise BAD_CREDENTIALS from None
    user = await get_user(session, user_id)
    if user is None or not user.is_active:
        raise BAD_CREDENTIALS
    if _locked(user):
        raise LOCKED
    return user


async def _start_session(
    session: AsyncSession,
    user: User,
    response: Response,
    family_id: uuid.UUID | None = None,
    method: str | None = None,
) -> SessionOut:
    settings = get_settings()
    token, digest = new_opaque_token()
    max_age = settings.refresh_token_days * 86400
    session.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid4(),
            token_hash=digest,
            expires_at=_now() + timedelta(seconds=max_age),
        )
    )
    if family_id is None:
        user.failed_logins = 0
        user.locked_until = None
        user.last_login_at = _now()
        await audit.record(
            session,
            "login_succeeded",
            actor_id=user.id,
            details={"method": method} if method else None,
        )
    await session.commit()
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path=COOKIE_PATH,
    )
    access, expires_in = create_access_token(user.id)
    return SessionOut(access_token=access, expires_in=expires_in)


@router.post("/login", response_model=StepOut, dependencies=[Depends(limit_auth)])
async def login(
    body: LoginIn, response: Response, session: AsyncSession = Depends(get_db)
) -> StepOut:
    user = await get_user_by_email(session, body.email)
    usable = user is not None and user.is_active and user.password_hash is not None
    ok = passwords.verify_password(user.password_hash if usable else None, body.password)
    if not usable:
        raise BAD_CREDENTIALS
    if _locked(user):
        raise LOCKED
    if not ok:
        await _fail(session, user, "password")
        raise BAD_CREDENTIALS
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(body.password)
        await session.commit()
    if skips_two_factor(user.email):
        out = await _start_session(session, user, response, method="demo_no_code")
        return StepOut(status="signed_in", token=out.access_token, expires_in=out.expires_in)
    if user.totp_enabled:
        return StepOut(status="totp_required", token=create_purpose_token(user.id, MFA))
    return StepOut(status="totp_enrollment_required", token=create_purpose_token(user.id, ENROLL))


@router.post("/totp/verify", response_model=SessionOut, dependencies=[Depends(limit_auth)])
async def totp_verify(
    body: CodeIn, response: Response, session: AsyncSession = Depends(get_db)
) -> SessionOut:
    user = await _user_for_step(session, body.token, MFA)
    if not user.totp_enabled or not user.totp_secret_enc:
        raise BAD_CREDENTIALS
    step = totp.verify_code(
        totp.decrypt_secret(user.totp_secret_enc), body.code, user.totp_last_step
    )
    if step is None:
        await _fail(session, user, "totp")
        raise BAD_CREDENTIALS
    user.totp_last_step = step
    return await _start_session(session, user, response)


@router.post("/totp/enroll", response_model=EnrollOut, dependencies=[Depends(limit_auth)])
async def totp_enroll(body: TokenIn, session: AsyncSession = Depends(get_db)) -> EnrollOut:
    user = await _user_for_step(session, body.token, ENROLL)
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "two-factor is already set up")
    secret = totp.new_secret()
    user.totp_secret_enc = totp.encrypt_secret(secret)
    user.totp_last_step = None
    await session.commit()
    return EnrollOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, user.email))


@router.post("/totp/enroll/confirm", response_model=SessionOut, dependencies=[Depends(limit_auth)])
async def totp_enroll_confirm(
    body: CodeIn, response: Response, session: AsyncSession = Depends(get_db)
) -> SessionOut:
    user = await _user_for_step(session, body.token, ENROLL)
    if user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(status.HTTP_409_CONFLICT, "start enrolment first")
    step = totp.verify_code(totp.decrypt_secret(user.totp_secret_enc), body.code, None)
    if step is None:
        await _fail(session, user, "totp_enroll")
        raise BAD_CREDENTIALS
    user.totp_enabled = True
    user.totp_last_step = step
    await audit.record(session, "totp_enrolled", actor_id=user.id)
    return await _start_session(session, user, response)


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    response: Response,
    session: AsyncSession = Depends(get_db),
    sop_refresh: str | None = Cookie(default=None),
) -> SessionOut:
    if not sop_refresh:
        raise BAD_CREDENTIALS
    row = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_opaque(sop_refresh))
        )
    ).scalar_one_or_none()
    if row is None:
        raise BAD_CREDENTIALS
    if row.revoked_at is not None:
        # A rotated token was used again: assume it was stolen; end the whole session.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await audit.record(
            session, "refresh_token_reuse", target_type="user", target_id=row.user_id
        )
        await session.commit()
        response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
        raise BAD_CREDENTIALS
    user = await get_user(session, row.user_id)
    if row.expires_at <= _now() or user is None or not user.is_active or not user.totp_enabled:
        raise BAD_CREDENTIALS
    row.revoked_at = _now()
    return await _start_session(session, user, response, family_id=row.family_id)


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    session: AsyncSession = Depends(get_db),
    sop_refresh: str | None = Cookie(default=None),
) -> Response:
    if sop_refresh:
        row = (
            await session.execute(
                select(RefreshToken).where(RefreshToken.token_hash == hash_opaque(sop_refresh))
            )
        ).scalar_one_or_none()
        if row is not None:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.family_id == row.family_id, RefreshToken.revoked_at.is_(None))
                .values(revoked_at=_now())
            )
            await audit.record(session, "logout", actor_id=row.user_id)
            await session.commit()
    response.status_code = 204
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    return response


@router.post("/invite/accept", status_code=204, dependencies=[Depends(limit_auth)])
async def invite_accept(body: InviteAcceptIn, session: AsyncSession = Depends(get_db)) -> Response:
    row = (
        await session.execute(
            select(OneTimeToken).where(
                OneTimeToken.token_hash == hash_opaque(body.token), OneTimeToken.purpose == "invite"
            )
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this link is invalid or has expired")
    try:
        password_hash = passwords.hash_password(body.password)
    except passwords.PasswordPolicyError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    user = await get_user(session, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "this link is invalid or has expired")
    row.used_at = _now()
    user.password_hash = password_hash
    user.failed_logins, user.locked_until = 0, None
    await audit.record(session, "password_set", actor_id=user.id)
    await session.commit()
    return Response(status_code=204)
