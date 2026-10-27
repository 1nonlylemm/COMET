"""add escalation notice trigger sla unique index

Revision ID: c4d5e6f7a8b9
Revises: e8a9f0b1c2d3
Create Date: 2026-10-08 20:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'e8a9f0b1c2d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'uq_notice_trigger_sla_type',
        'escalation_notices',
        ['trigger_sla_id', 'notice_type'],
        unique=True,
        postgresql_where=sa.text('trigger_sla_id IS NOT NULL'),
        sqlite_where=sa.text('trigger_sla_id IS NOT NULL'),
    )


def downgrade():
    op.drop_index('uq_notice_trigger_sla_type', table_name='escalation_notices')
