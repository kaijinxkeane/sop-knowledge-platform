"""Knowledge retention: per-person readers, handovers, gap topics, search history,
conflicts, retractions, leaving dates

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21

Visibility v3 (must match app.policy.engine.can_view_document): a document can
also be read by people listed in document_readers. Handover notes have no
space rows at all, so this is the only way to read them.
"""

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_ME = "NULLIF(current_setting('sop.user_id', true), '')"

DOC_VISIBLE_V3 = f"""
CREATE OR REPLACE FUNCTION sop_doc_visible(doc uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM documents d
    WHERE d.id = doc AND (
      (d.author_id IS NOT NULL AND d.author_id::text = {_ME})
      OR EXISTS (
        SELECT 1 FROM document_readers r
        WHERE r.document_id = d.id AND r.user_id::text = {_ME}
      )
      OR EXISTS (
        SELECT 1 FROM document_access a
        WHERE a.document_id = d.id
          AND GREATEST(sop_sensitivity_rank(a.sensitivity),
                       CASE WHEN cardinality(d.safeguards) > 0 THEN 2 ELSE 0 END)
              <= sop_scope_rank(a.space)
          AND (d.status NOT IN ('draft', 'in_review')
               OR (NULLIF(current_setting('sop.review_spaces', true), '')::jsonb ? a.space))
      )
    )
  )
$$
"""
DOC_VISIBLE_V2 = """
CREATE OR REPLACE FUNCTION sop_doc_visible(doc uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM documents d
    WHERE d.id = doc AND (
      (d.author_id IS NOT NULL
       AND d.author_id::text = NULLIF(current_setting('sop.user_id', true), ''))
      OR EXISTS (
        SELECT 1 FROM document_access a
        WHERE a.document_id = d.id
          AND GREATEST(sop_sensitivity_rank(a.sensitivity),
                       CASE WHEN cardinality(d.safeguards) > 0 THEN 2 ELSE 0 END)
              <= sop_scope_rank(a.space)
          AND (d.status NOT IN ('draft', 'in_review')
               OR (NULLIF(current_setting('sop.review_spaces', true), '')::jsonb ? a.space))
      )
    )
  )
$$
"""


def _created():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _fk(name, table, ondelete="CASCADE", nullable=False, index=True):
    return sa.Column(
        name,
        sa.UUID(),
        sa.ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
        index=index,
    )


def upgrade() -> None:
    op.add_column("users", sa.Column("leaving_on", sa.Date(), nullable=True))

    op.create_table(
        "document_readers",
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("reason", sa.String(16), nullable=False),  # author | receiver | lead | ceo
    )
    op.execute("GRANT SELECT ON document_readers TO sop_reader")
    op.execute("ALTER TABLE document_readers ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY own_rows ON document_readers FOR SELECT TO sop_reader "
        f"USING (user_id::text = {_ME})"
    )
    op.execute(DOC_VISIBLE_V3)

    op.create_table(
        "handovers",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("document_id", "documents"),
        sa.Column("space", sa.String(64), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=False, index=True),
        sa.Column("status", sa.String(16), nullable=False),  # draft | sent | acknowledged
        # the form fields the note was rendered from (names clients; API-only)
        sa.Column("fields", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created(),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "handover_receivers",
        sa.Column(
            "handover_id",
            sa.UUID(),
            sa.ForeignKey("handovers.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "handover_comments",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("handover_id", "handovers"),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        _created(),
    )

    op.create_table(
        "search_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("user_id", "users"),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("vector", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("results", sa.Integer(), nullable=False),
        sa.Column("best_distance", sa.Float(), nullable=True),
        _created(),
    )
    op.create_table(
        "gap_topics",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("space", sa.String(64), nullable=False, index=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("programme", sa.Text(), nullable=True),
        sa.Column("stage", sa.String(32), nullable=True),
        # open | training_planned | addressed
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("centroid", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("access_gap_document_id", sa.UUID(), nullable=True),
        sa.Column("status_changed_by", sa.UUID(), nullable=True),
        sa.Column("addressed_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.alter_column("gap_events", "message_id", nullable=True)
    op.add_column("gap_events", sa.Column("user_id", sa.UUID(), nullable=True, index=True))
    op.add_column(
        "gap_events",
        sa.Column(
            "question_id",
            sa.UUID(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "gap_events",
        sa.Column(
            "search_event_id",
            sa.UUID(),
            sa.ForeignKey("search_events.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.add_column(
        "gap_events",
        sa.Column(
            "topic_id",
            sa.UUID(),
            sa.ForeignKey("gap_topics.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    op.create_table(
        "conflicts",
        sa.Column("id", sa.UUID(), primary_key=True),
        _fk("document_a", "documents"),
        _fk("document_b", "documents"),
        sa.Column("hash_a", sa.String(64), nullable=False),
        sa.Column("hash_b", sa.String(64), nullable=False),
        sa.Column("conflict", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False, server_default=""),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),  # open | dismissed | checked
        _created(),
        sa.UniqueConstraint("document_a", "document_b", "hash_a", "hash_b", name="conflict_once"),
    )
    op.create_table(
        "retractions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),  # document | term
        sa.Column("vault_path", sa.Text(), nullable=True, index=True),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("term_hash", sa.String(64), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        _created(),
    )


def downgrade() -> None:
    op.drop_table("retractions")
    op.drop_table("conflicts")
    for col in ("topic_id", "search_event_id", "question_id", "user_id"):
        op.drop_column("gap_events", col)
    op.alter_column("gap_events", "message_id", nullable=False)
    op.drop_table("gap_topics")
    op.drop_table("search_events")
    op.drop_table("handover_comments")
    op.drop_table("handover_receivers")
    op.drop_table("handovers")
    op.execute(DOC_VISIBLE_V2)
    op.execute("DROP POLICY IF EXISTS own_rows ON document_readers")
    op.drop_table("document_readers")
    op.drop_column("users", "leaving_on")
