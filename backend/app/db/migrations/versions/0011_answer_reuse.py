"""answer_reuse: stored department answers, reused for the same question asked
against the same approved passages (plan §5.2 lever 5); search outcomes
(results opened, whether any helped) for "gaps from your searches" (plan §7)

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "answer_reuse",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("space", sa.String(64), nullable=False),
        sa.Column("section", postgresql.JSONB(), nullable=False),
        sa.Column("document_ids", postgresql.ARRAY(sa.UUID()), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_answer_reuse_documents", "answer_reuse", ["document_ids"], postgresql_using="gin"
    )
    op.add_column(
        "search_events", sa.Column("opened", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("search_events", sa.Column("used", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("search_events", "used")
    op.drop_column("search_events", "opened")
    op.drop_index("ix_answer_reuse_documents", table_name="answer_reuse")
    op.drop_table("answer_reuse")
