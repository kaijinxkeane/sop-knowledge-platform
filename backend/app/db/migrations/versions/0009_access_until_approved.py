"""Access stays as approved until a widening change is approved

documents.approved_access: the access rows in force when the live version was
approved. documents.pending_access: the (wider) rows the latest version asks
for, applied when it is approved. Existing approved documents are backfilled
with their current rows.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("approved_access", postgresql.JSONB(), nullable=True))
    op.add_column("documents", sa.Column("pending_access", postgresql.JSONB(), nullable=True))
    op.execute("""
        UPDATE documents d SET approved_access = (
          SELECT coalesce(jsonb_agg(jsonb_build_array(a.space, a.role, a.sensitivity, a.source)),
                          '[]'::jsonb)
          FROM document_access a WHERE a.document_id = d.id)
        WHERE d.approved_hash IS NOT NULL""")


def downgrade() -> None:
    op.drop_column("documents", "pending_access")
    op.drop_column("documents", "approved_access")
