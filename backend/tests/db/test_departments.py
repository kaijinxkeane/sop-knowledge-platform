"""Departments created in the app (Admin → Departments, `manage_spaces`).

- only the CEO (platform-admin) and HR's lead may create one
- it comes with staff and lead roles that nobody has yet, and public `ask`
  for every employee
- its folder gives notes added in Obsidian to the department, internal: an
  employee can't read them, the department's staff can
- the model gateway, agents and folder rules see it without a restart
- names, folders and roles never clash with what exists
"""

from sqlalchemy import select

from app.db.models import AuditEvent, Role
from app.identity import roles_by_name
from app.models.config import load_gateway_config
from app.spaces import space_profiles
from app.vault.indexer import Indexer
from app.vault.labels import vault_config
from tests.db.conftest import fake_embed

API = "/api/v1/admin/departments"
CEO = ("employee", "core-lead", "platform-admin")
HR_LEAD = ("employee", "hr-staff", "hr-lead")
MARKETING = {
    "title": "Marketing",
    "description": "Campaigns, brand guidelines, social media and events.",
    "contact": "Please contact the marketing team.",
}


async def test_ceo_creates_a_department_with_roles_and_folder(client, sessions, make_user, sign_in):
    h = await sign_in(await make_user(roles=CEO))
    r = await client.post(API, json=MARKETING, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "marketing" and body["folders"] == ["Marketing"]
    assert body["created_in_app"] is True
    assert body["roles"] == ["ceo", "marketing-lead", "marketing-staff"]

    async with sessions() as s:
        roles = {r.name: r for r in (await s.execute(select(Role))).scalars()}
        lead = roles["marketing-lead"].grants[0]
        assert (lead.space, lead.max_sensitivity) == ("marketing", "restricted")
        assert "approve" in lead.actions
        staff = roles["marketing-staff"].grants[0]
        assert (staff.max_sensitivity, sorted(staff.actions)) == ("internal", ["ask", "contribute"])
        employee = [g for g in roles["employee"].grants if g.space == "marketing"]
        assert [(g.max_sensitivity, g.actions) for g in employee] == [("public", ["ask"])]
        # the CEO role writes in every department, up to internal (roles.yaml new_departments)
        ceo = [g for g in roles["ceo"].grants if g.space == "marketing"]
        assert [(g.max_sensitivity, sorted(g.actions)) for g in ceo] == [
            ("internal", ["ask", "contribute"])
        ]
        ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "space_created"))
        ).scalar()
        assert ev.target_id == "marketing"

    assert "marketing" in space_profiles()
    assert space_profiles()["marketing"].contact == MARKETING["contact"]
    rule = next(r for r in vault_config().folder_rules if r.space == "marketing")
    assert (rule.path, rule.sensitivity) == ("Marketing/", "internal")
    from app.config import get_settings

    assert (
        "marketing"
        in load_gateway_config(get_settings().config_dir, {"OLLAMA_BASE_URL": "x"}).spaces
    )

    listed = (await client.get(API, headers=h)).json()
    assert {"core", "hr", "it", "marketing"} <= {d["name"] for d in listed}
    assert next(d for d in listed if d["name"] == "hr")["created_in_app"] is False


async def test_hr_lead_may_create_others_may_not(client, make_user, sign_in):
    staff = await sign_in(await make_user(roles=("employee", "core-staff")))
    assert (await client.post(API, json=MARKETING, headers=staff)).status_code == 403
    assert (await client.get(API, headers=staff)).status_code == 403
    hr = await sign_in(await make_user(roles=HR_LEAD))
    assert (await client.post(API, json=MARKETING, headers=hr)).status_code == 201


async def test_names_and_folders_never_clash(client, make_user, sign_in):
    h = await sign_in(await make_user(roles=CEO))
    assert (await client.post(API, json=MARKETING, headers=h)).status_code == 201
    assert (await client.post(API, json=MARKETING, headers=h)).status_code == 409
    clash_hr = {**MARKETING, "title": "People", "name": "people", "folder": "HR"}
    assert (await client.post(API, json=clash_hr, headers=h)).status_code == 409
    configured = {**MARKETING, "title": "IT", "name": "it", "folder": "Tech"}
    assert (await client.post(API, json=configured, headers=h)).status_code == 409
    for bad in ({"name": "Bad Name"}, {"name": "unclassified"}, {"folder": "../escape"}):
        r = await client.post(API, json={**MARKETING, "title": "Sales", **bad}, headers=h)
        assert r.status_code == 422, bad


async def test_notes_in_the_folder_belong_to_the_department(
    indexed, vault, client, sessions, make_user, sign_in
):
    h = await sign_in(await make_user(roles=CEO))
    assert (await client.post(API, json=MARKETING, headers=h)).status_code == 201
    note = vault.safe_path("Marketing/Launch Checklist.md")
    note.parent.mkdir()
    note.write_text("---\ntitle: Launch Checklist\n---\n\n# Launch Checklist\n\n1. Brief.\n")
    vault._git("add", "-A")
    vault._git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "add")
    await Indexer(vault, sessions, fake_embed).sync()

    def titles(listing):
        return {d["title"] for d in listing.json()}

    employee = await sign_in(await make_user(roles=("employee",)))
    assert "Launch Checklist" not in titles(await client.get("/api/v1/documents", headers=employee))
    async with sessions() as s:
        assert await roles_by_name(s, ["marketing-staff"])
    member = await sign_in(await make_user(roles=("employee", "marketing-staff")))
    assert "Launch Checklist" in titles(await client.get("/api/v1/documents", headers=member))


async def test_the_ceo_writes_in_every_department_but_reads_no_restricted_material(
    indexed, client, make_user, sign_in
):
    """`ceo` (config/roles.yaml) on its own: new notes and edits in Core, IT and HR,
    up to internal; approving stays with each department's lead."""
    h = await sign_in(await make_user(roles=("employee", "ceo")))
    me = (await client.get("/api/v1/me", headers=h)).json()
    for space in ("core", "hr", "it"):
        assert "contribute" in me["space_actions"][space], space
        assert "approve" not in me["space_actions"][space], space
    titles = {d["title"] for d in (await client.get("/api/v1/documents", headers=h)).json()}
    assert "Leave Policy" in titles  # HR internal: readable and editable
    assert "Disciplinary Process" not in titles  # HR restricted: still hidden
    note = {
        "title": "Office keys",
        "space": "hr",
        "sensitivity": "internal",
        "body": "# Office keys\n",
    }
    r = await client.post("/api/v1/notes", json=note, headers=h)
    assert r.status_code == 201, r.text
