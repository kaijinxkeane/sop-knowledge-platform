"""Row-level security: raw SQL as `sop_reader` only sees rows the scopes allow."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from app.db.models import Document, DocumentAccess

DOCS = {
    "core-public": [("core", "public")],
    "core-internal": [("core", "internal")],
    "core-restricted": [("core", "restricted")],
    "core-missing-label": [("core", None)],
    "core-capitalised": [("core", "Public")],
    "core-misspelled": [("core", "pubic")],
    "hr-public": [("hr", "public")],
    "core-shared-with-hr": [("core", "restricted"), ("hr", "internal")],
    "unassigned": [],
}


@pytest.fixture
async def seeded(sessions):
    async with sessions() as s:
        for title, rows in DOCS.items():
            s.add(
                Document(
                    vault_path=f"{title}.md",
                    title=title,
                    access=[DocumentAccess(space=sp, sensitivity=sens) for sp, sens in rows],
                )
            )
        await s.commit()
    return sessions


async def titles(sessions, scopes, *, set_scopes=True, table="documents"):
    async with sessions() as s, s.begin():
        await s.execute(text("SET LOCAL ROLE sop_reader"))
        if set_scopes:
            await s.execute(
                text("SELECT set_config('sop.scopes', :v, true)"),
                {"v": scopes if isinstance(scopes, str) else json.dumps(scopes)},
            )
        if table == "documents":
            rows = await s.execute(text("SELECT title FROM documents"))
        else:
            rows = await s.execute(
                text(
                    "SELECT d.vault_path || ':' || a.space FROM document_access a "
                    "JOIN documents d ON d.id = a.document_id"
                )
            )
        return set(rows.scalars())


async def test_public_only_user_sees_only_public(seeded):
    assert await titles(seeded, {"core": "public"}) == {"core-public"}
    assert await titles(seeded, {"core": "public", "hr": "public"}) == {"core-public", "hr-public"}


async def test_missing_or_invalid_labels_need_restricted(seeded):
    seen = await titles(seeded, {"core": "internal"})
    assert seen == {"core-public", "core-internal"}
    assert {"core-missing-label", "core-capitalised", "core-misspelled"} <= await titles(
        seeded, {"core": "restricted"}
    )


async def test_shared_document_visible_through_either_space(seeded):
    assert await titles(seeded, {"hr": "internal"}) == {"hr-public", "core-shared-with-hr"}


async def test_unassigned_documents_are_never_visible(seeded):
    everything = {"core": "restricted", "it": "restricted", "hr": "restricted"}
    assert "unassigned" not in await titles(seeded, everything)


@pytest.mark.parametrize("scopes", [{}, "", "{}", {"core": "Restricted"}, {"finance": "public"}])
async def test_no_or_bad_scopes_see_nothing(seeded, scopes):
    assert await titles(seeded, scopes) == set()


async def test_no_scope_setting_sees_nothing(seeded):
    assert await titles(seeded, None, set_scopes=False) == set()


async def test_access_rows_are_filtered_too(seeded):
    rows = await titles(seeded, {"hr": "internal"}, table="access")
    # The shared doc's core/restricted row stays hidden; only its hr row is readable.
    assert rows == {"hr-public.md:hr", "core-shared-with-hr.md:hr"}


async def test_reader_role_cannot_touch_identity_tables(seeded):
    async with seeded() as s, s.begin():
        await s.execute(text("SET LOCAL ROLE sop_reader"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            await s.execute(text("SELECT email FROM users"))


async def test_reader_role_cannot_write(seeded):
    async with seeded() as s, s.begin():
        await s.execute(text("SET LOCAL ROLE sop_reader"))
        with pytest.raises(ProgrammingError, match="permission denied"):
            await s.execute(text("UPDATE document_access SET sensitivity = 'public'"))
