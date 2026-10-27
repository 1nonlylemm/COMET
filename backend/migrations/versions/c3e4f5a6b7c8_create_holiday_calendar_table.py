"""create holiday_calendar table for statutory holidays and work suspensions

Revision ID: c3e4f5a6b7c8
Revises: b1d2e3f4a5b6
Create Date: 2026-09-05 21:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e4f5a6b7c8'
down_revision = 'b1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'holiday_calendar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('holiday_date', sa.Date(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('holiday_type', sa.String(length=30), nullable=False),
        sa.Column('is_non_working', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('scope', sa.String(length=20), server_default='national', nullable=False),
        sa.Column('lgu_id', sa.Integer(), nullable=True),
        sa.Column('source_reference', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['lgu_id'], ['lgu_profiles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('holiday_date', 'scope', 'lgu_id', name='uq_holiday_date_scope_lgu'),
    )
    op.create_index('ix_holiday_calendar_holiday_date', 'holiday_calendar', ['holiday_date'])
    op.create_index('ix_holiday_calendar_lgu_id', 'holiday_calendar', ['lgu_id'])
    op.create_index('idx_holiday_calendar_lookup', 'holiday_calendar', ['holiday_date', 'scope', 'is_non_working'])


def downgrade():
    op.drop_index('idx_holiday_calendar_lookup', table_name='holiday_calendar')
    op.drop_index('ix_holiday_calendar_lgu_id', table_name='holiday_calendar')
    op.drop_index('ix_holiday_calendar_holiday_date', table_name='holiday_calendar')
    op.drop_table('holiday_calendar')
