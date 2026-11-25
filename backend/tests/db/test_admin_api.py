"""Admin endpoints: permission checks, grant safety, last-admin protection, audit."""

import json

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.audit import verify_chain
from app.db.models import AuditEvent

API = "/api/v1/admin"


@pytest.fixture
async def admin(make_user, sign_in):
    person = await make_user(email="admin@example.com", roles=("employee", "platform-admin"))
    return person, await sign_in(person)


async def test_non_admins_are_refused(client, make_user, sign_in):
    headers = await sign_in(await make_user(roles=("employee", "core-lead")))
    for path in ("/users", "/roles", "/audit", "/options"):
        assert (await client.get(API + path, headers=headers)).status_code == 403
    assert (await client.get(API + "/users")).status_code == 401


async def test_options_list_every_space_and_action(client, admin):
    _, h = admin
    body = (await client.get(API + "/options", headers=h)).json()
    assert {"core", "it", "hr"} <= {sp["name"] for sp in body["spaces"]}
    assert "approve" in body["space_actions"] and "manage_users" in body["global_actions"]
    assert body["sensitivities"] == ["public", "internal", "restricted"]


async def test_create_user_returns_one_time_invite(client, admin):
    _, h = admin
    r = await client.post(
        f"{API}/users",
        headers=h,
        json={
            "email": "trainer@example.com",
            "display_name": "Trainer",
            "roles": ["employee", "core-staff"],
            "home_space": "core",
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["invite_token"] and body["user"]["invite_pending"]
    assert body["user"]["roles"] == ["core-staff", "employee"]
    dup = await client.post(
        f"{API}/users", headers=h, json={"email": "TRAINER@example.com", "display_name": "Again"}
    )
    assert dup.status_code == 409
    bad = await client.post(
        f"{API}/users",
        headers=h,
        json={"email": "x@example.com", "display_name": "X", "home_space": "finance"},
    )
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "grant",
    [
        {"space": None, "max_sensitivity": "restricted", "actions": ["ask"]},
        {"space": "core", "actions": ["manage_users"]},
        {"space": "finance", "actions": ["ask"]},
        {"space": "core", "max_sensitivity": "secret", "actions": ["ask"]},
    ],
)
async def test_unsafe_grants_are_rejected(client, admin, grant):
    _, h = admin
    r = await client.post(f"{API}/roles", headers=h, json={"name": "test-role", "grants": [grant]})
    assert r.status_code == 422


async def test_role_changes_apply_on_the_next_request(client, admin, make_user, sign_in):
    _, h = admin
    staff = await make_user(roles=("employee",))
    sh = await sign_in(staff)
    assert (await client.get("/api/v1/me", headers=sh)).json()["scopes"]["core"] == "public"
    r = await client.patch(
        f"{API}/users/{staff.user.id}", headers=h, json={"roles": ["employee", "core-lead"]}
    )
    assert r.status_code == 200
    assert (await client.get("/api/v1/me", headers=sh)).json()["scopes"]["core"] == "restricted"


async def test_deactivation_cuts_access_immediately(client, admin, make_user, sign_in):
    _, h = admin
    staff = await make_user()
    sh = await sign_in(staff)
    await client.patch(f"{API}/users/{staff.user.id}", headers=h, json={"is_active": False})
    assert (await client.get("/api/v1/me", headers=sh)).status_code == 401


async def test_last_admin_is_protected(client, admin):
    person, h = admin
    me = f"{API}/users/{person.user.id}"
    assert (await client.patch(me, headers=h, json={"is_active": False})).status_code == 409
    assert (await client.patch(me, headers=h, json={"roles": ["employee"]})).status_code == 409
    roles = (await client.get(f"{API}/roles", headers=h)).json()
    pa = next(r for r in roles if r["name"] == "platform-admin")
    assert (await client.delete(f"{API}/roles/{pa['id']}", headers=h)).status_code == 409
    gid = pa["grants"][0]["id"]
    assert (await client.delete(f"{API}/grants/{gid}", headers=h)).status_code == 409
    # Still an admin afterwards.
    assert (await client.get(f"{API}/users", headers=h)).status_code == 200


async def test_reset_totp_forces_re_enrolment(client, admin, make_user, sign_in):
    _, h = admin
    staff = await make_user()
    sh = await sign_in(staff)
    r = await client.post(f"{API}/users/{staff.user.id}/reset-totp", headers=h)
    assert r.json()["totp_enabled"] is False
    assert (await client.get("/api/v1/me", headers=sh)).status_code == 401
    r = await client.post(
        "/api/v1/auth/login", json={"email": staff.email, "password": "a-long-test-password"}
    )
    assert r.json()["status"] == "totp_enrollment_required"


async def test_audit_log_is_recorded_viewable_and_verifiable(client, admin, sessions):
    _, h = admin
    await client.post(
        f"{API}/users", headers=h, json={"email": "a@example.com", "display_name": "A"}
    )
    events = (await client.get(f"{API}/audit", headers=h)).json()
    actions = [e["action"] for e in events]
    assert "user_created" in actions and "login_succeeded" in actions
    # Audit rows hold ids, never emails or secrets.
    assert "a@example.com" not in json.dumps(events)
    assert (await client.get(f"{API}/audit/verify", headers=h)).json()["ok"] is True
    async with sessions() as s:
        viewed = (
            (await s.execute(select(AuditEvent).where(AuditEvent.action == "audit_viewed")))
            .scalars()
            .all()
        )
        assert viewed  # viewing the log is itself logged
        rows = (await s.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
        assert verify_chain(rows) == (True, None)


async def test_audit_rows_cannot_be_changed_or_deleted(client, admin, sessions):
    for stmt in ("UPDATE audit_events SET action = 'x'", "DELETE FROM audit_events"):
        async with sessions() as s:
            with pytest.raises(DBAPIError, match="append-only"):
                await s.execute(text(stmt))


async def test_people_picker_gives_names_only(client, admin, make_user, sign_in):
    _, h = admin
    staff = await make_user(email="robin.picker@example.com")
    gone = await make_user(email="robin.gone@example.com")
    await client.patch(f"{API}/users/{gone.user.id}", headers=h, json={"is_active": False})
    me = await make_user()
    mh = await sign_in(me)
    r = await client.get("/api/v1/people", params={"q": "robin"}, headers=mh)
    assert r.status_code == 200
    assert r.json() == [{"id": str(staff.user.id), "name": "robin.picker"}]  # no emails
    everyone = (await client.get("/api/v1/people", headers=mh)).json()
    assert str(me.user.id) not in {p["id"] for p in everyone}
    # Wildcards in the query are ignored, never used as patterns.
    assert (await client.get("/api/v1/people", params={"q": "%"}, headers=mh)).status_code == 200
    assert (await client.get("/api/v1/people")).status_code == 401
