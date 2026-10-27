"""expand nlp scan review metadata

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-04-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('nlp_scan_results', schema=None) as batch_op:
        batch_op.add_column(sa.Column('suggested_project_requirement_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('review_notes', sa.Text(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_nlp_scan_results_suggested_project_requirement_id'),
            ['suggested_project_requirement_id'],
            unique=False,
        )
        batch_op.create_foreign_key(
            'fk_nlp_scan_results_suggested_pr_id',
            'project_requirements',
            ['suggested_project_requirement_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_nlp_scan_results_reviewed_by',
            'users',
            ['reviewed_by'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('nlp_scan_results', schema=None) as batch_op:
        batch_op.drop_constraint('fk_nlp_scan_results_reviewed_by', type_='foreignkey')
        batch_op.drop_constraint(
            'fk_nlp_scan_results_suggested_pr_id',
            type_='foreignkey',
        )
        batch_op.drop_index(batch_op.f('ix_nlp_scan_results_suggested_project_requirement_id'))
        batch_op.drop_column('review_notes')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('suggested_project_requirement_id')
