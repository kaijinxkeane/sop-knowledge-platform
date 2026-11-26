"""Library folders: each department arranges its own documents.

- contributors make folders inside their own department only
- a document moves only within its department, and only where its access
  stays exactly the same (never into restricted Commercial/, never into HR)
- it keeps its identity: approval, versions and past versions still work
- folder names are shown only to the department or to readers of what's inside
"""

from sqlalchemy import select

from app.db.models import AuditEvent, Document

API = "/api/v1/library"
SOP = "Programmes/Signature Personal Brand Programme/01 Discovery/Discovery Workshop SOP.md"
CORE_STAFF = ("employee", "core-staff")
HR_STAFF = ("employee", "hr-staff")


async def _doc(sessions, path=SOP) -> Document:
    async with sessions() as s:
        return (await s.execute(select(Document).where(Document.vault_path == path))).scalar_one()


async def test_contributors_make_folders_in_their_own_department(
    indexed, client, make_user, sign_in
):
    core = await sign_in(await make_user(roles=CORE_STAFF))
    new = {"space": "core", "parent": "Programmes", "name": "New Starter Training"}
    r = await client.post(f"{API}/folders", json=new, headers=core)
    assert r.status_code == 201, r.text
    assert r.json()["path"] == "Programmes/New Starter Training"
    assert (await client.post(f"{API}/folders", json=new, headers=core)).status_code == 409

    # Another department's folder, or another department altogether: refused.
    into_hr = {"space": "core", "parent": "HR", "name": "Mine"}
    assert (await client.post(f"{API}/folders", json=into_hr, headers=core)).status_code == 422
    hr_space = {"space": "hr", "parent": "HR", "name": "Mine"}
    assert (await client.post(f"{API}/folders", json=hr_space, headers=core)).status_code == 403
    for bad in ("../x", ".hidden", "a/b"):
        body = {"space": "core", "parent": "Programmes", "name": bad}
        assert (await client.post(f"{API}/folders", json=body, headers=core)).status_code == 422

    listed = {f["path"] for f in (await client.get(f"{API}/folders", headers=core)).json()}
    assert "Programmes/New Starter Training" in listed
    assert not any(p.startswith("HR") for p in listed)
    hr = await sign_in(await make_user(roles=HR_STAFF))
    hr_listed = {f["path"] for f in (await client.get(f"{API}/folders", headers=hr)).json()}
    assert "Programmes/New Starter Training" not in hr_listed  # nothing of theirs inside
    assert "HR" in hr_listed


async def test_moving_keeps_identity_approval_and_history(
    indexed, client, sessions, vault, make_user, sign_in
):
    before = await _doc(sessions)
    assert before.approved_hash
    core = await sign_in(await make_user(roles=CORE_STAFF))
    body = {"space": "core", "parent": "Programmes", "name": "Discovery"}
    assert (await client.post(f"{API}/folders", json=body, headers=core)).status_code == 201
    r = await client.post(
        f"{API}/documents/{before.id}/move", json={"folder": "Programmes/Discovery"}, headers=core
    )
    assert r.status_code == 200, r.text
    moved = "Programmes/Discovery/Discovery Workshop SOP.md"
    assert r.json() == {"id": str(before.id), "vault_path": moved}

    after = await _doc(sessions, moved)
    assert after.id == before.id
    assert after.approved_hash == before.approved_hash  # still approved, still cited
    assert vault.safe_path(moved).exists() and not vault.safe_path(SOP).exists()
    assert "SOP-User:" in vault._git("log", "-1", "--format=%B")

    versions = (await client.get(f"/api/v1/documents/{before.id}/versions", headers=core)).json()
    oldest = versions[-1]["commit"]
    old = await client.get(f"/api/v1/documents/{before.id}/versions/{oldest}", headers=core)
    assert old.status_code == 200, old.text  # the version from before the move
    async with sessions() as s:
        ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "document_moved"))
        ).scalar_one()
        assert ev.target_id == str(before.id)


async def test_documents_never_move_across_departments_or_access(
    indexed, client, sessions, make_user, sign_in
):
    doc = await _doc(sessions)
    lead = await sign_in(await make_user(roles=("employee", "core-lead")))

    async def move(folder, h=lead):
        return await client.post(
            f"{API}/documents/{doc.id}/move", json={"folder": folder}, headers=h
        )

    assert (await move("HR")).status_code == 422  # another department
    assert (await move("Help")).status_code == 422  # the built-in guide
    assert (await move("Handovers/core")).status_code == 422
    assert (await move("Commercial")).status_code == 409  # restricted: who can read it changes
    reader = await sign_in(await make_user(roles=("employee",)))
    assert (await move("Programmes", reader)).status_code == 404  # can't read it at all
    hr = await sign_in(await make_user(roles=HR_STAFF))
    assert (await move("Programmes", hr)).status_code == 404
    assert (await _doc(sessions)).vault_path == SOP


async def test_only_empty_app_folders_can_be_removed(indexed, client, sessions, make_user, sign_in):
    core = await sign_in(await make_user(roles=CORE_STAFF))
    body = {"space": "core", "parent": "Programmes", "name": "Holding"}
    folder = (await client.post(f"{API}/folders", json=body, headers=core)).json()
    doc = await _doc(sessions)
    lead = await sign_in(await make_user(roles=("employee", "core-lead")))
    await client.post(
        f"{API}/documents/{doc.id}/move", json={"folder": "Programmes/Holding"}, headers=lead
    )
    assert (await client.delete(f"{API}/folders/{folder['id']}", headers=core)).status_code == 409
    await client.post(
        f"{API}/documents/{doc.id}/move",
        json={"folder": "Programmes/Signature Personal Brand Programme/01 Discovery"},
        headers=lead,
    )
    assert (await client.delete(f"{API}/folders/{folder['id']}", headers=core)).status_code == 204


async def test_arranging_a_programme_stage(indexed, sessions, client, make_user, sign_in):
    stage_dir = "Programmes/Signature Personal Brand Programme/01 Discovery/"
    async with sessions() as s:
        docs = (
            (await s.execute(select(Document).where(Document.vault_path.like(stage_dir + "%"))))
            .scalars()
            .all()
        )
    notes = [d for d in docs if d.kind == "note"]
    assert len(notes) >= 2
    programme, stage = notes[0].programme, notes[0].stage
    ids = [str(d.id) for d in reversed(notes)]
    body = {"programme": programme, "stage": stage, "document_ids": ids}
    url = f"{API}/order"

    staff = await sign_in(await make_user(roles=CORE_STAFF))
    r = await client.put(url, json=body, headers=staff)
    assert r.status_code == 204, r.text
    got = {o["document_id"]: o["position"] for o in (await client.get(url, headers=staff)).json()}
    assert sorted(ids, key=got.get) == ids

    # Can't see them: nothing to arrange, and their positions aren't listed.
    for roles in (("employee",), HR_STAFF):
        h = await sign_in(await make_user(roles=roles))
        assert (await client.put(url, json=body, headers=h)).status_code == 404
        listed = {o["document_id"] for o in (await client.get(url, headers=h)).json()}
        assert not listed & set(ids)
    # Wrong stage for the documents: refused.
    wrong = {**body, "stage": "delivery"}
    assert (await client.put(url, json=wrong, headers=staff)).status_code == 422
    async with sessions() as s:
        ev = (
            await s.execute(select(AuditEvent).where(AuditEvent.action == "programme_arranged"))
        ).scalar()
        assert ev.details == {"documents": len(ids)}


async def test_arranging_keeps_the_place_of_documents_you_cannot_see(
    indexed, sessions, client, make_user, sign_in
):
    async with sessions() as s, s.begin():
        stages: dict = {}
        for d in (await s.execute(select(Document).order_by(Document.vault_path))).scalars():
            owner = next((x.space for x in d.access if x.role == "owner"), None)
            if d.kind == "note" and d.programme and owner == "core":
                stages.setdefault((d.programme, d.stage), []).append(d)
        notes = next(ds for ds in stages.values() if len(ds) >= 3)[:3]
        hidden = notes[0]
        for a in hidden.access:  # only the lead can read it now
            a.sensitivity = "restricted"
    a, b, c = (str(d.id) for d in notes)
    programme, stage = notes[0].programme, notes[0].stage
    url = f"{API}/order"
    lead = await sign_in(await make_user(roles=("employee", "core-lead")))
    staff = await sign_in(await make_user(roles=CORE_STAFF))

    body = {"programme": programme, "stage": stage, "document_ids": [a, b, c]}
    assert (await client.put(url, json=body, headers=lead)).status_code == 204
    # Staff can't see the first one; they swap the other two.
    body = {"programme": programme, "stage": stage, "document_ids": [c, b]}
    assert (await client.put(url, json=body, headers=staff)).status_code == 204

    got = {o["document_id"]: o["position"] for o in (await client.get(url, headers=lead)).json()}
    assert len({got[a], got[b], got[c]}) == 3, got  # no two share a place
    assert sorted([a, b, c], key=got.get) == [a, c, b]


async def test_an_empty_folder_with_an_underscore_can_be_removed(
    indexed, client, make_user, sign_in
):
    # "_" is a LIKE wildcard: "Signature_Personal…" must not count the documents
    # in "Signature Personal…" as its own.
    core = await sign_in(await make_user(roles=CORE_STAFF))
    body = {"space": "core", "parent": "Programmes", "name": "Signature_Personal Brand Programme"}
    r = await client.post(f"{API}/folders", json=body, headers=core)
    assert r.status_code == 201, r.text
    gone = await client.delete(f"{API}/folders/{r.json()['id']}", headers=core)
    assert gone.status_code == 204, gone.text
