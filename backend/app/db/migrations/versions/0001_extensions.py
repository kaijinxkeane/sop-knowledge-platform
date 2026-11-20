"""Enable Postgres extensions used by the platform.

Revision ID: 0001
Revises:
Create Date: 2026-11-20
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")  # embeddings (pgvector)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")  # gen_random_uuid(), digests


def downgrade() -> None:
    # Extensions are left in place: dropping them could destroy data in later tables.
    pass
