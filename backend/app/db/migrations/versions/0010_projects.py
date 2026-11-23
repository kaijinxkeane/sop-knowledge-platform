"""Project spaces: cross-department projects with time-limited, lead-approved sharing

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-22

Visibility v4 (must match app.policy.engine.can_view_document): a published
document can also be read through a *partial* project share (selected folders
or documents of one department's space, approved by its lead), passed per
request in `sop.partial` as [{space, rank, folders, docs}]. The safeguard
floor applies as for any other row. Whole-space shares are ordinary scopes.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_ME = "NULLIF(current_setting('sop.user_id', true), '')"
_FLOOR = "CASE WHEN cardinality(d.safeguards) > 0 THEN 2 ELSE 0 END"


def _visible(partial: bool) -> str:
    extra = (
        f"""
      OR (d.status NOT IN ('draft', 'in_review') AND EXISTS (
        SELECT 1 FROM document_access a,
             jsonb_array_elements(
               coalesce(NULLIF(current_setting('sop.partial', true), '')::jsonb, '[]'::jsonb)
             ) p
        WHERE a.document_id = d.id
          AND a.space = p->>'space'
          AND GREATEST(sop_sensitivity_rank(a.sensitivity), {_FLOOR}) <= (p->>'rank')::int
          AND ((p->'docs') ? d.id::text
               OR EXISTS (SELECT 1 FROM jsonb_array_elements_text(p->'folders') f
                          WHERE starts_with(d.vault_path, f)))
      ))"""
        if partial
        else ""
    )
    return f"""
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
          AND GREATEST(sop_sensitivity_rank(a.sensitivity), {_FLOOR})
              <= sop_scope_rank(a.space)
          AND (d.status NOT IN ('draft', 'in_review')
               OR (NULLIF(current_setting('sop.review_spaces', true), '')::jsonb ? a.space))
      ){extra}
    )
  )
$$
"""


def _created():
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )


def _user(name, nullable=False):
    return sa.Column(
        name, sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "space", sa.String(64), sa.ForeignKey("spaces.name"), nullable=False, unique=True
        ),
        sa.Column("folder", sa.String(300), nullable=False),
        _user("lead_id"),
        _user("created_by"),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        _created(),
    )
    op.create_table(
        "project_members",
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        _user("added_by", nullable=True),
        _created(),
    )
    op.create_index("ix_project_members_user", "project_members", ["user_id"])
    op.create_table(
        "project_shares",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("space", sa.String(64), sa.ForeignKey("spaces.name"), nullable=False),
        # requested | approved | declined | revoked
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("scope", sa.String(16), nullable=True),  # space | selected (set on approval)
        sa.Column("max_sensitivity", sa.String(16), nullable=False, server_default="internal"),
        sa.Column("folders", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("documents", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        _user("requested_by"),
        _user("decided_by", nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_until", sa.Date(), nullable=True),
        # the project was renewed: the lead is asked to confirm for the new period
        sa.Column("renewal_requested", sa.Boolean(), nullable=False, server_default="false"),
        _created(),
        sa.UniqueConstraint("project_id", "space", name="uq_project_share_space"),
    )
    op.execute(_visible(partial=True))
    # Access rows of a partly shared document are readable too (the Library's
    # space filter and the policy engine's second check read them under RLS).
    op.execute("""
CREATE OR REPLACE FUNCTION sop_partial_space(sp text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (
    SELECT 1 FROM jsonb_array_elements(
      coalesce(NULLIF(current_setting('sop.partial', true), '')::jsonb, '[]'::jsonb)) p
    WHERE p->>'space' = sp)
$$""")
    op.execute("DROP POLICY IF EXISTS scoped_read ON document_access")
    op.execute("""
CREATE POLICY scoped_read ON document_access FOR SELECT TO sop_reader
  USING (sop_sensitivity_rank(sensitivity) <= sop_scope_rank(space)
         OR (sop_partial_space(space) AND sop_doc_visible(document_id)))""")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS scoped_read ON document_access")
    op.execute("""
CREATE POLICY scoped_read ON document_access FOR SELECT TO sop_reader
  USING (sop_sensitivity_rank(sensitivity) <= sop_scope_rank(space))""")
    op.execute("DROP FUNCTION IF EXISTS sop_partial_space(text)")
    op.execute(_visible(partial=False))
    op.drop_table("project_shares")
    op.drop_index("ix_project_members_user", table_name="project_members")
    op.drop_table("project_members")
    op.drop_table("projects")
