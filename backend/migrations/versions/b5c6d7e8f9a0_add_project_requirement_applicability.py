"""add project requirement applicability fields

Revision ID: b5c6d7e8f9a0
Revises: a6b7c8d9e0f1
Create Date: 2026-10-21 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5c6d7e8f9a0'
down_revision = 'a6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('project_requirements', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('applicability', sa.String(length=30), nullable=False, server_default='applicable')
        )
        batch_op.add_column(sa.Column('applicability_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('applicability_set_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('applicability_set_at', sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            'ck_project_req_applicability',
            "applicability IN ('applicable', 'not_applicable')",
        )
        batch_op.create_foreign_key(
            'fk_project_req_applicability_set_by',
            'users',
            ['applicability_set_by'],
            ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('project_requirements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_req_applicability_set_by', type_='foreignkey')
        batch_op.drop_constraint('ck_project_req_applicability', type_='check')
        batch_op.drop_column('applicability_set_at')
        batch_op.drop_column('applicability_set_by')
        batch_op.drop_column('applicability_reason')
        batch_op.drop_column('applicability')
