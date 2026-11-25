"""Sign-in end to end: invite, password, mandatory TOTP, refresh rotation, lockout."""

import logging

import pyotp
from sqlalchemy import select

from app.db.models import AuditEvent
from app.identity import create_user
from tests.db.conftest import PASSWORD

API = "/api/v1"


async def test_invite_to_first_sign_in(client, sessions):
    async with sessions() as s:
        _, invite = await create_user(
            s,
            email="New.Person@Example.com",
            display_name="New",
            role_names=["employee", "core-staff"],
            home_space="core",
            actor_id=None,
        )
        await s.commit()

    # Before the invite is accepted there is no password: sign-in fails generically.
    r = await client.post(
        f"{API}/auth/login", json={"email": "new.person@example.com", "password": PASSWORD}
    )
    assert r.status_code == 401

    r = await client.post(f"{API}/auth/invite/accept", json={"token": invite, "password": "short"})
    assert r.status_code == 422
    r = await client.post(f"{API}/auth/invite/accept", json={"token": invite, "password": PASSWORD})
    assert r.status_code == 204
    r = await client.post(f"{API}/auth/invite/accept", json={"token": invite, "password": PASSWORD})
    assert r.status_code == 400  # one-time

    # Email is case-insensitive. TOTP isn't set up yet, so enrolment is required.
    r = await client.post(
        f"{API}/auth/login", json={"email": "NEW.person@example.com", "password": PASSWORD}
    )
    assert r.json()["status"] == "totp_enrollment_required"
    enroll_token = r.json()["token"]

    # The enrolment token is not an access token.
    assert (
        await client.get(f"{API}/me", headers={"Authorization": f"Bearer {enroll_token}"})
    ).status_code == 401

    r = await client.post(f"{API}/auth/totp/enroll", json={"token": enroll_token})
    secret = r.json()["secret"]
    assert r.json()["otpauth_uri"].startswith("otpauth://totp/")
    r = await client.post(
        f"{API}/auth/totp/enroll/confirm", json={"token": enroll_token, "code": "000000"}
    )
    assert r.status_code == 401
    r = await client.post(
        f"{API}/auth/totp/enroll/confirm",
        json={"token": enroll_token, "code": pyotp.TOTP(secret).now()},
    )
    assert r.status_code == 200
    assert "sop_refresh" in r.headers["set-cookie"] and "HttpOnly" in r.headers["set-cookie"]
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = (await client.get(f"{API}/me", headers=headers)).json()
    assert me["email"] == "new.person@example.com"
    assert me["scopes"] == {"core": "internal", "hr": "public", "it": "public"}
    assert me["space_actions"]["core"] == ["ask", "contribute"]
    assert me["notice"]["acknowledged"] is False


async def test_totp_code_cannot_be_replayed(client, make_user):
    person = await make_user()
    code = pyotp.TOTP(person.secret).now()
    for expected in (200, 401):
        r = await client.post(
            f"{API}/auth/login", json={"email": person.email, "password": PASSWORD}
        )
        r = await client.post(
            f"{API}/auth/totp/verify", json={"token": r.json()["token"], "code": code}
        )
        assert r.status_code == expected


async def test_wrong_password_locks_the_account(client, make_user, sessions):
    person = await make_user()
    for _ in range(5):
        r = await client.post(
            f"{API}/auth/login", json={"email": person.email, "password": "wrong-password-123"}
        )
        assert r.status_code == 401
    r = await client.post(f"{API}/auth/login", json={"email": person.email, "password": PASSWORD})
    assert r.status_code == 429  # locked, even with the right password
    async with sessions() as s:
        actions = list((await s.execute(select(AuditEvent.action))).scalars())
    assert actions.count("login_failed") == 5 and "account_locked" in actions


async def test_unknown_email_and_wrong_password_look_the_same(client, make_user):
    person = await make_user()
    a = await client.post(
        f"{API}/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    b = await client.post(
        f"{API}/auth/login", json={"email": person.email, "password": "wrong-password-123"}
    )
    assert (a.status_code, a.json()) == (b.status_code, b.json())


async def test_refresh_rotates_and_reuse_ends_the_session(client, make_user, sign_in):
    person = await make_user()
    await sign_in(person)
    first = client.cookies.get("sop_refresh")

    r = await client.post(f"{API}/auth/refresh")
    assert r.status_code == 200
    second = client.cookies.get("sop_refresh")
    assert second and second != first

    # Replaying the old cookie (e.g. stolen) revokes the whole family...
    client.cookies.set("sop_refresh", first, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401
    # ...so the newer token stops working too.
    client.cookies.set("sop_refresh", second, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_logout_revokes_refresh(client, make_user, sign_in):
    person = await make_user()
    await sign_in(person)
    token = client.cookies.get("sop_refresh")
    assert (await client.post(f"{API}/auth/logout")).status_code == 204
    client.cookies.set("sop_refresh", token, path="/api/v1/auth")
    assert (await client.post(f"{API}/auth/refresh")).status_code == 401


async def test_unenrolled_user_never_gets_an_access_token(client, make_user):
    person = await make_user(enrolled=False)
    r = await client.post(f"{API}/auth/login", json={"email": person.email, "password": PASSWORD})
    assert r.json()["status"] == "totp_enrollment_required"
    r = await client.post(
        f"{API}/auth/totp/verify", json={"token": r.json()["token"], "code": "123456"}
    )
    assert r.status_code == 401


async def test_notice_acknowledgement(client, make_user, sign_in):
    headers = await sign_in(await make_user())
    notice = (await client.get(f"{API}/notice", headers=headers)).json()
    assert "24 months" in notice["markdown"] and not notice["acknowledged"]
    r = await client.post(f"{API}/notice/acknowledge", headers=headers, json={"version": "old"})
    assert r.status_code == 409
    r = await client.post(
        f"{API}/notice/acknowledge", headers=headers, json={"version": notice["version"]}
    )
    assert r.status_code == 204
    assert (await client.get(f"{API}/me", headers=headers)).json()["notice"]["acknowledged"]


async def test_sign_in_logs_contain_no_credentials(client, make_user, caplog):
    person = await make_user()
    with caplog.at_level(logging.DEBUG):
        await client.post(
            f"{API}/auth/login", json={"email": person.email, "password": "wrong-password-123"}
        )
        await client.post(f"{API}/auth/login", json={"email": person.email, "password": PASSWORD})
    logged = " ".join(r.getMessage() + repr(getattr(r, "fields", "")) for r in caplog.records)
    assert person.email not in logged and PASSWORD not in logged
    assert "wrong-password-123" not in logged


async def test_demo_accounts_skip_the_code_only_in_development(client, make_user, monkeypatch):
    from app.config import get_settings

    demo = await make_user(email="sam.lee@staff.example.com")
    other = await make_user()
    login = {"email": demo.email, "password": PASSWORD}

    # Switch off (the default): a demo account still needs its code.
    r = await client.post(f"{API}/auth/login", json=login)
    assert r.json()["status"] == "totp_required"

    monkeypatch.setenv("SOP_DEMO_SKIP_2FA", "true")
    get_settings.cache_clear()
    r = await client.post(f"{API}/auth/login", json=login)
    assert r.status_code == 200 and r.json()["status"] == "signed_in"
    assert "sop_refresh" in r.cookies
    me = await client.get(f"{API}/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.status_code == 200 and me.json()["email"] == demo.email

    # Everyone else still needs a code, and a wrong password still fails.
    r = await client.post(f"{API}/auth/login", json={"email": other.email, "password": PASSWORD})
    assert r.json()["status"] == "totp_required"
    r = await client.post(f"{API}/auth/login", json={**login, "password": "wrong"})
    assert r.status_code == 401


async def test_demo_sign_in_without_a_code_is_audited(client, make_user, sessions, monkeypatch):
    from app.config import get_settings

    demo = await make_user(email="casey.wong@staff.example.com")
    monkeypatch.setenv("SOP_DEMO_SKIP_2FA", "true")
    get_settings.cache_clear()
    await client.post(f"{API}/auth/login", json={"email": demo.email, "password": PASSWORD})
    async with sessions() as s:
        event = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "login_succeeded"))
        ).scalar_one()
    assert event.details == {"method": "demo_no_code"}
