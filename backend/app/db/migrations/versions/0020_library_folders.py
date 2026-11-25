"""Library folders people create inside a department (Library → New folder).

A folder with documents in it is simply where they are in the vault; this
table remembers folders made in the app, so an empty one still shows (git
doesn't keep empty folders). Each belongs to one department.

Revision ID: 0020
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "library_folders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("space", sa.String(64), sa.ForeignKey("spaces.name"), nullable=False),
        sa.Column("path", sa.Text, nullable=False, unique=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("library_folders_space", "library_folders", ["space"])


def downgrade() -> None:
    op.drop_table("library_folders")
