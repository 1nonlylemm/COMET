"""add system_operational_events table

Revision ID: e5f6a7b8c9d0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-09 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_operational_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('component', sa.String(length=50), nullable=False),
        sa.Column('event_name', sa.String(length=100), nullable=False),
        sa.Column('message', sa.String(length=2000), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('operation_id', sa.String(length=64), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('context_data', sa.JSON(), nullable=True),
        sa.Column('traceback', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_system_operational_events_timestamp'), 'system_operational_events', ['timestamp'], unique=False)
    op.create_index(op.f('ix_system_operational_events_request_id'), 'system_operational_events', ['request_id'], unique=False)
    op.create_index(op.f('ix_system_operational_events_operation_id'), 'system_operational_events', ['operation_id'], unique=False)
    op.create_index(op.f('ix_system_operational_events_user_id'), 'system_operational_events', ['user_id'], unique=False)
    op.create_index('ix_operational_events_severity_timestamp', 'system_operational_events', ['severity', 'timestamp'], unique=False)
    op.create_index('ix_operational_events_component_timestamp', 'system_operational_events', ['component', 'timestamp'], unique=False)


def downgrade():
    op.drop_index('ix_operational_events_component_timestamp', table_name='system_operational_events')
    op.drop_index('ix_operational_events_severity_timestamp', table_name='system_operational_events')
    op.drop_index(op.f('ix_system_operational_events_user_id'), table_name='system_operational_events')
    op.drop_index(op.f('ix_system_operational_events_operation_id'), table_name='system_operational_events')
    op.drop_index(op.f('ix_system_operational_events_request_id'), table_name='system_operational_events')
    op.drop_index(op.f('ix_system_operational_events_timestamp'), table_name='system_operational_events')
    op.drop_table('system_operational_events')
