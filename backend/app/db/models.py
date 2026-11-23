"""ORM models for identity, permissions, audit and document access (plan §9).

`documents` and `document_access` are the minimal Phase 1 shape needed to
enforce row-level security; Phase 2 adds versions, chunks and attachments.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

SENSITIVITY_CHECK = "max_sensitivity IN ('public', 'internal', 'restricted')"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Space(Base):
    __tablename__ = "spaces"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    local_only: Mapped[bool] = mapped_column(Boolean, default=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)  # stored lower-case
    display_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str | None] = mapped_column(Text)  # null until the invite is accepted
    totp_secret_enc: Mapped[str | None] = mapped_column(Text)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    totp_last_step: Mapped[int | None] = mapped_column(BigInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_space: Mapped[str | None] = mapped_column(ForeignKey("spaces.name"))
    created_at: Mapped[datetime] = _created()
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leaving_on: Mapped[date | None] = mapped_column(Date)  # for the bus-factor report

    roles: Mapped[list[Role]] = relationship(secondary="user_roles", lazy="selectin")


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")

    grants: Mapped[list[Grant]] = relationship(
        back_populates="role", cascade="all, delete-orphan", lazy="selectin"
    )


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )


class Grant(Base):
    __tablename__ = "grants"
    __table_args__ = (CheckConstraint(SENSITIVITY_CHECK, name="grants_sensitivity"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"))
    # NULL = company-wide grant (global actions only; enforced by the policy engine).
    space: Mapped[str | None] = mapped_column(ForeignKey("spaces.name"))
    max_sensitivity: Mapped[str] = mapped_column(String(16), default="public")
    actions: Mapped[list[str]] = mapped_column(ARRAY(String(32)))

    role: Mapped[Role] = relationship(back_populates="grants")


class OneTimeToken(Base):
    """Invite / password-reset links. Only a hash of the token is stored."""

    __tablename__ = "one_time_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(16))  # invite
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class RefreshToken(Base):
    """Rotating refresh tokens. Reuse of a rotated token revokes the whole family."""

    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class NoticeAcknowledgement(Base):
    __tablename__ = "notice_acknowledgements"
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    notice_version: Mapped[str] = mapped_column(String(32), primary_key=True)
    acknowledged_at: Mapped[datetime] = _created()


class AuditEvent(Base):
    """Append-only (DB trigger) and hash-chained. Details never hold secrets."""

    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


EMBEDDING_DIM = 1024  # qwen3-embedding:0.6b (and bge-m3)


class Document(Base):
    """One vault file (note or attachment). Postgres is only an index: the vault
    is the source of truth and the index can be rebuilt from it."""

    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = _uuid_pk()
    vault_path: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = _created()
    kind: Mapped[str] = mapped_column(String(16), default="note")  # note | attachment
    doc_type: Mapped[str] = mapped_column(String(32), default="guide")
    status: Mapped[str] = mapped_column(String(16), default="unreviewed")
    programme: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(32))
    owner: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # created in the app by
    frontmatter: Mapped[dict] = mapped_column(JSONB, default=dict)
    label_source: Mapped[str] = mapped_column(String(16), default="default")
    safeguards: Mapped[list[str]] = mapped_column(ARRAY(String(64)), default=list)
    current_commit: Mapped[str | None] = mapped_column(String(64))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Name detector (plan §4.1): the content hash last checked for names, and the
    # names found that are neither staff nor confirmed safe.
    name_check_hash: Mapped[str | None] = mapped_column(String(64))
    name_hits: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # Governance (plan §6): approvals cover one exact version. `governed_hash`
    # ignores the frontmatter keys the platform writes itself.
    governed_hash: Mapped[str | None] = mapped_column(String(64))
    approved_hash: Mapped[str | None] = mapped_column(String(64))
    approved_commit: Mapped[str | None] = mapped_column(String(64))
    review_due: Mapped[date | None] = mapped_column(Date)
    # Access in force when the live version was approved, and the wider access a
    # newer version asks for (applied on approval): [[space, role, sensitivity, source]]
    approved_access: Mapped[list | None] = mapped_column(JSONB)
    pending_access: Mapped[list | None] = mapped_column(JSONB)
    # ids of instruction-like patterns in the text (app.governance.injection), never text
    injection_flags: Mapped[list[str] | None] = mapped_column(JSONB)

    access: Mapped[list[DocumentAccess]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    # Per-person read access (handover notes). Under RLS a user sees only their own row.
    readers: Mapped[list[DocumentReader]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class DocumentReader(Base):
    __tablename__ = "document_readers"
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    reason: Mapped[str] = mapped_column(String(16))  # author | receiver | lead | ceo


class DocumentAccess(Base):
    """The labels in force. Sensitivity is free text on purpose: anything but an
    exact known label is treated as restricted, by the app and by RLS alike."""

    __tablename__ = "document_access"
    __table_args__ = (UniqueConstraint("document_id", "space", name="document_access_once"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    space: Mapped[str] = mapped_column(ForeignKey("spaces.name"))
    role: Mapped[str] = mapped_column(String(8), default="owner")  # owner | shared
    sensitivity: Mapped[str | None] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16), default="default")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime] = _created()


class DocumentVersion(Base):
    """A git commit that changed the file, with who made it (plan §3.2)."""

    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "git_commit", name="version_once"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    git_commit: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    authored_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    author_name: Mapped[str] = mapped_column(Text)
    author_source: Mapped[str] = mapped_column(String(16))  # app | git | unattributed
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime] = _created()


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    ord: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None] = mapped_column(Text)
    part: Mapped[str | None] = mapped_column(String(8))  # slide | page
    part_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(8), default="en")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # live: part of the approved version (used in answers); current: part of
    # the latest version in the vault. Current-but-not-live = unapproved change.
    live: Mapped[bool] = mapped_column(Boolean, default=True)
    current: Mapped[bool] = mapped_column(Boolean, default=True)
    tsv = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('english', coalesce(heading, '')), 'A') || "
            "to_tsvector('english', text)",
            persisted=True,
        ),
    )


class DocumentLink(Base):
    __tablename__ = "document_links"
    id: Mapped[uuid.UUID] = _uuid_pk()
    from_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    target: Mapped[str] = mapped_column(Text)
    to_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    embed: Mapped[bool] = mapped_column(Boolean, default=False)


class AttachmentPart(Base):
    __tablename__ = "attachment_parts"
    __table_args__ = (UniqueConstraint("document_id", "part", "number", name="part_once"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    part: Mapped[str] = mapped_column(String(8))
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text, default="")
    speaker_notes: Mapped[str] = mapped_column(Text, default="")


class DocumentTag(Base):
    __tablename__ = "document_tags"
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag: Mapped[str] = mapped_column(String(128), primary_key=True)


class VaultState(Base):
    """Indexer bookkeeping, e.g. the last indexed commit."""

    __tablename__ = "vault_state"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class ClassificationProposal(Base):
    """What the AI Classifier suggested for one version of a document (plan §4.1).

    Holds the model's reasoning and the passages it relied on, so it is read
    only through the review API (never granted to sop_reader)."""

    __tablename__ = "classification_proposals"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64))
    proposed_space: Mapped[str | None] = mapped_column(String(64))  # None = unsure
    proposed_sensitivity: Mapped[str] = mapped_column(String(16))
    proposed_shared_with: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float)
    rationale: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    names: Mapped[list] = mapped_column(JSONB, default=list)
    model: Mapped[str] = mapped_column(String(128))
    # pending | auto_applied | approved | rejected | superseded | recorded
    status: Mapped[str] = mapped_column(String(16), index=True)
    # what the one-way rule did: auto_tighten | queued | quarantined | unchanged
    decision: Mapped[str] = mapped_column(String(16))
    group_key: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class KnownName(Base):
    """Names a reviewer has looked at: `safe` names stop flagging notes, `client`
    names are the client list that builds up over time (plan §4.1)."""

    __tablename__ = "known_names"
    name: Mapped[str] = mapped_column(Text, primary_key=True)  # lower-cased
    kind: Mapped[str] = mapped_column(String(16))  # safe | client
    added_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    added_at: Mapped[datetime] = _created()


class Conversation(Base):
    """A user's chat thread. Private to that user (no API reads anyone else's)."""

    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class ChatMessage(Base):
    __tablename__ = "messages"
    id: Mapped[uuid.UUID] = _uuid_pk()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text, default="")
    # assistant only: [{space, text, no_answer, confidence, model, tier, ...}]
    sections: Mapped[list] = mapped_column(JSONB, default=list)
    route: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class MessageCitation(Base):
    __tablename__ = "message_citations"
    id: Mapped[uuid.UUID] = _uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    space: Mapped[str] = mapped_column(String(64))
    n: Mapped[int] = mapped_column(Integer)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    git_commit: Mapped[str | None] = mapped_column(String(64))
    part: Mapped[str | None] = mapped_column(String(8))
    part_number: Mapped[int | None] = mapped_column(Integer)


class MessageFeedback(Base):
    __tablename__ = "message_feedback"
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    helpful: Mapped[bool] = mapped_column(Boolean)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class GapEvent(Base):
    """A question a space couldn't answer well (plan §7). Holds no question text:
    it links to the question (a chat message or a search), and reports only
    ever show counts (HR) or anonymous example questions (the space's leads)."""

    __tablename__ = "gap_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    space: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    # no_answer | low_confidence | not_helpful | requested
    reason: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = _created()
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    question_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE")
    )
    search_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_events.id", ondelete="CASCADE")
    )
    topic_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("gap_topics.id", ondelete="SET NULL"), index=True
    )


class SopApproval(Base):
    """One approved version of a document (plan §6). `method`: review (a lead
    approved someone else's change), self (the lead approved their own change),
    baseline (already published when the platform was first connected)."""

    __tablename__ = "sop_approvals"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    git_commit: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))  # governed hash
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    method: Mapped[str] = mapped_column(String(16))
    review_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReviewRequest(Base):
    """A change submitted for review. Bound to one version: if the note changes
    again before approval, approving this request is refused."""

    __tablename__ = "review_requests"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    git_commit: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    base_commit: Mapped[str | None] = mapped_column(String(64))  # last approved version
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    # open | approved | changes_requested | superseded | withdrawn
    status: Mapped[str] = mapped_column(String(20), index=True)
    summary: Mapped[str | None] = mapped_column(Text)  # local model; quotes the note
    summary_model: Mapped[str | None] = mapped_column(String(128))
    summary_failed: Mapped[int] = mapped_column(Integer, default=0)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _created()


class Notification(Base):
    """In-app notification. Holds ids only; titles are looked up (and permission
    checked) when the user lists them."""

    __tablename__ = "notifications"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    ref_id: Mapped[str | None] = mapped_column(String(64))
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = _created()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    """Outbox for outbound webhooks (plan §8). Payloads hold ids only."""

    __tablename__ = "webhook_deliveries"
    id: Mapped[uuid.UUID] = _uuid_pk()
    event: Mapped[str] = mapped_column(String(32))
    url: Mapped[str] = mapped_column(Text)
    secret_env: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()


class Handover(Base):
    """In-flight work passed to colleagues (plan §7). The text lives in a vault
    note under the handover folder; this row tracks who receives it."""

    __tablename__ = "handovers"
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    space: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | sent | acknowledged
    fields: Mapped[dict] = mapped_column(JSONB, default=dict)  # names clients; API-only
    created_at: Mapped[datetime] = _created()
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    receivers: Mapped[list[HandoverReceiver]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


class HandoverReceiver(Base):
    __tablename__ = "handover_receivers"
    handover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class HandoverComment(Base):
    __tablename__ = "handover_comments"
    id: Mapped[uuid.UUID] = _uuid_pk()
    handover_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("handovers.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class SearchEvent(Base):
    """A Library search, kept for the user's own "gaps from your searches"
    (plan §7). Private to that user; deleted after the retention period."""

    __tablename__ = "search_events"
    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    query: Mapped[str] = mapped_column(Text)
    vector: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    results: Mapped[int] = mapped_column(Integer)
    best_distance: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = _created()


class GapTopic(Base):
    """Similar unanswered questions in one space, grouped nightly (plan §7)."""

    __tablename__ = "gap_topics"
    id: Mapped[uuid.UUID] = _uuid_pk()
    space: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(Text)  # written from the questions only
    programme: Mapped[str | None] = mapped_column(Text)
    stage: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="open")
    centroid: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    size: Mapped[int] = mapped_column(Integer, default=0)
    # a document that covers the topic but the askers couldn't read (leads only)
    access_gap_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status_changed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    addressed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = _created()


class Conflict(Base):
    """Two live SOPs the Librarian checked for contradictions (plan §7)."""

    __tablename__ = "conflicts"
    __table_args__ = (
        UniqueConstraint("document_a", "document_b", "hash_a", "hash_b", name="conflict_once"),
    )
    id: Mapped[uuid.UUID] = _uuid_pk()
    document_a: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    document_b: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    hash_a: Mapped[str] = mapped_column(String(64))
    hash_b: Mapped[str] = mapped_column(String(64))
    conflict: Mapped[bool] = mapped_column(Boolean)
    explanation: Mapped[str] = mapped_column(Text, default="")  # quotes both SOPs
    model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))  # open | dismissed | checked
    created_at: Mapped[datetime] = _created()


class Retraction(Base):
    """A purge from the index and history (plan §7). A term is never stored,
    only its hash; `result` holds counts."""

    __tablename__ = "retractions"
    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(16))  # document | term
    vault_path: Mapped[str | None] = mapped_column(Text, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    term_hash: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _created()


class Project(Base):
    """A cross-department project (plan §4, project spaces). Its own space
    (`p-<slug>`, notes under `Projects/<slug>/`), a lead, members, and shares
    of department spaces that each department's lead approves."""

    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(120))
    space: Mapped[str] = mapped_column(ForeignKey("spaces.name"), unique=True)
    folder: Mapped[str] = mapped_column(String(300))
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created()

    members: Mapped[list[ProjectMember]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )
    shares: Mapped[list[ProjectShare]] = relationship(cascade="all, delete-orphan", lazy="selectin")

    def active(self, today: date) -> bool:
        return self.closed_at is None and self.starts_on <= today <= self.ends_on


class ProjectMember(Base):
    __tablename__ = "project_members"
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    added_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = _created()


class ProjectShare(Base):
    """One department space shared with a project. Nothing is shared until that
    space's lead approves; they choose the whole space or selected folders/SOPs
    and the level (internal unless they pick restricted)."""

    __tablename__ = "project_shares"
    __table_args__ = (UniqueConstraint("project_id", "space", name="uq_project_share_space"),)
    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    space: Mapped[str] = mapped_column(ForeignKey("spaces.name"))
    status: Mapped[str] = mapped_column(String(16))  # requested|approved|declined|revoked
    scope: Mapped[str | None] = mapped_column(String(16))  # space | selected
    max_sensitivity: Mapped[str] = mapped_column(String(16), default="internal")
    folders: Mapped[list] = mapped_column(JSONB, default=list)
    documents: Mapped[list] = mapped_column(JSONB, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_until: Mapped[date | None] = mapped_column(Date)
    renewal_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
