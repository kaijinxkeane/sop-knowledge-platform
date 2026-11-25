"""The built-in user guide (config/help) is added to every vault, once.

- added as a platform commit, so it's never "unattributed"
- approved (citable) even when the vault's first-run baseline already ran
- readable by everyone (core, public), including a new hire
- a guide edited or deleted in the vault is never overwritten or put back
"""

from sqlalchemy import select

from app.classify.service import ClassifierService
from app.db.models import Document
from app.vault.help import guide_sources, install_help, sync_with_help
from app.vault.indexer import Indexer
from tests.db.conftest import fake_embed, no_names

API = "/api/v1"
NEW_HIRE = ("employee",)


async def test_guides_are_added_approved_and_readable_by_everyone(
    indexed, vault, sessions, client, make_user, sign_in
):
    # `indexed` already ran the first-run baseline, like an existing install.
    names = [p.name for p in guide_sources()]
    assert len(names) >= 10
    summary = await sync_with_help(Indexer(vault, sessions, fake_embed))
    assert summary["help_added"] == len(names)
    assert summary["help_approved"] == len(names)
    assert "SOP-Platform: true" in vault._git("log", "-1", "--format=%B")
    await ClassifierService(sessions, no_names).run_pending(limit=100)

    async with sessions() as s:
        docs = (
            (await s.execute(select(Document).where(Document.vault_path.like("Help/%"))))
            .scalars()
            .all()
        )
    assert len(docs) == len(names)
    assert all(d.approved_hash and d.status == "published" for d in docs)

    h = await sign_in(await make_user(roles=NEW_HIRE, home_space="core"))
    listed = (await client.get(f"{API}/documents", headers=h)).json()
    titles = {d["title"] for d in listed}
    assert "Getting Started with the SOP Assistant" in titles
    assert "Asking Questions" in titles


async def test_edited_or_deleted_guides_are_left_alone(indexed, vault, sessions):
    await install_help(vault, sessions)
    edited = vault.safe_path("Help/Asking Questions.md")
    edited.write_text(edited.read_text() + "\nOur own tip.\n")
    vault.safe_path("Help/Admin Guide.md").unlink()
    vault._git("add", "-A")
    vault._git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "edit")

    assert await install_help(vault, sessions) == []
    assert "Our own tip." in edited.read_text()
    assert not vault.safe_path("Help/Admin Guide.md").exists()
