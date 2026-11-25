"""The trained sorter (app/classify/sorter.py) and its suggestions.

`sorter_models` keeps the latest trained model: average fingerprints per
department, level and folder, never text. Proposals remember the sorter's
vote and the folder it suggested, shown to reviewers next to the AI's labels.

Revision ID: 0021
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sorter_models",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trained_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("documents", sa.Integer, nullable=False),
        sa.Column("data", JSONB, nullable=False),
    )
    op.add_column("classification_proposals", sa.Column("suggested_folder", sa.Text))
    op.add_column("classification_proposals", sa.Column("sorter_vote", JSONB))


def downgrade() -> None:
    op.drop_column("classification_proposals", "sorter_vote")
    op.drop_column("classification_proposals", "suggested_folder")
    op.drop_table("sorter_models")
