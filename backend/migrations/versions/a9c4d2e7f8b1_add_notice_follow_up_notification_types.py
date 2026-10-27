"""add notice follow-up notification types

Revision ID: a9c4d2e7f8b1
Revises: f2a4c6d8e0b1
Create Date: 2026-05-01 14:30:00.000000
"""

from alembic import op


revision = 'a9c4d2e7f8b1'
down_revision = 'f2a4c6d8e0b1'
branch_labels = None
depends_on = None


UPGRADED_TYPES = (
    "'sla_warning', 'sla_breached', 'escalation_generated', "
    "'status_change_requested', 'submission_received', 'report_ready', "
    "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due'"
)
DOWNGRADED_TYPES = (
    "'sla_warning', 'sla_breached', 'escalation_generated', "
    "'status_change_requested', 'submission_received', 'report_ready'"
)


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({UPGRADED_TYPES})",
        )


def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({DOWNGRADED_TYPES})",
        )
