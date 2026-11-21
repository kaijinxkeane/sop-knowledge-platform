"""Phase 2 acceptance: the demo vault indexed from git, searched per role.

- every result a user gets (list or search) is allowed by the ground truth
- the slide-14 speaker note is found and cited by slide number
- app saves are commits in the user's name, re-indexed immediately
- edit clashes, missing permissions and widening are refused
- drafts are visible only to their author and the space's reviewers
- Obsidian edits (git commits) are picked up incrementally
- stray uncommitted edits are committed as unattributed
- with the embedding model down, keyword search still works
"""

from __future__ import annotations

import pytest
import yaml
from sqlalchemy import func, select

from app.api import deps
from app.classify.service import ClassifierService
from app.db.models import Chunk, Document, DocumentVersion
from app.policy.engine import Sensitivity
from app.vault.indexer import Indexer, commit_stray_changes
from tests.conftest import REPO_ROOT
from tests.db.conftest import _git, broken, fake_embed, no_names

TRUTH = yaml.safe_load((REPO_ROOT / "demo-vault-labels.yaml").read_text())
ALL_TRUTH = {**TRUTH["notes"], **TRUTH["attachments"]}
P, INT, RES = Sensitivity.PUBLIC, Sensitivity.INTERNAL, Sensitivity.RESTRICTED
ROLE_SETS = {
    "new hire": (("employee",), {"core": P, "it": P, "hr": P}),
    "core staff": (("employee", "core-staff"), {"core": INT, "it": P, "hr": P}),
    "ceo": (("employee", "core-lead", "platform-admin"), {"core": RES, "it": P, "hr": P}),
    "it lead": (("employee", "it-lead"), {"core": P, "it": RES, "hr": P}),
    "hr lead": (("employee", "hr-staff", "hr-lead"), {"core": P, "it": P, "hr": RES}),
}
QUERIES = [
    "rate card pricing",
    "discount floor price",
    "disciplinary process",
    "salary",
    "discovery workshop",
    "laptop setup",
    "leave policy",
    "contract",
    "client phone",
    "values card sort",
    "brand pillars",
]
DECK = "Training Content/Attachments/Brand Foundations.pptx"


def allowed(path: str, scopes: dict) -> bool:
    t = ALL_TRUTH.get(path)
    if t is None:
        return False
    return t["space"] in scopes and Sensitivity[t["sensitivity"].upper()] <= scopes[t["space"]]


async def test_full_index_of_demo_vault(indexed, sessions):
    assert indexed.embed_failures == 0
    async with sessions() as s:
        paths = set((await s.execute(select(Document.vault_path))).scalars())
        unembedded = await s.scalar(select(func.count()).where(Chunk.embedding.is_(None)))
        versions = await s.scalar(select(func.count()).select_from(DocumentVersion))
    assert paths == set(ALL_TRUTH)  # templates and .obsidian ignored
    assert unembedded == 0 and versions == len(paths)


@pytest.mark.parametrize("who", sorted(ROLE_SETS))
async def test_no_result_exceeds_ground_truth(indexed, client, make_user, sign_in, who):
    roles, scopes = ROLE_SETS[who]
    h = await sign_in(await make_user(roles=roles))
    listed = (await client.get("/api/v1/documents", headers=h)).json()
    assert listed, "each role should see something"
    for d in listed:
        assert allowed(d["vault_path"], scopes), (who, d["vault_path"])
    for q in QUERIES:
        r = await client.get("/api/v1/search", params={"q": q}, headers=h)
        assert r.status_code == 200 and r.json()["semantic"] is True
        for hit in r.json()["results"]:
            assert allowed(hit["vault_path"], scopes), (who, q, hit["vault_path"])


async def test_unsorted_inbox_is_hidden_from_everyone(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=ROLE_SETS["ceo"][0]))
    r = await client.get("/api/v1/search", params={"q": "meeting notes"}, headers=h)
    assert not [x for x in r.json()["results"] if x["vault_path"].startswith("Inbox/")]


async def test_slide_14_speaker_note_is_cited(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    r = await client.get(
        "/api/v1/search", headers=h, params={"q": "read colleagues intake answers silently"}
    )
    top = r.json()["results"][0]
    assert top["vault_path"] == DECK
    assert (top["part"], top["part_number"]) == ("slide", 14)
    parts = (await client.get(f"/api/v1/documents/{top['document_id']}/parts", headers=h)).json()
    assert len(parts) == 18 and "intake answers" in parts[13]["speaker_notes"]
    f = await client.get(f"/api/v1/documents/{top['document_id']}/file", headers=h)
    assert f.status_code == 200 and f.content[:2] == b"PK"
    assert f.headers["cache-control"] == "private, no-store"


async def test_files_and_parts_are_404_when_hidden(indexed, client, make_user, sign_in, sessions):
    async with sessions() as s:
        doc_id = await s.scalar(select(Document.id).where(Document.vault_path == DECK))
    h = await sign_in(await make_user(roles=("employee",)))
    for sub in ("", "/parts", "/versions", "/file"):
        r = await client.get(f"/api/v1/documents/{doc_id}{sub}", headers=h)
        assert r.status_code == 404, sub


async def test_keyword_search_when_embeddings_are_down(vault, sessions, client, make_user, sign_in):
    report = await Indexer(vault, sessions, broken).sync()
    assert report.embed_failures > 0
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    app = client._transport.app
    app.dependency_overrides[deps.get_query_embedder] = lambda: broken
    h = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    r = await client.get("/api/v1/search", params={"q": "values card sort"}, headers=h)
    assert r.json()["semantic"] is False and r.json()["results"]
    # Once the model is back, the missing vectors are filled in.
    assert await Indexer(vault, sessions, fake_embed).embed_missing() > 0


# --- editing -------------------------------------------------------------------


async def _create(client, h, **kw):
    body = {
        "title": "Venue Checklist",
        "space": "core",
        "sensitivity": "internal",
        "body": "# Venue Checklist\n\nCheck the projector and the flip charts.",
    } | kw
    return await client.post("/api/v1/notes", json=body, headers=h)


async def test_save_is_a_commit_in_the_users_name(indexed, client, make_user, sign_in, vault):
    avery = await make_user("avery@example.com", roles=ROLE_SETS["core staff"][0])
    h = await sign_in(avery)
    r = await _create(client, h)
    assert r.status_code == 201, r.text
    saved = r.json()
    info = vault.last_commit(saved["vault_path"])
    assert info.author_email == "avery@example.com" and info.user_id == avery.user.id
    # searchable straight away, by its author
    s = await client.get("/api/v1/search", params={"q": "projector flip charts"}, headers=h)
    assert s.json()["results"][0]["document_id"] == saved["id"]
    versions = (await client.get(f"/api/v1/documents/{saved['id']}/versions", headers=h)).json()
    assert versions[0]["author_source"] == "app"
    assert versions[0]["authored_by"] == str(avery.user.id)


async def test_drafts_visible_to_author_and_reviewers_only(indexed, client, make_user, sign_in):
    author = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    doc_id = (await _create(client, author)).json()["id"]
    colleague = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    lead = await sign_in(await make_user(roles=ROLE_SETS["ceo"][0]))
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=colleague)).status_code == 404
    assert (await client.get(f"/api/v1/documents/{doc_id}", headers=lead)).status_code == 200
    hits = (
        await client.get("/api/v1/search", params={"q": "projector flip charts"}, headers=colleague)
    ).json()["results"]
    assert doc_id not in {x["document_id"] for x in hits}


async def test_edit_clash_is_refused(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    doc_id = (await _create(client, h)).json()["id"]
    src = (await client.get(f"/api/v1/notes/{doc_id}/source", headers=h)).json()
    first = src["content"] + "\nAlso check the whiteboard markers.\n"
    r = await client.put(
        f"/api/v1/notes/{doc_id}",
        headers=h,
        json={"base_version": src["version"], "content": first},
    )
    assert r.status_code == 200, r.text
    stale = await client.put(
        f"/api/v1/notes/{doc_id}",
        headers=h,
        json={"base_version": src["version"], "content": src["content"]},
    )
    assert stale.status_code == 409


async def test_permission_rules_on_save(indexed, client, make_user, sign_in):
    reader = await sign_in(await make_user(roles=("employee",)))
    assert (await _create(client, reader)).status_code == 403
    staff = await sign_in(await make_user(roles=ROLE_SETS["core staff"][0]))
    assert (await _create(client, staff, space="hr")).status_code == 403
    assert (await _create(client, staff, title="Open Day", sensitivity="public")).status_code == 403
    doc_id = (await _create(client, staff)).json()["id"]
    src = (await client.get(f"/api/v1/notes/{doc_id}/source", headers=staff)).json()
    for old, new in (
        ("sensitivity: internal", "sensitivity: public"),
        ("status: draft", "status: published"),
    ):
        assert old in src["content"]
        r = await client.put(
            f"/api/v1/notes/{doc_id}",
            headers=staff,
            json={"base_version": src["version"], "content": src["content"].replace(old, new)},
        )
        assert r.status_code == 403, new
    lead = await sign_in(await make_user(roles=ROLE_SETS["ceo"][0]))
    r = await client.put(
        f"/api/v1/notes/{doc_id}",
        headers=lead,
        json={
            "base_version": src["version"],
            "content": src["content"].replace("status: draft", "status: published"),
        },
    )
    assert r.status_code == 200, r.text


async def test_attachment_upload_inherits_space_never_public(
    indexed, client, make_user, sign_in, sessions
):
    lead = await sign_in(await make_user(roles=ROLE_SETS["ceo"][0]))
    doc_id = (await _create(client, lead, title="Open Day", sensitivity="public")).json()["id"]
    deck = (REPO_ROOT / "demo-vault" / DECK).read_bytes()
    r = await client.post(
        f"/api/v1/notes/{doc_id}/attachments",
        headers=lead,
        files={"file": ("Open Day Slides.pptx", deck)},
        data={"source_tool": "Canva", "original_link": "https://x.example"},
    )
    assert r.status_code == 201, r.text
    async with sessions() as s:
        att = await s.get(Document, __import__("uuid").UUID(r.json()["id"]))
        assert att.kind == "attachment"
        assert [(a.space, a.sensitivity) for a in att.access] == [("core", "internal")]
    bad = await client.post(
        f"/api/v1/notes/{doc_id}/attachments", headers=lead, files={"file": ("run.exe", b"MZ")}
    )
    assert bad.status_code == 422


# --- worker jobs -------------------------------------------------------------------


async def test_obsidian_commit_is_indexed_incrementally(indexed, vault, sessions):
    note = vault.root / "IT/Laptop Setup for New Staff.md"
    note.write_text(note.read_text() + "\n## Docking\n\nUse the grey dock on desk 4.\n")
    _git(
        vault.root,
        "-c",
        "user.name=Riley",
        "-c",
        "user.email=riley@example.com",
        "commit",
        "-qam",
        "vault: docking",
    )
    report = await Indexer(vault, sessions, fake_embed).sync()
    assert report.indexed == ["IT/Laptop Setup for New Staff.md"]
    assert await Indexer(vault, sessions, fake_embed).sync() is not None  # no-op is fine


async def test_stray_edits_are_committed_as_unattributed(indexed, vault, sessions):
    note = vault.root / "IT/Laptop Setup for New Staff.md"
    note.write_text("# Laptop Setup\n\nEdited on the server.\n")
    assert commit_stray_changes(vault) == ["IT/Laptop Setup for New Staff.md"]
    await Indexer(vault, sessions, fake_embed).sync()
    async with sessions() as s:
        doc_id = await s.scalar(
            select(Document.id).where(Document.vault_path == "IT/Laptop Setup for New Staff.md")
        )
        sources = set(
            (
                await s.execute(
                    select(DocumentVersion.author_source).where(
                        DocumentVersion.document_id == doc_id
                    )
                )
            ).scalars()
        )
    assert "unattributed" in sources


async def test_unrelated_question_finds_nothing(indexed, client, make_user, sign_in):
    h = await sign_in(await make_user(roles=ROLE_SETS["ceo"][0]))
    r = await client.get("/api/v1/search", params={"q": "zebra quantum volcano"}, headers=h)
    assert r.json()["results"] == []
