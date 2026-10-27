"""align project statuses to monitoring terms

Revision ID: e1f2a3b4c5d6
Revises: d7e8f9a0b1c2
Create Date: 2026-05-07 22:30:00.000000
"""

from alembic import op


revision = 'e1f2a3b4c5d6'
down_revision = 'd7e8f9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_constraint('ck_project_overall_status', type_='check')

    op.execute(
        """
        UPDATE projects
        SET custom_fields = (
            COALESCE(custom_fields::jsonb, '{}'::jsonb)
            || jsonb_build_object('legacy_overall_status', overall_status)
        )
        WHERE overall_status IN ('active', 'suspended', 'terminated', 'archived')
          AND NOT (COALESCE(custom_fields::jsonb, '{}'::jsonb) ? 'legacy_overall_status')
        """
    )
    op.execute("UPDATE projects SET overall_status = 'ongoing' WHERE overall_status = 'active'")
    op.execute("UPDATE projects SET overall_status = 'cancelled' WHERE overall_status IN ('suspended', 'terminated')")
    op.execute("UPDATE projects SET overall_status = 'completed' WHERE overall_status = 'archived'")

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.alter_column('overall_status', server_default='not_yet_started')
        batch_op.create_check_constraint(
            'ck_project_overall_status',
            "overall_status IN ('not_yet_started', 'ongoing', 'completed', 'cancelled')",
        )


def downgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_constraint('ck_project_overall_status', type_='check')
        batch_op.alter_column('overall_status', server_default='active')

    op.execute("UPDATE projects SET overall_status = 'active' WHERE overall_status = 'ongoing'")
    op.execute("UPDATE projects SET overall_status = 'terminated' WHERE overall_status = 'cancelled'")

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_project_overall_status',
            "overall_status IN ('active', 'suspended', 'terminated', 'completed', 'archived')",
        )

