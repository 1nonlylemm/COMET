"""add shared document workflow (requirement categories, workflow states)

Revision ID: a1b2c3d4e5f6
Revises: f9c0d1e2f3a4
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'f9c0d1e2f3a4'
branch_labels = None
depends_on = None


DOCUMENT_CATEGORY_VALUES = (
    "'monthly_progress_report', 'form_3', 'form_3_mov', 'project_exception_report', "
    "'apm_template', 'non_infra_monitoring_evidence', 'signed_distribution_list', "
    "'acknowledgement_receipt', 'beneficiary_tracking_record', 'turnover_photos', "
    "'delivery_invoice', 'final_swa', 'final_inspection_report', "
    "'certificate_of_final_acceptance', 'final_sord', 'proof_of_return_of_funds'"
)

WORKFLOW_STATUS_VALUES = (
    "'draft', 'submitted', 'under_verification', 'staff_approved', "
    "'pending_provincial_approval', 'approved', 'returned_for_revision', 'resubmitted'"
)

WORKFLOW_ACTION_VALUES = (
    "'submit', 'verify', 'staff_approve', 'provincial_approve', "
    "'return_for_revision', 'resubmit'"
)


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            "notification_type IN ("
            "'sla_warning', 'sla_breached', 'escalation_generated', "
            "'status_change_requested', 'submission_received', 'report_ready', "
            "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', "
            "'workflow_document_submitted', 'workflow_document_returned', "
            "'workflow_staff_approved', 'workflow_pending_provincial_approval', "
            "'workflow_document_approved'"
            ")",
        )

    with op.batch_alter_table('requirements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_category', sa.String(length=60), nullable=True))
        batch_op.create_check_constraint(
            'ck_requirement_document_category',
            f'document_category IS NULL OR document_category IN ({DOCUMENT_CATEGORY_VALUES})',
        )

    with op.batch_alter_table('project_requirements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_category', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('workflow_status', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('workflow_submitted_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('workflow_submitted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('workflow_staff_reviewer_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('workflow_staff_approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('workflow_provincial_reviewer_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('workflow_approved_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('workflow_return_reason', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('workflow_returned_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('workflow_returned_at', sa.DateTime(), nullable=True))
        batch_op.create_index(
            batch_op.f('ix_project_requirements_document_category'), ['document_category'], unique=False,
        )
        batch_op.create_index(
            batch_op.f('ix_project_requirements_workflow_status'), ['workflow_status'], unique=False,
        )
        batch_op.create_index('idx_project_req_workflow_status', ['workflow_status'], unique=False)
        batch_op.create_check_constraint(
            'ck_project_req_document_category',
            f'document_category IS NULL OR document_category IN ({DOCUMENT_CATEGORY_VALUES})',
        )
        batch_op.create_check_constraint(
            'ck_project_req_workflow_status',
            f'workflow_status IS NULL OR workflow_status IN ({WORKFLOW_STATUS_VALUES})',
        )
        batch_op.create_foreign_key(
            'fk_project_req_workflow_submitted_by', 'users', ['workflow_submitted_by'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_project_req_workflow_staff_reviewer_id', 'users', ['workflow_staff_reviewer_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_project_req_workflow_provincial_reviewer_id', 'users', ['workflow_provincial_reviewer_id'], ['id'], ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_project_req_workflow_returned_by', 'users', ['workflow_returned_by'], ['id'], ondelete='SET NULL',
        )

    op.create_table(
        'requirement_workflow_transitions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('from_status', sa.String(length=30), nullable=True),
        sa.Column('to_status', sa.String(length=30), nullable=False),
        sa.Column('action', sa.String(length=30), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'to_status IN ({WORKFLOW_STATUS_VALUES})',
            name='ck_workflow_transition_to_status',
        ),
        sa.CheckConstraint(
            f'action IN ({WORKFLOW_ACTION_VALUES})',
            name='ck_workflow_transition_action',
        ),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_requirement_workflow_transitions_project_requirement_id'),
        'requirement_workflow_transitions',
        ['project_requirement_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_requirement_workflow_transitions_actor_id'),
        'requirement_workflow_transitions',
        ['actor_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_requirement_workflow_transitions_created_at'),
        'requirement_workflow_transitions',
        ['created_at'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        op.f('ix_requirement_workflow_transitions_created_at'),
        table_name='requirement_workflow_transitions',
    )
    op.drop_index(
        op.f('ix_requirement_workflow_transitions_actor_id'),
        table_name='requirement_workflow_transitions',
    )
    op.drop_index(
        op.f('ix_requirement_workflow_transitions_project_requirement_id'),
        table_name='requirement_workflow_transitions',
    )
    op.drop_table('requirement_workflow_transitions')

    with op.batch_alter_table('project_requirements', schema=None) as batch_op:
        batch_op.drop_constraint('fk_project_req_workflow_returned_by', type_='foreignkey')
        batch_op.drop_constraint('fk_project_req_workflow_provincial_reviewer_id', type_='foreignkey')
        batch_op.drop_constraint('fk_project_req_workflow_staff_reviewer_id', type_='foreignkey')
        batch_op.drop_constraint('fk_project_req_workflow_submitted_by', type_='foreignkey')
        batch_op.drop_constraint('ck_project_req_workflow_status', type_='check')
        batch_op.drop_constraint('ck_project_req_document_category', type_='check')
        batch_op.drop_index('idx_project_req_workflow_status')
        batch_op.drop_index(batch_op.f('ix_project_requirements_workflow_status'))
        batch_op.drop_index(batch_op.f('ix_project_requirements_document_category'))
        batch_op.drop_column('workflow_returned_at')
        batch_op.drop_column('workflow_returned_by')
        batch_op.drop_column('workflow_return_reason')
        batch_op.drop_column('workflow_approved_at')
        batch_op.drop_column('workflow_provincial_reviewer_id')
        batch_op.drop_column('workflow_staff_approved_at')
        batch_op.drop_column('workflow_staff_reviewer_id')
        batch_op.drop_column('workflow_submitted_at')
        batch_op.drop_column('workflow_submitted_by')
        batch_op.drop_column('workflow_status')
        batch_op.drop_column('document_category')

    with op.batch_alter_table('requirements', schema=None) as batch_op:
        batch_op.drop_constraint('ck_requirement_document_category', type_='check')
        batch_op.drop_column('document_category')

    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            "notification_type IN ("
            "'sla_warning', 'sla_breached', 'escalation_generated', "
            "'status_change_requested', 'submission_received', 'report_ready', "
            "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due'"
            ")",
        )
