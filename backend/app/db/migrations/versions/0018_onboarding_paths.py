"""Onboarding paths (frontend spec §9.1)

- reading_paths: a lead's ordered path for a space (e.g. "New trainer")
- path_items: SOPs, decks and worksheets in steps; some marked required
- path_assignments: a path for a person or everyone with a role
- path_progress: "Done" on an item that isn't required reading

A required item counts as done when its SOP is acknowledged (read_acknowledgements).

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reading_paths",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("space", sa.String(64), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "path_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("reading_paths.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step", sa.Integer, nullable=False),
        sa.Column("step_title", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "path_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "path_id",
            UUID(as_uuid=True),
            sa.ForeignKey("reading_paths.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("target_type", sa.String(8), nullable=False),
        sa.Column("target", sa.String(64), nullable=False),
        sa.Column("due_on", sa.Date, nullable=True),
        sa.Column("assigned_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("target_type IN ('user', 'role')", name="path_target_type"),
        sa.UniqueConstraint("path_id", "target_type", "target", name="path_assigned_once"),
    )
    op.create_table(
        "path_progress",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("path_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "done_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("path_progress")
    op.drop_table("path_assignments")
    op.drop_table("path_items")
    op.drop_table("reading_paths")
