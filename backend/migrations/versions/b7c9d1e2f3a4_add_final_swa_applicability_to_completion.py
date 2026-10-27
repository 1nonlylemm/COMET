"""add final SWA applicability to completion milestones

Revision ID: b7c9d1e2f3a4
Revises: f1c2b3d4e5f6
Create Date: 2026-04-11 17:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7c9d1e2f3a4'
down_revision = 'f1c2b3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('completion_milestones', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_final_swa_applicable',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    op.execute(
        """
        UPDATE completion_milestones
        SET is_final_swa_applicable = CASE
            WHEN EXISTS (
                SELECT 1
                FROM projects
                JOIN programs ON programs.id = projects.program_id
                WHERE projects.id = completion_milestones.project_id
                  AND programs.program_type IN ('infrastructure', 'hybrid')
            )
            THEN true
            ELSE false
        END
        """
    )


def downgrade():
    with op.batch_alter_table('completion_milestones', schema=None) as batch_op:
        batch_op.drop_column('is_final_swa_applicable')
