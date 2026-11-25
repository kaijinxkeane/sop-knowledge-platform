"""Departments can be created in the app: give `manage_spaces` to the roles
config/roles.yaml now gives it to (platform-admin, hr-lead), on databases
whose roles were created before it existed. Roles that don't exist are skipped.

Revision ID: 0019
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add to an existing company-wide grant, or create one.
    op.execute(
        """
        UPDATE grants SET actions = array_append(actions, 'manage_spaces')
        WHERE space IS NULL AND NOT ('manage_spaces' = ANY(actions))
          AND role_id IN (SELECT id FROM roles WHERE name IN ('platform-admin', 'hr-lead'))
          AND id IN (
            SELECT DISTINCT ON (role_id) id FROM grants
            WHERE space IS NULL ORDER BY role_id, id
          )
        """
    )
    op.execute(
        """
        INSERT INTO grants (id, role_id, space, max_sensitivity, actions)
        SELECT gen_random_uuid(), r.id, NULL, 'public', ARRAY['manage_spaces']::varchar[]
        FROM roles r
        WHERE r.name IN ('platform-admin', 'hr-lead')
          AND NOT EXISTS (
            SELECT 1 FROM grants g WHERE g.role_id = r.id AND g.space IS NULL
              AND 'manage_spaces' = ANY(g.actions)
          )
        """
    )


def downgrade() -> None:
    op.execute(
        "UPDATE grants SET actions = array_remove(actions, 'manage_spaces') WHERE space IS NULL"
    )
    op.execute("DELETE FROM grants WHERE space IS NULL AND cardinality(actions) = 0")
