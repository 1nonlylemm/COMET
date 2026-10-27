"""add appendix_reference to non_infra_monitoring and beneficiary_evidence records

Revision ID: a7c8e9f1d2b3
Revises: e8a1b2c3d4f5
Create Date: 2026-09-04 12:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c8e9f1d2b3'
down_revision = 'e8a1b2c3d4f5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('non_infra_monitoring_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appendix_reference', sa.String(length=50), nullable=True))

    with op.batch_alter_table('beneficiary_evidence_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appendix_reference', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('beneficiary_evidence_records', schema=None) as batch_op:
        batch_op.drop_column('appendix_reference')

    with op.batch_alter_table('non_infra_monitoring_records', schema=None) as batch_op:
        batch_op.drop_column('appendix_reference')
