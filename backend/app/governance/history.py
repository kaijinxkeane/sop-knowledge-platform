"""Which past versions of a note a person may read (plan §6, red-team 2026-11-22).

Two rules, both needed:
- **Approval:** someone who doesn't see unapproved changes (`sees_latest` is
  false) only gets versions that were approved at some point. Unapproved edits
  are for the note's editors.
- **Labels it had:** any version other than the approved and latest ones is
  judged by the labels it had, so an old restricted version stays restricted
  after the document was made more open. Notes: re-read from that version's own
  frontmatter and folder. Decks, PDFs and other files keep no labels inside, so
  the access snapshot taken when the version was indexed is used
  (`document_versions.access`); a version without one fails closed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, SopApproval
from app.policy.engine import Principal, Sensitivity, can_view_document
from app.vault.git import GitError, GitVault
from app.vault.labels import resolve_labels, vault_config
from app.vault.parse import parse_note


def owner_space(doc: Document) -> str | None:
    return next((a.space for a in doc.access if a.role == "owner"), None)


def _lead_only(principal: Principal, doc: Document) -> bool:
    """Unknown labels: only someone who approves the owner space at `restricted`."""
    space = owner_space(doc)
    return (
        bool(space)
        and principal.can("approve", space)
        and principal.can_read(space, Sensitivity.RESTRICTED)
    )


def version_readable(
    principal: Principal,
    doc: Document,
    git: GitVault,
    commit: str,
    spaces,
    *,
    snapshot: list | None = None,
) -> bool:
    """May this user read that version, judged by the labels it had then?
    The approved and latest versions follow the document's access (already
    checked); any other version is judged by its own labels (see module doc).
    Unknown labels fail closed."""
    for known in (doc.approved_commit, doc.current_commit):
        if known and known.startswith(commit):
            return True
    if doc.kind != "note":
        if not snapshot:
            return _lead_only(principal, doc)
        return can_view_document(principal, [(sp, sens) for sp, sens in snapshot])
    try:
        text = git.show(doc.vault_path, commit).decode("utf-8", "replace")
    except GitError:
        return False
    parsed = parse_note(doc.vault_path, text)
    labels = resolve_labels(
        doc.vault_path,
        parsed.frontmatter,
        text,
        known_spaces=spaces,
        config=vault_config(),
        frontmatter_error=parsed.frontmatter_error,
    )
    rows = [(space, sens) for space, _, sens in labels.rows()]
    if labels.space is None or not rows:
        return _lead_only(principal, doc)
    return can_view_document(principal, rows, safeguards=labels.safeguards)


async def approved_commits(session: AsyncSession, doc: Document) -> set[str]:
    rows = await session.execute(
        select(SopApproval.git_commit).where(
            SopApproval.document_id == doc.id, SopApproval.git_commit.is_not(None)
        )
    )
    out = set(rows.scalars())
    if doc.approved_commit:
        out.add(doc.approved_commit)
    return out


async def readable_versions(
    session: AsyncSession,
    principal: Principal,
    doc: Document,
    git: GitVault,
    commits: dict[str, list | None],
    spaces,
    *,
    editor: bool,
) -> set[str]:
    """The subset of `commits` ({commit: access snapshot}) this person may read.
    `editor` is `sees_latest(...)`, decided under RLS before this is called;
    this runs as the owner role (approvals aren't readable by `sop_reader`)."""
    approved = await approved_commits(session, doc)
    return {
        c
        for c, snapshot in commits.items()
        if (editor or c in approved)
        and version_readable(principal, doc, git, c, spaces, snapshot=snapshot)
    }
