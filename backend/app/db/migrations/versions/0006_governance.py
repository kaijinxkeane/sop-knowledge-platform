"""SOP governance: version-bound approvals, review requests, live chunks, notifications, webhooks

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21

Chunks gain `live` (the approved version, used in answers) and `current` (the
latest version in the vault). For a document that has an approved version, a
chunk that is not live is an unapproved change: RLS shows it only to the
note's editors (its author, or people with `contribute`/`review` on one of its
spaces). Documents never approved stay readable as before, but are never live.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

# Who may see work in progress on a document (must match
# app.policy.engine.can_see_unapproved): its author, or anyone with
# contribute/review on a space it belongs to (and who can see the document).
DOC_EDITOR = """
CREATE OR REPLACE FUNCTION sop_doc_editor(doc uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT sop_doc_visible(doc) AND EXISTS (
    SELECT 1 FROM documents d
    WHERE d.id = doc AND (
      (d.author_id IS NOT NULL
       AND d.author_id::text = NULLIF(current_setting('sop.user_id', true), ''))
      OR EXISTS (
        SELECT 1 FROM document_access a
        WHERE a.document_id = d.id
          AND (NULLIF(current_setting('sop.edit_spaces', true), '')::jsonb ? a.space)
      )
    )
  )
$$
"""

# Who sees the latest (possibly unapproved) text rather than the approved one.
DOC_WIP = """
CREATE OR REPLACE FUNCTION sop_doc_wip_visible(doc uuid) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT sop_doc_visible(doc) AND (
    EXISTS (SELECT 1 FROM documents d WHERE d.id = doc AND d.approved_hash IS NULL)
    OR sop_doc_editor(doc)
  )
$$
"""

SECURITY_UP = [
    DOC_EDITOR,
    DOC_WIP,
    "REVOKE ALL ON FUNCTION sop_doc_editor(uuid) FROM PUBLIC",
    "REVOKE ALL ON FUNCTION sop_doc_wip_visible(uuid) FROM PUBLIC",
    "GRANT EXECUTE ON FUNCTION sop_doc_editor(uuid) TO sop_reader",
    "GRANT EXECUTE ON FUNCTION sop_doc_wip_visible(uuid) TO sop_reader",
    "DROP POLICY IF EXISTS scoped_read ON chunks",
    "CREATE POLICY scoped_read ON chunks FOR SELECT TO sop_reader "
    "USING (sop_doc_visible(document_id) AND (live OR sop_doc_wip_visible(document_id)))",
]
SECURITY_DOWN = [
    "DROP POLICY IF EXISTS scoped_read ON chunks",
    "CREATE POLICY scoped_read ON chunks FOR SELECT TO sop_reader "
    "USING (sop_doc_visible(document_id))",
    "DROP FUNCTION IF EXISTS sop_doc_wip_visible(uuid)",
    "DROP FUNCTION IF EXISTS sop_doc_editor(uuid)",
]


def _created():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def upgrade() -> None:
    op.add_column(
        "chunks", sa.Column("live", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.add_column(
        "chunks", sa.Column("current", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    # Nothing is approved yet: no existing text is live until the indexer's
    # one-time baseline approves the notes already marked `published`.
    op.execute("UPDATE chunks SET live = false")
    op.add_column("documents", sa.Column("governed_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("approved_hash", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("approved_commit", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("review_due", sa.Date(), nullable=True))

    op.create_table(
        "sop_approvals",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
        ),
        sa.Column("git_commit", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("method", sa.String(16), nullable=False),  # review | self | baseline
        sa.Column("review_request_id", sa.UUID(), nullable=True),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_table(
        "review_requests",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "document_id", sa.UUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), index=True
        ),
        sa.Column("git_commit", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("base_commit", sa.String(64), nullable=True),
        sa.Column("requested_by", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_model", sa.String(128), nullable=True),
        sa.Column("summary_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=False, server_default=""),
        _created(),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), index=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("ref_id", sa.String(64), nullable=True),
        sa.Column("dedupe_key", sa.String(200), nullable=True, unique=True),
        _created(),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("event", sa.String(32), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret_env", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, index=True),  # pending | sent | failed
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
    )
    for stmt in SECURITY_UP:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in SECURITY_DOWN:
        op.execute(stmt)
    op.drop_table("webhook_deliveries")
    op.drop_table("notifications")
    op.drop_table("review_requests")
    op.drop_table("sop_approvals")
    for col in ("review_due", "approved_commit", "approved_hash", "governed_hash"):
        op.drop_column("documents", col)
    op.drop_column("chunks", "current")
    op.drop_column("chunks", "live")
