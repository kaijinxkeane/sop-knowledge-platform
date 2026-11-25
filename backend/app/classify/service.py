"""Run the Classifier over documents that need it, and apply the one-way rule.

A document needs the Classifier when
- no human label covers it (no frontmatter or folder rule) and this version
  has no proposal yet, or
- it is in a name-checked space and this version has not been checked for
  names (`names_pending`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import PurePosixPath

from sqlalchemy import exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import audit
from app.classify.model import EXAMPLE_CHARS, MAX_EXAMPLES, Classifier, ClassifyInput, Example
from app.classify.names import staff_index, unresolved_names
from app.classify.rules import (
    NAME_FLAGS,
    NAMES_FOUND,
    NAMES_PENDING,
    RULE_SOURCES,
    Decision,
    Proposal,
    decide,
)
from app.classify.sorter import combine, predict
from app.classify.training import doc_vector, latest_sorter
from app.db.models import (
    Chunk,
    ClassificationProposal,
    Document,
    DocumentAccess,
    KnownName,
    Space,
    User,
)
from app.vault.folders import department_of
from app.vault.labels import Labels, VaultConfig, labels_from_rows, vault_config

log = logging.getLogger("sop.classifier")


@dataclass
class ClassifyReport:
    classified: int = 0
    failed: int = 0
    decisions: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict:
        return {"classified": self.classified, "failed": self.failed, **self.decisions}


def refresh_name_flags(doc: Document, rows: list[DocumentAccess], config: VaultConfig) -> None:
    """Recompute the name-detector part of doc.safeguards (pattern hits are kept)."""
    pattern = [x for x in (doc.safeguards or []) if x not in NAME_FLAGS]
    owner = next((r.space for r in rows if r.role == "owner"), None)
    flags = []
    if owner in config.name_check_spaces:
        if doc.name_check_hash != doc.content_hash:
            flags.append(NAMES_PENDING)
        elif doc.name_hits:
            flags.append(NAMES_FOUND)
    doc.safeguards = pattern + flags


def group_key(vault_path: str, space: str | None, sensitivity: str) -> str:
    folder = vault_path.rsplit("/", 1)[0] if "/" in vault_path else ""
    return f"{folder}|{space or 'unsure'}|{sensitivity}"


async def replace_access(
    s: AsyncSession, doc: Document, labels: Labels, *, source: str, decided_by=None
) -> list[DocumentAccess]:
    for r in (
        await s.execute(select(DocumentAccess).where(DocumentAccess.document_id == doc.id))
    ).scalars():
        await s.delete(r)
    await s.flush()
    now = datetime.now(UTC)
    rows = [
        DocumentAccess(
            document_id=doc.id,
            space=sp,
            role=role,
            sensitivity=sens,
            source=source,
            decided_by=decided_by,
            decided_at=now,
        )
        for sp, role, sens in labels.rows()
    ]
    s.add_all(rows)
    await s.flush()
    return rows


async def pending_documents(s: AsyncSession, limit: int) -> list[Document]:
    has_proposal = exists().where(
        ClassificationProposal.document_id == Document.id,
        ClassificationProposal.content_hash == Document.content_hash,
    )
    q = (
        select(Document)
        .where(
            Document.content_hash.is_not(None),
            or_(
                Document.label_source.not_in(RULE_SOURCES) & ~has_proposal,
                Document.safeguards.contains([NAMES_PENDING]),
            ),
        )
        .order_by(Document.indexed_at)
        .limit(limit)
    )
    return list((await s.execute(q)).scalars())


HUMAN_SOURCES = ("frontmatter", "folder_rule", "approved_ai")  # labels a person decided
EXAMPLE_DISTANCE = 0.6  # farther than this, a "similar" note is not similar


async def similar_labelled(s: AsyncSession, doc_id, k: int = MAX_EXAMPLES) -> list[Example]:
    """The k notes most like this one (mean chunk embedding) whose labels people decided."""
    rows = (
        await s.execute(
            text("""
            WITH q AS (SELECT avg(embedding) AS v FROM chunks
                       WHERE document_id = :id AND embedding IS NOT NULL)
            SELECT c.document_id, min(c.embedding <=> q.v) AS dist
            FROM chunks c JOIN documents d ON d.id = c.document_id, q
            WHERE q.v IS NOT NULL AND c.embedding IS NOT NULL AND c.document_id <> :id
              AND d.label_source = ANY(:sources)
            GROUP BY c.document_id HAVING min(c.embedding <=> q.v) <= :maxd
            ORDER BY dist LIMIT :k"""),
            {"id": doc_id, "sources": list(HUMAN_SOURCES), "maxd": EXAMPLE_DISTANCE, "k": k},
        )
    ).all()
    out = []
    for doc_id_, _ in rows:
        doc = await s.get(Document, doc_id_)
        owner = await s.scalar(
            select(DocumentAccess).where(
                DocumentAccess.document_id == doc_id_, DocumentAccess.role == "owner"
            )
        )
        first = await s.scalar(
            select(Chunk.text).where(Chunk.document_id == doc_id_).order_by(Chunk.ord).limit(1)
        )
        if doc is None or owner is None:
            continue
        folder = str(PurePosixPath(doc.vault_path).parent)
        out.append(
            Example(
                doc.title,
                (first or "")[:EXAMPLE_CHARS],
                owner.space,
                owner.sensitivity,
                folder if department_of(folder, vault_config()) == owner.space else None,
            )
        )
    return out


class ClassifierService:
    def __init__(
        self,
        sessions: async_sessionmaker,
        classifier: Classifier,
        config: VaultConfig | None = None,
        # Off by default: on the blind eval, examples from 30/60/120 labelled
        # notes gave 71.7/79.2/77.5% vs 79.2% without (no significant gain).
        # Re-run `eval-classifier --example-pool N` on real labels before enabling.
        use_examples: bool | None = None,
        use_sorter: bool | None = None,
    ):
        self.sessions, self.classifier = sessions, classifier
        self.config = config or vault_config()
        self.use_examples = (
            self.config.classifier_examples if use_examples is None else use_examples
        )
        self.use_sorter = self.config.classifier_sorter if use_sorter is None else use_sorter

    async def run_pending(self, limit: int = 20) -> ClassifyReport:
        report = ClassifyReport()
        async with self.sessions() as s:
            ids = [d.id for d in await pending_documents(s, limit)]
        for doc_id in ids:
            try:
                decision = await self.classify(doc_id)
            except Exception:  # noqa: BLE001 - model down etc.: stays restricted, retried later
                report.failed += 1
                log.warning("classify_failed", extra={"fields": {"document_id": str(doc_id)}})
                continue
            if decision is not None:
                report.classified += 1
                report.decisions[decision] = report.decisions.get(decision, 0) + 1
        if report.classified or report.failed:
            log.info("classify_run", extra={"fields": report.summary()})
        return report

    async def classify(self, doc_id) -> str | None:
        async with self.sessions() as s:
            doc = await s.get(Document, doc_id)
            if doc is None:
                return None
            text = "\n\n".join(
                (
                    await s.execute(
                        select(Chunk.text).where(Chunk.document_id == doc_id).order_by(Chunk.ord)
                    )
                ).scalars()
            )
            examples = (
                tuple(await similar_labelled(s, doc_id))
                if doc.label_source not in RULE_SOURCES and self.use_examples
                else ()
            )
            item = ClassifyInput(
                vault_path=doc.vault_path,
                title=doc.title,
                kind=doc.kind,
                text=text,
                examples=examples,
            )
            version = doc.content_hash
            vote = None
            if self.use_sorter and doc.label_source not in RULE_SOURCES:
                model = await latest_sorter(s)
                vector = await doc_vector(s, doc_id) if model else None
                vote = predict(model, vector) if model and vector else None
        proposal = await self.classifier(item)  # outside any transaction (slow)
        if not proposal.valid:
            raise ValueError("unreadable classifier reply")  # stays pending; retried
        proposal, folder = combine(proposal, vote)

        async with self.sessions() as s, s.begin():
            doc = await s.get(Document, doc_id, with_for_update=True)
            if doc is None or doc.content_hash != version:
                return None  # changed meanwhile: the next run picks up the new version
            names = await self._unresolved(s, proposal, item.text)
            doc.name_check_hash, doc.name_hits = version, names

            rows = list(
                (
                    await s.execute(
                        select(DocumentAccess).where(DocumentAccess.document_id == doc.id)
                    )
                ).scalars()
            )
            outcome = "names_checked"
            if doc.label_source not in RULE_SOURCES:
                outcome, rows = await self._label(s, doc, rows, proposal, names, vote, folder)
            refresh_name_flags(doc, rows, self.config)
            await audit.record(
                s,
                "document_classified",
                target_type="document",
                target_id=doc.id,
                details={"decision": outcome, "model": proposal.model, "names": len(names)},
            )
        return outcome

    async def _unresolved(self, s: AsyncSession, proposal: Proposal, text: str) -> list[str]:
        staff = staff_index((await s.execute(select(User.display_name))).scalars())
        known = (await s.execute(select(KnownName.name, KnownName.kind))).all()
        safe = {n for n, k in known if k == "safe"} | set(self.config.known_names)
        clients = {n for n, k in known if k == "client"}
        return unresolved_names(proposal.names, text, staff=staff, safe=safe, clients=clients)

    async def _label(
        self,
        s: AsyncSession,
        doc: Document,
        rows: list[DocumentAccess],
        proposal: Proposal,
        names: list[str],
        vote=None,
        folder: str | None = None,
    ) -> tuple[str, list]:
        spaces = set((await s.execute(select(Space.name))).scalars())
        current = labels_from_rows(rows) if rows else None
        result: Decision = decide(current, proposal, known_spaces=spaces)
        await s.execute(
            ClassificationProposal.__table__.update()
            .where(
                ClassificationProposal.document_id == doc.id,
                ClassificationProposal.status == "pending",
            )
            .values(status="superseded")
        )
        s.add(
            ClassificationProposal(
                document_id=doc.id,
                content_hash=doc.content_hash,
                proposed_space=proposal.space,
                proposed_sensitivity=proposal.sensitivity.label,
                proposed_shared_with=[[sp, lvl.label] for sp, lvl in proposal.shared_with],
                confidence=proposal.confidence,
                rationale=proposal.rationale,
                evidence=list(proposal.evidence),
                names=names,
                model=proposal.model,
                status=result.status,
                decision=result.decision,
                group_key=group_key(doc.vault_path, proposal.space, proposal.sensitivity.label),
                sorter_vote=None
                if vote is None
                else {
                    "space": vote.space,
                    "confidence": vote.confidence,
                    "sensitivity": vote.sensitivity.label if vote.sensitivity else None,
                },
                suggested_folder=folder,
            )
        )
        if result.apply is not None:
            rows = await replace_access(s, doc, result.apply, source="auto_tighten")
        return result.decision, rows


async def proposal_counts(s: AsyncSession) -> dict[str, int]:
    rows = (
        await s.execute(
            select(ClassificationProposal.status, func.count()).group_by(
                ClassificationProposal.status
            )
        )
    ).all()
    return dict(rows)
