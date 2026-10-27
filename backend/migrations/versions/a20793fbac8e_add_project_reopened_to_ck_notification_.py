"""add project_reopened to ck_notification_type

Revision ID: a20793fbac8e
Revises: f03fdc8036c0
Create Date: 2026-08-21 10:45:03.977097

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a20793fbac8e'
down_revision = 'f03fdc8036c0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            "notification_type IN ('sla_warning', 'sla_breached', 'escalation_generated', 'status_change_requested', 'submission_received', 'report_ready', 'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', 'workflow_document_submitted', 'workflow_document_returned', 'workflow_staff_approved', 'workflow_pending_provincial_approval', 'workflow_document_approved', 'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened', 'requirement_privilege_override', 'mar_privilege_override')"
        )

def downgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            "notification_type IN ('sla_warning', 'sla_breached', 'escalation_generated', 'status_change_requested', 'submission_received', 'report_ready', 'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', 'workflow_document_submitted', 'workflow_document_returned', 'workflow_staff_approved', 'workflow_pending_provincial_approval', 'workflow_document_approved', 'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed')"
        )
