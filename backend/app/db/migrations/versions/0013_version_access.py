"""document_versions.access: the access each version had (decks and PDFs keep
no labels in the file, so old versions are judged by this snapshot)

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("access", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_versions", "access")
