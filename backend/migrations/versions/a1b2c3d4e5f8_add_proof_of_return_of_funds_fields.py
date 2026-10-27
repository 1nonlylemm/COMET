"""add proof of return of funds fields

Revision ID: a1b2c3d4e5f8
Revises: e9f0a1b2c3d4
Create Date: 2026-08-08 14:28:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f8'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('completion_document_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('returned_amount', sa.Numeric(precision=15, scale=2), nullable=True))
        batch_op.add_column(sa.Column('receipt_number', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('completion_document_records', schema=None) as batch_op:
        batch_op.drop_column('receipt_number')
        batch_op.drop_column('returned_amount')
