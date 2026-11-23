"""bookmarks: ★ on documents, slides, pages and conversations (frontend spec §9.4)

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookmarks",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("target_type", sa.String(16), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("part", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("target_type IN ('document', 'conversation')", name="bookmark_type"),
        # NULLS NOT DISTINCT: one bookmark per whole document, as well as per slide.
        sa.UniqueConstraint(
            "user_id",
            "target_type",
            "target_id",
            "part",
            name="bookmark_once",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_bookmarks_user_id", "bookmarks", ["user_id"])


def downgrade() -> None:
    op.drop_table("bookmarks")
