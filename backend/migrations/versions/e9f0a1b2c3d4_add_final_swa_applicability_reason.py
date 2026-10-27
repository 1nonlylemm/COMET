"""add final swa applicability reason

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-08-08 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9f0a1b2c3d4'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('completion_milestones', schema=None) as batch_op:
        batch_op.add_column(sa.Column('final_swa_applicability_reason', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('completion_milestones', schema=None) as batch_op:
        batch_op.drop_column('final_swa_applicability_reason')
