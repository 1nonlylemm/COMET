"""add requirement and submission refs to drive pushes

Revision ID: f1c2b3d4e5f6
Revises: e4b7a1d2c9f0
Create Date: 2026-04-11 15:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1c2b3d4e5f6'
down_revision = 'e4b7a1d2c9f0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('google_drive_pushes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_requirement_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('submission_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('destination_path', sa.String(length=1000), nullable=True))
        batch_op.create_index(batch_op.f('ix_google_drive_pushes_project_requirement_id'), ['project_requirement_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_google_drive_pushes_submission_id'), ['submission_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_google_drive_pushes_project_requirement_id',
            'project_requirements',
            ['project_requirement_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_google_drive_pushes_submission_id',
            'submissions',
            ['submission_id'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('google_drive_pushes', schema=None) as batch_op:
        batch_op.drop_constraint('fk_google_drive_pushes_submission_id', type_='foreignkey')
        batch_op.drop_constraint('fk_google_drive_pushes_project_requirement_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_google_drive_pushes_submission_id'))
        batch_op.drop_index(batch_op.f('ix_google_drive_pushes_project_requirement_id'))
        batch_op.drop_column('destination_path')
        batch_op.drop_column('submission_id')
        batch_op.drop_column('project_requirement_id')
