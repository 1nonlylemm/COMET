"""add is_provisional to holiday_calendar

Revision ID: d4f5a6b7c8d9
Revises: c3e4f5a6b7c8
Create Date: 2026-09-05 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f5a6b7c8d9'
down_revision = 'c3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'holiday_calendar',
        sa.Column('is_provisional', sa.Boolean(), nullable=False, server_default=sa.text('false'))
    )


def downgrade():
    op.drop_column('holiday_calendar', 'is_provisional')
