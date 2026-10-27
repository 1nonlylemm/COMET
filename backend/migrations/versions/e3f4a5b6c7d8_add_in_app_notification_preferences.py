"""add in_app notification preferences

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-16 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = 'd2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'user_notification_preferences',
        sa.Column('in_app_critical_alerts', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )
    op.add_column(
        'user_notification_preferences',
        sa.Column('in_app_deadline_reminders', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )
    op.add_column(
        'user_notification_preferences',
        sa.Column('in_app_review_reminders', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )
    op.add_column(
        'user_notification_preferences',
        sa.Column('in_app_workflow_notifications', sa.Boolean(), nullable=False, server_default=sa.text('true'))
    )


def downgrade():
    op.drop_column('user_notification_preferences', 'in_app_workflow_notifications')
    op.drop_column('user_notification_preferences', 'in_app_review_reminders')
    op.drop_column('user_notification_preferences', 'in_app_deadline_reminders')
    op.drop_column('user_notification_preferences', 'in_app_critical_alerts')
