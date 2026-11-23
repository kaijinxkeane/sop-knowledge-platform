"""Versions of decks and PDFs: their text for reading and diffs, the original
files, and the access each version had (decks keep no labels inside)."""

from __future__ import annotations

import io

import pytest
from pptx import Presentation
from sqlalchemy import select, update

from app.classify.service import ClassifierService
from app.db.models import Document, DocumentVersion, Grant, Role
from app.vault.indexer import Indexer
from tests.db.conftest import fake_embed, no_names

API = "/api/v1/documents"
DECK = "Training Content/Attachments/Brand Foundations.pptx"
STAFF = ("employee", "core-staff")
LEAD = ("employee", "core-lead")
READER = ("employee", "core-reader")


@pytest.fixture
async def reader_role(sessions):
    """Reads core up to internal, can't edit: sees approved versions only."""
    async with sessions() as s:
        s.add(
            Role(
                name="core-reader",
                grants=[Grant(space="core", max_sensitivity="internal", actions=["ask"])],
            )
        )
        await s.commit()


def _retitled(data: bytes, title: str) -> bytes:
    deck = Presentation(io.BytesIO(data))
    deck.slides[0].shapes.title.text_frame.text = title
    out = io.BytesIO()
    deck.save(out)
    return out.getvalue()


async def _new_version(vault, sessions, staff, title: str) -> str:
    full = vault.safe_path(DECK)
    full.write_bytes(_retitled(full.read_bytes(), title))
    sha = vault.commit(
        [DECK],
        f"Retitle {title}",
        author_name=staff.user.display_name,
        author_email=staff.user.email,
        user_id=staff.user.id,
    )
    await Indexer(vault, sessions, fake_embed).sync()
    await ClassifierService(sessions, no_names).run_pending(limit=100)
    return sha


async def _deck(sessions) -> str:
    async with sessions() as s:
        return str(
            (await s.execute(select(Document.id).where(Document.vault_path == DECK))).scalar_one()
        )


async def test_deck_versions_text_file_and_approval(
    indexed, vault, sessions, client, make_user, sign_in, reader_role
):
    staff, reader = await make_user(roles=STAFF), await make_user(roles=READER)
    hs, hr = await sign_in(staff), await sign_in(reader)
    deck = await _deck(sessions)
    original = vault.safe_path(DECK).read_bytes()
    seed = (await client.get(f"{API}/{deck}/versions", headers=hr)).json()
    assert len(seed) == 1 and seed[0]["live"]

    new = await _new_version(vault, sessions, staff, "Welcome, version two")

    # The editor sees both, the new one unapproved, as slide text with speaker notes.
    vs = (await client.get(f"{API}/{deck}/versions", headers=hs)).json()
    assert [(v["commit"], v["approved"]) for v in vs] == [
        (new, False),
        (seed[0]["commit"], True),
    ]
    r = (await client.get(f"{API}/{deck}/versions/{new}", headers=hs)).json()
    assert r["content"].startswith("## Slide 1: Welcome, version two")
    assert r["parts"][0] == {
        "part": "slide",
        "number": 1,
        "title": "Welcome, version two",
        "speaker_notes": r["parts"][0]["speaker_notes"],
    }
    old = await client.get(f"{API}/{deck}/versions/{seed[0]['commit']}/file", headers=hs)
    assert old.status_code == 200 and old.content == original
    assert old.headers["cache-control"] == "private, no-store"

    # The reader gets the approved version only: not listed, not by commit, not the file.
    assert [
        v["commit"] for v in (await client.get(f"{API}/{deck}/versions", headers=hr)).json()
    ] == [seed[0]["commit"]]
    for path in (f"{API}/{deck}/versions/{new}", f"{API}/{deck}/versions/{new}/file"):
        r = await client.get(path, headers=hr)
        assert r.status_code == 404 and "version two" not in r.text
    r = await client.get(f"{API}/{deck}/versions/{seed[0]['commit']}", headers=hr)
    assert r.status_code == 200 and "version two" not in r.text


@pytest.mark.parametrize("snapshot", [[["core", "restricted"]], None])
async def test_old_deck_version_keeps_the_access_it_had(
    indexed, vault, sessions, client, make_user, sign_in, snapshot
):
    """A middle version that was restricted (or whose access is unknown) stays
    out of reach of staff after the deck moved on; the lead can open it."""
    staff, lead = await make_user(roles=STAFF), await make_user(roles=LEAD)
    hs, hl = await sign_in(staff), await sign_in(lead)
    deck = await _deck(sessions)
    middle = await _new_version(vault, sessions, staff, "Restricted draft title")
    async with sessions() as s:
        await s.execute(
            update(DocumentVersion)
            .where(DocumentVersion.git_commit == middle)
            .values(access=snapshot)
        )
        await s.commit()
    await _new_version(vault, sessions, staff, "Clean title")

    listed = {v["commit"] for v in (await client.get(f"{API}/{deck}/versions", headers=hs)).json()}
    assert middle not in listed
    for path in (f"{API}/{deck}/versions/{middle}", f"{API}/{deck}/versions/{middle}/file"):
        r = await client.get(path, headers=hs)
        assert r.status_code == 404 and "Restricted draft" not in r.text
    r = await client.get(f"{API}/{deck}/versions/{middle}", headers=hl)
    assert r.status_code == 200 and "Restricted draft title" in r.json()["content"]


async def test_new_versions_record_their_access(indexed, vault, sessions, make_user):
    staff = await make_user(roles=STAFF)
    sha = await _new_version(vault, sessions, staff, "Snapshot check")
    async with sessions() as s:
        v = await s.scalar(select(DocumentVersion).where(DocumentVersion.git_commit == sha))
    assert v.access and all(len(row) == 2 for row in v.access)
    assert {space for space, _ in v.access} == {"core"}
