"""model_usage: daily model-call totals for the cost dashboard (plan §8.1, Admin)

Counts and token numbers only; no content and no user ids.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_usage",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("tier", sa.String(64), primary_key=True),
        sa.Column("model", sa.String(128), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("location", sa.String(8), nullable=False),
        sa.Column("calls", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fallbacks", sa.Integer, nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger, nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("model_usage")
