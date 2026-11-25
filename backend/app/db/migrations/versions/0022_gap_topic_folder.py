"""Gap topics remember the Library folder of the nearest approved document.

Revision ID: 0022
"""

import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("gap_topics", sa.Column("folder", sa.Text))


def downgrade() -> None:
    op.drop_column("gap_topics", "folder")
