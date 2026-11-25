"""Notes placed by a decision (no space in the file) can still be edited.

Regression: an Inbox note placed in `core` by the classifier showed "core" in
the editor, but every save failed with "choose a space for this note" because
the file itself names no space.
"""

from sqlalchemy import delete, select

from app.db.models import Document, DocumentAccess
from app.policy.engine import Sensitivity
from app.vault.labels import Labels, pin_placement

API = "/api/v1"
NOTE = "Inbox/untitled.md"
LEAD = ("employee", "core-lead")


async def _place(sessions, path, space="core", sensitivity="restricted", source="auto_tighten"):
    async with sessions() as s:
        doc_id = (await s.execute(select(Document.id).where(Document.vault_path == path))).scalar()
        await s.execute(delete(DocumentAccess).where(DocumentAccess.document_id == doc_id))
        s.add(
            DocumentAccess(
                document_id=doc_id,
                space=space,
                role="owner",
                sensitivity=sensitivity,
                source=source,
            )
        )
        await s.commit()
    return doc_id


async def _save(client, h, doc_id, change):
    r = await client.get(f"{API}/notes/{doc_id}/source", headers=h)
    assert r.status_code == 200, r.text
    src = r.json()
    return src, await client.put(
        f"{API}/notes/{doc_id}",
        headers=h,
        json={"base_version": src["version"], "content": change(src["content"])},
    )


async def test_note_placed_by_a_decision_can_be_saved(
    indexed, sessions, client, make_user, sign_in
):
    doc_id = await _place(sessions, NOTE)
    h = await sign_in(await make_user(roles=LEAD, home_space="core"))

    src, r = await _save(client, h, doc_id, lambda t: t + "\nBring spare markers.\n")
    assert r.status_code == 200, r.text
    out = r.json()
    # The placement now lives in the file, and the editor gets the stored text.
    assert out["content"].startswith("---\nspace: core\nsensitivity: restricted\n---\n")
    assert out["content"].endswith(src["content"] + "\nBring spare markers.\n")
    async with sessions() as s:
        rows = (
            (await s.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc_id)))
            .scalars()
            .all()
        )
    assert [(r.space, r.role, r.sensitivity) for r in rows] == [("core", "owner", "restricted")]

    # The next save (from the stored text) works too, and submit for review is allowed.
    _, r = await _save(client, h, doc_id, lambda t: t + "Label the boxes.\n")
    assert r.status_code == 200, r.text
    assert r.json()["content"] is None
    assert (await client.post(f"{API}/notes/{doc_id}/submit", headers=h)).status_code < 300


async def test_placement_cannot_be_moved_to_another_space(
    indexed, sessions, client, make_user, sign_in
):
    doc_id = await _place(sessions, NOTE)
    h = await sign_in(await make_user(roles=LEAD, home_space="core"))
    # Writing a different space while saving is still checked like any move.
    _, r = await _save(client, h, doc_id, lambda t: "---\nspace: hr\n---\n" + t)
    assert r.status_code == 403


async def test_other_spaces_people_still_cannot_edit(indexed, sessions, client, make_user, sign_in):
    doc_id = await _place(sessions, "Inbox/printer jam fix.md", space="it")
    h = await sign_in(await make_user(roles=LEAD, home_space="core"))
    r = await client.get(f"{API}/notes/{doc_id}/source", headers=h)
    assert r.status_code == 404
    r = await client.put(
        f"{API}/notes/{doc_id}", headers=h, json={"base_version": "0" * 64, "content": "hi\n"}
    )
    assert r.status_code == 404


def test_pin_placement_only_adds_lines():
    labels = Labels(space="core", sensitivity=Sensitivity.INTERNAL)
    with_fm = "---\ntitle: X  # keep\nsensitivity: restricted\n---\n\nBody\n"
    assert pin_placement(with_fm, {"title": "X", "sensitivity": "restricted"}, labels) == (
        "---\ntitle: X  # keep\nsensitivity: restricted\nspace: core\n---\n\nBody\n"
    )
    assert (
        pin_placement("Body\n", {}, labels)
        == "---\nspace: core\nsensitivity: internal\n---\nBody\n"
    )
    shared = Labels(
        space="core", sensitivity=Sensitivity.INTERNAL, shared_with=[("hr", Sensitivity.RESTRICTED)]
    )
    assert 'shared_with: ["hr:restricted"]' in pin_placement("B\n", {}, shared)
    assert pin_placement("B\n", {}, Labels(space=None, sensitivity=Sensitivity.RESTRICTED)) == "B\n"
