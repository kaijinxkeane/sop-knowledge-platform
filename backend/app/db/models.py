"""ORM models for identity, permissions, audit and document access (plan §9).

`documents` and `document_access` are the minimal Phase 1 shape needed to
enforce row-level security; Phase 2 adds versions, chunks and attachments.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
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

    access: Mapped[list[DocumentAccess]] = relationship(
        cascade="all, delete-orphan", lazy="selectin"
    )


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
