"""add reference number to beneficiary evidence

Revision ID: b1c2d3e4f5g9
Revises: a1b2c3d4e5f8
Create Date: 2026-08-08 14:52:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5g9'
down_revision = 'a1b2c3d4e5f8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('beneficiary_evidence_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reference_number', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('beneficiary_evidence_records', schema=None) as batch_op:
        batch_op.drop_column('reference_number')
