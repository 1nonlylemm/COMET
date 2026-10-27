"""remove dead notification types status_change_requested and report_ready

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-16 23:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f4a5b6c7d8e9'
down_revision = 'e3f4a5b6c7d8'
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
    "'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened', "
    "'requirement_missing_reminder', 'submission_unreviewed_reminder', "
    "'revision_pending_reminder', 'resubmission_unreviewed_reminder', "
    "'provincial_approval_reminder', 'security_alert', 'compliance_breach'"
)

NEW_NOTIFICATION_TYPES = (
    "'requirement_privilege_override', 'mar_privilege_override', "
    "'sla_warning', 'sla_breached', 'escalation_generated', "
    "'submission_received', "
    "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', "
    "'workflow_document_submitted', 'workflow_document_returned', "
    "'workflow_staff_approved', 'workflow_pending_provincial_approval', "
    "'workflow_document_approved', "
    "'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened', "
    "'requirement_missing_reminder', 'submission_unreviewed_reminder', "
    "'revision_pending_reminder', 'resubmission_unreviewed_reminder', "
    "'provincial_approval_reminder', 'security_alert', 'compliance_breach'"
)


def upgrade():
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({NEW_NOTIFICATION_TYPES})"
        )


def downgrade():
    with op.batch_alter_table('notifications') as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f"notification_type IN ({OLD_NOTIFICATION_TYPES})"
        )
