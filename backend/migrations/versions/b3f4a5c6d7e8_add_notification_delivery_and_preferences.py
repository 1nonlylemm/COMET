"""add notification delivery and preferences

Revision ID: b3f4a5c6d7e8
Revises: a3e8f1b2c4d5
Create Date: 2026-09-07 07:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3f4a5c6d7e8'
down_revision = 'a3e8f1b2c4d5'
branch_labels = None
depends_on = None

OLD_NOTIFICATION_TYPES = (
    "'requirement_privilege_override', 'mar_privilege_override', "
    "'sla_warning', 'sla_breached', 'escalation_generated', "
    "'status_change_requested', 'submission_received', 'report_ready', "
    "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', "
    "'workflow_document_submitted', 'workflow_document_returned', "
    "'workflow_staff_approved', 'workflow_pending_provincial_approval', "
    "'workflow_document_approved', "
    "'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened'"
)

NEW_NOTIFICATION_TYPES = (
    f"{OLD_NOTIFICATION_TYPES}, "
    "'requirement_missing_reminder', 'submission_unreviewed_reminder', "
    "'revision_pending_reminder', 'resubmission_unreviewed_reminder', "
    "'provincial_approval_reminder'"
)


def upgrade():
    # 1. Extend notifications table
    op.add_column(
        'notifications',
        sa.Column('priority', sa.String(length=20), nullable=False, server_default='normal')
    )
    op.add_column(
        'notifications',
        sa.Column('action_url', sa.String(length=500), nullable=True)
    )
    op.add_column(
        'notifications',
        sa.Column('dedup_key', sa.String(length=255), nullable=True)
    )
    op.create_index(
        op.f('ix_notifications_dedup_key'),
        'notifications',
        ['dedup_key'],
        unique=True
    )

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({NEW_NOTIFICATION_TYPES})"
        )
        batch_op.create_check_constraint(
            'ck_notification_priority',
            "priority IN ('low', 'normal', 'high', 'critical')"
        )

    # 2. Create notification_deliveries table
    op.create_table(
        'notification_deliveries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('notification_id', sa.Integer(), sa.ForeignKey('notifications.id', ondelete='CASCADE'), nullable=False),
        sa.Column('channel', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False, server_default='pending'),
        sa.Column('attempted_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('provider_message_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("channel IN ('in_app', 'email')", name='ck_delivery_channel'),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name='ck_delivery_status'),
        sa.UniqueConstraint('notification_id', 'channel', name='uq_notification_delivery_channel'),
    )
    op.create_index(
        op.f('ix_notification_deliveries_notification_id'),
        'notification_deliveries',
        ['notification_id'],
        unique=False
    )

    # 3. Create user_notification_preferences table
    op.create_table(
        'user_notification_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email_critical_alerts', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_deadline_reminders', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_review_reminders', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_workflow_notifications', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_daily_digest', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('user_id', name='uq_user_notification_preferences_user_id'),
    )
    op.create_index(
        op.f('ix_user_notification_preferences_user_id'),
        'user_notification_preferences',
        ['user_id'],
        unique=True
    )


def downgrade():
    op.drop_index(op.f('ix_user_notification_preferences_user_id'), table_name='user_notification_preferences')
    op.drop_table('user_notification_preferences')

    op.drop_index(op.f('ix_notification_deliveries_notification_id'), table_name='notification_deliveries')
    op.drop_table('notification_deliveries')

    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('ck_notification_priority', type_='check')
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({OLD_NOTIFICATION_TYPES})"
        )

    op.drop_index(op.f('ix_notifications_dedup_key'), table_name='notifications')
    op.drop_column('notifications', 'dedup_key')
    op.drop_column('notifications', 'action_url')
    op.drop_column('notifications', 'priority')
