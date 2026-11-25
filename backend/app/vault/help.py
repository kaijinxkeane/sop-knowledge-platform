"""The built-in user guide (config/help/*.md) as notes in every vault.

Each guide is added once to the vault's `Help/` folder as a platform commit, so
the nightly check doesn't flag it and history shows where it came from. A guide
already in the vault is left alone (people may have edited it), and one deleted
from the vault isn't put back. Guides marked `status: published` are approved
as `baseline` (never reviewed in the platform), so answers can cite them.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.db.models import Document, VaultState
from app.governance.approvals import approve
from app.vault.git import PLATFORM_EMAIL, PLATFORM_NAME, GitVault
from app.vault.labels import VaultConfig

HELP_FOLDER = "Help"
INSTALLED_KEY = "help_installed"


def guide_sources(config_dir: Path | None = None) -> list[Path]:
    folder = (config_dir or get_settings().config_dir) / "help"
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


async def install_help(
    git: GitVault, sessions: async_sessionmaker, config_dir: Path | None = None
) -> list[str]:
    """Add guides the vault has never had. Returns the vault paths added."""
    sources = guide_sources(config_dir)
    if not sources:
        return []
    async with sessions() as s:
        state = await s.get(VaultState, INSTALLED_KEY)
        done = set(json.loads(state.value)) if state else set()
    added = []
    with git.lock():
        for src in sources:
            rel = f"{HELP_FOLDER}/{src.name}"
            full = git.safe_path(rel)
            if src.name in done or full.exists():
                continue
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_bytes(src.read_bytes())
            added.append(rel)
        if added:
            git.commit(
                added,
                "Add the built-in user guide",
                author_name=PLATFORM_NAME,
                author_email=PLATFORM_EMAIL,
                platform=True,
            )
    names = sorted(done | {src.name for src in sources})
    if names != sorted(done):
        async with sessions() as s, s.begin():
            await s.merge(VaultState(key=INSTALLED_KEY, value=json.dumps(names)))
    return added


async def approve_guides(s: AsyncSession, paths: list[str], config: VaultConfig) -> int:
    """Approve newly added guides marked published that nothing approved yet
    (on a vault's first connection the baseline already did)."""
    if not paths:
        return 0
    docs = (
        (
            await s.execute(
                select(Document).where(
                    Document.vault_path.in_(paths),
                    Document.approved_hash.is_(None),
                    Document.frontmatter["status"].astext == "published",
                )
            )
        )
        .scalars()
        .all()
    )
    for doc in docs:
        await approve(s, doc, approver_id=None, method="baseline", config=config)
    return len(docs)


async def sync_with_help(indexer, *, full: bool = False) -> dict:
    """Add any missing guides, index the vault, then approve the new guides."""
    added = await install_help(indexer.git, indexer.sessions)
    report = await indexer.sync(full=full)
    summary = report.summary()
    if added:
        async with indexer.sessions() as s, s.begin():
            summary["help_added"] = len(added)
            summary["help_approved"] = await approve_guides(s, added, indexer.config)
    return summary
