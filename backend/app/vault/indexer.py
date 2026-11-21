"""Keep the search index in step with the vault (plan §3.1).

Driven by git: after each commit only the changed files are re-indexed. Each
file is parsed locally, labelled (frontmatter > folder rule > preserved
human/AI decisions > quarantine; safeguards always tighten), chunked and
embedded with the local embedding model. If embedding fails, chunks are
stored without vectors (keyword search still works) and filled in later.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.classify.service import refresh_name_flags
from app.db.models import (
    AttachmentPart,
    Chunk,
    Document,
    DocumentAccess,
    DocumentLink,
    DocumentTag,
    DocumentVersion,
    Space,
    User,
    VaultState,
)
from app.retrieval.embed import Embedder
from app.vault.git import GitVault
from app.vault.labels import Labels, VaultConfig, resolve_labels, vault_config
from app.vault.parse import Parsed, is_supported, link_name, parse_file

log = logging.getLogger("sop.indexer")
STATUSES = {"draft", "in_review", "published", "retired"}
# Access rows the indexer derives itself and may replace. Others (an uploader's
# choice, approved AI labels in Phase 2b) are human decisions and are kept
# unless the note's frontmatter or a folder rule says otherwise.
DERIVED_SOURCES = {"frontmatter", "folder_rule", "default", "safeguard", "demo_seed"}


@dataclass
class IndexReport:
    indexed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    embed_failures: int = 0
    commit: str | None = None

    def summary(self) -> dict:
        return {
            "indexed": len(self.indexed),
            "unchanged": len(self.unchanged),
            "removed": len(self.removed),
            "skipped": len(self.skipped),
            "embed_failures": self.embed_failures,
        }


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value if isinstance(value, (str, int, float, bool)) or value is None else str(value)


class Indexer:
    def __init__(
        self,
        git: GitVault,
        sessions: async_sessionmaker,
        embed: Embedder | None,
        config: VaultConfig | None = None,
    ):
        self.git, self.sessions, self.embed = git, sessions, embed
        self.config = config or vault_config()

    # --- entry points ------------------------------------------------------------

    async def sync(self, *, full: bool = False) -> IndexReport:
        """Index everything committed since the last run (or the whole vault)."""
        async with self.sessions() as s:
            state = await s.get(VaultState, "last_commit")
            last = None if full or state is None else state.value
        head = self.git.head()
        try:
            changed, deleted = self.git.changed_since(last)
        except Exception:  # noqa: BLE001 - e.g. history rewritten: fall back to a full scan
            changed, deleted = self.git.tracked_files(), []
        if full or last is None:
            async with self.sessions() as s:
                known = set((await s.execute(select(Document.vault_path))).scalars())
            deleted = sorted(known - set(changed))
        report = await self.index_paths(changed, deleted)
        report.commit = head
        await self.embed_missing(report)
        if head:
            async with self.sessions() as s:
                await s.merge(VaultState(key="last_commit", value=head))
                await s.commit()
        if report.indexed or report.removed:
            log.info("index_sync", extra={"fields": report.summary()})
        return report

    async def index_paths(self, paths: list[str], deleted: list[str] = ()) -> IndexReport:
        report = IndexReport()
        for rel in deleted:
            async with self.sessions() as s, s.begin():
                await self._lock(s, rel)
                gone = await s.execute(delete(Document).where(Document.vault_path == rel))
                if gone.rowcount:
                    report.removed.append(rel)
        for rel in paths:
            if self.config.is_ignored(rel) or not is_supported(rel):
                report.skipped.append(rel)
                continue
            async with self.sessions() as s, s.begin():
                await self._lock(s, rel)
                outcome = await self._index_file(s, rel, report)
            getattr(report, outcome).append(rel)
        if report.indexed or report.removed:
            async with self.sessions() as s, s.begin():
                await self._resolve_links(s)
        return report

    async def embed_missing(self, report: IndexReport | None = None, limit: int = 500) -> int:
        """Fill in vectors for chunks stored while the embedding model was down."""
        if self.embed is None:
            return 0
        async with self.sessions() as s:
            rows = (
                await s.execute(
                    select(Chunk, Document.title)
                    .join(Document, Document.id == Chunk.document_id)
                    .where(Chunk.embedding.is_(None))
                    .limit(limit)
                )
            ).all()
            if not rows:
                return 0
            try:
                vectors = await self.embed(
                    [_embed_text(title, c.heading, c.text) for c, title in rows]
                )
            except Exception:  # noqa: BLE001
                if report is not None:
                    report.embed_failures += len(rows)
                return 0
            for (c, _), v in zip(rows, vectors, strict=True):
                c.embedding = v
            await s.commit()
            return len(rows)

    # --- one file ------------------------------------------------------------------

    @staticmethod
    async def _lock(s: AsyncSession, rel: str) -> None:
        key = int.from_bytes(hashlib.sha256(rel.encode()).digest()[:8], "big", signed=True)
        await s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": key})

    async def _index_file(self, s: AsyncSession, rel: str, report: IndexReport) -> str:
        try:
            full = self.git.safe_path(rel)
        except ValueError:
            return "skipped"
        doc = (await s.execute(select(Document).where(Document.vault_path == rel))).scalar()
        if not full.is_file():
            if doc is not None:
                await s.delete(doc)
                return "removed"
            return "skipped"
        data = full.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        try:
            parsed = parse_file(rel, data)
        except Exception:  # noqa: BLE001 - a corrupt file must not stop indexing
            log.warning("parse_failed", extra={"fields": {"path_hash": digest[:12]}})
            return "skipped"

        spaces = set((await s.execute(select(Space.name))).scalars())
        all_text = "\n".join([parsed.title, *(c.text for c in parsed.chunks)])
        labels = resolve_labels(
            rel,
            parsed.frontmatter,
            all_text,
            known_spaces=spaces,
            config=self.config,
            frontmatter_error=parsed.frontmatter_error,
        )
        unchanged = doc is not None and doc.content_hash == digest
        if doc is None:
            doc = Document(vault_path=rel, title=parsed.title)
            s.add(doc)
        self._apply_metadata(doc, parsed, labels, digest)
        await s.flush()
        await self._apply_access(s, doc, labels)
        await s.flush()
        rows = list(
            (
                await s.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id))
            ).scalars()
        )
        refresh_name_flags(doc, rows, self.config)  # new version -> names_pending

        commit = self.git.last_commit(rel)
        if commit is not None:
            doc.current_commit = commit.sha
            await self._record_version(s, doc, commit, digest)
        doc.indexed_at = datetime.now(UTC)
        if unchanged and await s.scalar(select(func.count()).where(Chunk.document_id == doc.id)):
            return "unchanged"
        await self._replace_content(s, doc, parsed, report)
        return "indexed"

    def _apply_metadata(self, doc: Document, parsed: Parsed, labels: Labels, digest: str) -> None:
        fm = parsed.frontmatter
        doc.title = parsed.title
        doc.kind = parsed.kind
        doc.doc_type = str(fm.get("doc_type") or parsed.doc_type)[:32]
        status = str(fm.get("status") or "").strip()
        doc.status = status if status in STATUSES else "unreviewed"
        doc.programme = str(fm["programme"]).strip() if fm.get("programme") else None
        stage = str(fm.get("stage") or "").strip()
        doc.stage = stage if stage in self.config.stages else None
        doc.owner = str(fm["owner"]).strip() if fm.get("owner") else None
        doc.frontmatter = _json_safe(fm)
        doc.label_source = labels.source
        doc.safeguards = labels.safeguards
        doc.content_hash = digest

    async def _apply_access(self, s: AsyncSession, doc: Document, labels: Labels) -> None:
        rows = (
            (await s.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id)))
            .scalars()
            .all()
        )
        preserved = [r for r in rows if r.source not in DERIVED_SOURCES]
        authoritative = labels.source in ("frontmatter", "folder_rule")
        if authoritative or not preserved:
            for r in rows:
                await s.delete(r)
            await s.flush()
            source = "safeguard" if labels.safeguards else labels.source
            for space, role, sens in labels.rows():
                s.add(
                    DocumentAccess(
                        document_id=doc.id, space=space, role=role, sensitivity=sens, source=source
                    )
                )
        # Human/AI decisions in `preserved` are kept as they are: safeguards in
        # documents.safeguards floor them to `restricted` at read time
        # (policy engine + RLS), and lift again once they are cleared.

    async def _record_version(self, s: AsyncSession, doc: Document, commit, digest: str) -> None:
        exists = await s.scalar(
            select(func.count()).where(
                DocumentVersion.document_id == doc.id, DocumentVersion.git_commit == commit.sha
            )
        )
        if exists:
            return
        authored_by, source = commit.user_id, "app" if commit.user_id else "git"
        if commit.unattributed:
            authored_by, source = None, "unattributed"
        elif authored_by is None:
            authored_by = await s.scalar(
                select(User.id).where(func.lower(User.email) == commit.author_email.lower())
            )
        s.add(
            DocumentVersion(
                document_id=doc.id,
                git_commit=commit.sha,
                content_hash=digest,
                authored_by=authored_by,
                author_name=commit.author_name,
                author_source=source,
                committed_at=commit.committed_at,
            )
        )

    async def _replace_content(
        self, s: AsyncSession, doc: Document, parsed: Parsed, report: IndexReport
    ) -> None:
        for model, col in (
            (Chunk, Chunk.document_id),
            (DocumentLink, DocumentLink.from_id),
            (DocumentTag, DocumentTag.document_id),
            (AttachmentPart, AttachmentPart.document_id),
        ):
            await s.execute(delete(model).where(col == doc.id))
        vectors: list[list[float] | None] = [None] * len(parsed.chunks)
        if self.embed is not None and parsed.chunks:
            try:
                vectors = await self.embed(
                    [_embed_text(doc.title, c.heading, c.text) for c in parsed.chunks]
                )
            except Exception:  # noqa: BLE001 - keyword search still works; retried later
                report.embed_failures += len(parsed.chunks)
        for i, (c, v) in enumerate(zip(parsed.chunks, vectors, strict=True)):
            s.add(
                Chunk(
                    document_id=doc.id,
                    ord=i,
                    heading=c.heading,
                    part=c.part,
                    part_number=c.number,
                    text=c.text,
                    embedding=v,
                )
            )
        for link in parsed.links:
            s.add(DocumentLink(from_id=doc.id, target=_link_key(link.target), embed=link.embed))
        for tag in parsed.tags:
            s.add(DocumentTag(document_id=doc.id, tag=tag[:128]))
        for part in parsed.parts:
            s.add(
                AttachmentPart(
                    document_id=doc.id,
                    part=part.part,
                    number=part.number,
                    title=part.title,
                    speaker_notes=part.speaker_notes,
                )
            )

    async def _resolve_links(self, s: AsyncSession) -> None:
        docs = (await s.execute(select(Document.id, Document.vault_path))).all()
        by_name: dict[str, uuid.UUID] = {}
        for doc_id, path in docs:
            by_name.setdefault(_link_key(path), doc_id)
        links = (await s.execute(select(DocumentLink))).scalars().all()
        for link in links:
            link.to_id = by_name.get(link.target)


def _link_key(target: str) -> str:
    name = target.rsplit("/", 1)[-1]
    return name.lower() if "." in name and not name.lower().endswith(".md") else link_name(name)


def _embed_text(title: str, heading: str | None, body: str) -> str:
    return "\n".join(x for x in (title, heading, "", body) if x is not None)


def commit_stray_changes(git: GitVault, config: VaultConfig | None = None) -> list[str]:
    """Nightly check: commit files changed outside the app/Obsidian Git as unattributed."""
    config = config or vault_config()
    paths = [p for p in git.uncommitted() if not config.is_ignored(p)]
    if not paths:
        return []
    with git.lock():
        git.commit(
            paths,
            "Unattributed changes found by the nightly check",
            author_name="SOP Platform",
            author_email="platform@sop.local",
            unattributed=True,
        )
    return paths
