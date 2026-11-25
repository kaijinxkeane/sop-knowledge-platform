"""Required reading and sign-off (frontend spec §9.2)

- reading_assignments: a lead marks an SOP as must-read for people or roles
- read_acknowledgements: "I have read version N", append-only (no updates)
- sop_approvals.material_change: approving with it makes earlier
  acknowledgements stop counting, so assignees read again

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sop_approvals",
        sa.Column("material_change", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "reading_assignments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("target_type", sa.String(8), nullable=False),  # user | role
        sa.Column("target", sa.String(64), nullable=False),  # user id or role name
        sa.Column("due_on", sa.Date, nullable=True),
        sa.Column("assigned_by", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("target_type IN ('user', 'role')", name="reading_target_type"),
        sa.UniqueConstraint("document_id", "target_type", "target", name="reading_once"),
    )
    op.create_table(
        "read_acknowledgements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "document_id",
            UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "approval_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sop_approvals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer, nullable=False),  # 1 = first approved version
        sa.Column("git_commit", sa.String(64), nullable=True),
        sa.Column(
            "acknowledged_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Append-only: an acknowledgement is never edited (deletes stay possible
    # for the retention job and retractions).
    op.execute(
        """
        CREATE FUNCTION read_ack_no_update() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'read acknowledgements are append-only';
        END $$;
        """
    )
    op.execute(
        "CREATE TRIGGER read_ack_append_only BEFORE UPDATE ON read_acknowledgements "
        "FOR EACH ROW EXECUTE FUNCTION read_ack_no_update()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS read_ack_append_only ON read_acknowledgements")
    op.execute("DROP FUNCTION IF EXISTS read_ack_no_update()")
    op.drop_table("read_acknowledgements")
    op.drop_table("reading_assignments")
    op.drop_column("sop_approvals", "material_change")
