"""message_feedback.reason: why an answer wasn't helpful (frontend spec §4)

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message_feedback", sa.Column("reason", sa.String(16), nullable=True))
    op.create_check_constraint(
        "feedback_reason",
        "message_feedback",
        "reason IS NULL OR reason IN ('wrong', 'outdated', 'missing_steps', 'unclear', 'other')",
    )


def downgrade() -> None:
    op.drop_constraint("feedback_reason", "message_feedback")
    op.drop_column("message_feedback", "reason")
