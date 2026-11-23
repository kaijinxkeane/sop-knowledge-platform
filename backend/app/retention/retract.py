"""Retract (plan §7, PDPA): purge a note, or a piece of personal data, from
everything the platform keeps outside the vault.

- **document**: the index (document, chunks, versions, links, proposals,
  approvals, reviews, conflicts, handover), citations, and the text of
  answers that cited it. The indexer then skips that file while its content
  is unchanged; the vault itself is edited by its owners.
- **term**: every document whose text contains it (as above), and the term
  itself is replaced by `[RETRACTED]` in chat history, conversation titles,
  review summaries and comments, handover comments and fields, feedback and
  gap-topic labels; searches and AI proposals containing it are deleted.

Matching reuses llm-wiki's retract patterns (the term plus its common
encodings: URL, JSON, base64, hex). After purging, everything is scanned
again and the remaining counts are returned (they must be 0). The vault is
scanned with llm-wiki's retract scanner and only *counts* are reported, so
the admin knows which files the owners still need to edit. The audit log
never holds content (checked on write), so it needs no purge; it is scanned
too and the count reported.

The term is never stored or logged: the retraction row keeps a SHA-256 hash.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import Text, cast, delete, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    ChatMessage,
    ClassificationProposal,
    Conflict,
    Conversation,
    Document,
    GapTopic,
    Handover,
    HandoverComment,
    MessageCitation,
    MessageFeedback,
    Retraction,
    ReviewRequest,
    SearchEvent,
)
from app.vault.git import GitVault

MARKER = "[RETRACTED]"
REMOVED_ANSWER = "[This answer was removed because a source it used was retracted.]"
MIN_TERM = 3


def term_patterns(term: str) -> list[str]:
    from wiki_core import retract_patterns

    _, names = retract_patterns(term.encode("utf-8"), "common")
    return [p for p in names if len(p) >= MIN_TERM]


def _redact(value, rx: re.Pattern):
    if isinstance(value, str):
        return rx.sub(MARKER, value)
    if isinstance(value, list):
        return [_redact(v, rx) for v in value]
    if isinstance(value, dict):
        return {k: _redact(v, rx) for k, v in value.items()}
    return value


@dataclass
class RetractResult:
    documents: int = 0
    answers_removed: int = 0
    redacted: dict[str, int] = field(default_factory=dict)
    deleted: dict[str, int] = field(default_factory=dict)
    remaining: dict[str, int] = field(default_factory=dict)
    vault_files_with_term: int = 0
    audit_events_with_term: int = 0

    @property
    def clean(self) -> bool:
        return not any(self.remaining.values())

    def summary(self) -> dict:
        return {**self.__dict__, "clean": self.clean}


async def _purge_document(
    s: AsyncSession, doc: Document, actor: uuid.UUID, result: RetractResult, term_hash=None
) -> None:
    cited = set(
        (
            await s.execute(
                select(MessageCitation.message_id).where(MessageCitation.document_id == doc.id)
            )
        ).scalars()
    )
    if cited:
        await s.execute(
            update(ChatMessage)
            .where(ChatMessage.id.in_(cited))
            .values(content=REMOVED_ANSWER, sections=[])
        )
        await s.execute(delete(MessageCitation).where(MessageCitation.message_id.in_(cited)))
        result.answers_removed += len(cited)
    from app.agents.reuse import forget_documents

    await forget_documents(s, [doc.id])
    await s.execute(
        update(GapTopic)
        .where(GapTopic.access_gap_document_id == doc.id)
        .values(access_gap_document_id=None)
    )
    s.add(
        Retraction(
            kind="document",
            vault_path=doc.vault_path,
            content_hash=doc.content_hash,
            term_hash=term_hash,
            created_by=actor,
            result={"answers_removed": len(cited)},
        )
    )
    await s.delete(doc)  # cascades: chunks, versions, links, parts, tags, proposals, ...
    await s.flush()
    result.documents += 1


async def retract_document(s: AsyncSession, doc_id: uuid.UUID, actor: uuid.UUID) -> RetractResult:
    result = RetractResult()
    doc = await s.get(Document, doc_id)
    if doc is None:
        return result
    path = doc.vault_path
    await _purge_document(s, doc, actor, result)
    result.remaining = {
        "documents": await s.scalar(
            text("SELECT count(*) FROM documents WHERE vault_path = :p"), {"p": path}
        ),
        "citations": await s.scalar(
            text("SELECT count(*) FROM message_citations WHERE document_id = :d"), {"d": doc_id}
        ),
        "chunks": await s.scalar(
            text("SELECT count(*) FROM chunks WHERE document_id = :d"), {"d": doc_id}
        ),
    }
    return result


# (table, column, how) for the term scan; json columns are matched as text
_TEXT_COLUMNS = [
    ("messages", "content"),
    ("messages", "sections::text"),
    ("answer_reuse", "section::text"),
    ("conversations", "title"),
    ("search_events", "query"),
    ("handover_comments", "body"),
    ("handovers", "fields::text"),
    ("review_requests", "coalesce(summary, '') || ' ' || comment"),
    ("message_feedback", "comment"),
    ("gap_topics", "label"),
    ("classification_proposals", "rationale || ' ' || evidence::text || ' ' || names::text"),
    ("conflicts", "explanation"),
    ("chunks", "text"),
    ("documents", "title || ' ' || frontmatter::text"),
]


async def _count(s: AsyncSession, patterns: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for table, col in _TEXT_COLUMNS:
        conds = " OR ".join(f"({col}) ILIKE :p{i}" for i in range(len(patterns)))
        params = {f"p{i}": f"%{_like(p)}%" for i, p in enumerate(patterns)}
        n = await s.scalar(text(f"SELECT count(*) FROM {table} WHERE {conds}"), params)
        key = f"{table}.{col.split('::')[0].split(' ')[0]}"
        out[key] = out.get(key, 0) + (n or 0)
    return out


def _like(p: str) -> str:
    return p.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def retract_term(
    s: AsyncSession, term: str, actor: uuid.UUID, git: GitVault | None = None
) -> RetractResult:
    term = term.strip()
    if len(term) < MIN_TERM:
        raise ValueError(f"the value to retract needs at least {MIN_TERM} characters")
    patterns = term_patterns(term)
    rx = re.compile("|".join(re.escape(p) for p in patterns), re.IGNORECASE)
    term_hash = hashlib.sha256(term.lower().encode()).hexdigest()
    result = RetractResult()

    def matching(col):
        return or_(*(col.ilike(f"%{_like(p)}%", escape="\\") for p in patterns))

    # 1. Documents whose text holds it leave the index entirely.
    doc_ids = set(
        (
            await s.execute(
                text(
                    "SELECT DISTINCT document_id FROM chunks WHERE "
                    + " OR ".join(f"text ILIKE :p{i}" for i in range(len(patterns)))
                ),
                {f"p{i}": f"%{_like(p)}%" for i, p in enumerate(patterns)},
            )
        ).scalars()
    )
    doc_ids |= set(
        (
            await s.execute(
                select(Document.id).where(
                    matching(Document.title) | matching(cast(Document.frontmatter, Text))
                )
            )
        ).scalars()
    )
    for doc_id in doc_ids:
        doc = await s.get(Document, doc_id)
        if doc is not None:
            await _purge_document(s, doc, actor, result, term_hash)

    # 2. Redact it where people wrote or read it.
    async def redact(model, col, key):
        rows = (await s.execute(select(model).where(matching(col)))).scalars().all()
        for row in rows:
            setattr(row, col.key, _redact(getattr(row, col.key), rx))
        result.redacted[key] = len(rows)

    from app.db.models import AnswerReuse

    result.redacted["reused_answers"] = (
        await s.execute(delete(AnswerReuse).where(matching(cast(AnswerReuse.section, Text))))
    ).rowcount or 0
    await redact(ChatMessage, ChatMessage.content, key="messages")
    msgs = (
        (await s.execute(select(ChatMessage).where(matching(cast(ChatMessage.sections, Text)))))
        .scalars()
        .all()
    )
    for m in msgs:
        m.sections = _redact(m.sections, rx)
    result.redacted["answer_sections"] = len(msgs)
    await redact(Conversation, Conversation.title, key="conversation_titles")
    await redact(HandoverComment, HandoverComment.body, key="handover_comments")
    hs = (
        (await s.execute(select(Handover).where(matching(cast(Handover.fields, Text)))))
        .scalars()
        .all()
    )
    for h in hs:
        h.fields = _redact(h.fields, rx)
    result.redacted["handover_fields"] = len(hs)
    rr = (
        (
            await s.execute(
                select(ReviewRequest).where(
                    matching(ReviewRequest.summary) | matching(ReviewRequest.comment)
                )
            )
        )
        .scalars()
        .all()
    )
    for r in rr:
        r.summary = _redact(r.summary, rx) if r.summary else r.summary
        r.comment = _redact(r.comment, rx)
    result.redacted["review_requests"] = len(rr)
    await redact(MessageFeedback, MessageFeedback.comment, key="feedback")
    await redact(GapTopic, GapTopic.label, key="gap_topic_labels")

    # 3. Delete what only exists because of it.
    for model, cond, key in (
        (SearchEvent, matching(SearchEvent.query), "searches"),
        (
            ClassificationProposal,
            matching(ClassificationProposal.rationale)
            | matching(cast(ClassificationProposal.evidence, Text))
            | matching(cast(ClassificationProposal.names, Text)),
            "ai_proposals",
        ),
        (Conflict, matching(Conflict.explanation), "conflicts"),
    ):
        r = await s.execute(delete(model).where(cond))
        result.deleted[key] = r.rowcount or 0
    await s.flush()

    # 4. Verify: nothing left outside the vault and the (content-free) audit log.
    result.remaining = await _count(s, patterns)
    result.audit_events_with_term = (
        await s.scalar(
            text(
                "SELECT count(*) FROM audit_events WHERE "
                + " OR ".join(f"details::text ILIKE :p{i}" for i in range(len(patterns)))
            ),
            {f"p{i}": f"%{_like(p)}%" for i, p in enumerate(patterns)},
        )
        or 0
    )
    if git is not None:
        result.vault_files_with_term = vault_matches(git, term)
    s.add(
        Retraction(
            kind="term",
            term_hash=term_hash,
            created_by=actor,
            result={k: v for k, v in result.summary().items() if k != "remaining"}
            | {"remaining": sum(result.remaining.values())},
        )
    )
    return result


def vault_matches(git: GitVault, term: str) -> int:
    """How many vault files still contain the value (llm-wiki's retract scanner)."""
    from wiki_core import retract_patterns, scan_retract_roots

    byte_patterns, name_patterns = retract_patterns(term.encode("utf-8"), "common")
    scan = scan_retract_roots([git.root], byte_patterns, name_patterns)
    return len(scan.text_matches) + len(scan.binary_matches) + len(scan.name_matches)


async def is_retracted(s: AsyncSession, path: str, content_hash: str) -> bool:
    """The indexer skips a retracted file until its content changes."""
    return bool(
        await s.scalar(
            select(Retraction.id).where(
                Retraction.kind == "document",
                Retraction.vault_path == path,
                Retraction.content_hash == content_hash,
            )
        )
    )
