"""add phase 2a monitoring records (monthly progress, form3, exception report, MAR notifications)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


NOTIFICATION_TYPE_VALUES = (
    "'sla_warning', 'sla_breached', 'escalation_generated', "
    "'status_change_requested', 'submission_received', 'report_ready', "
    "'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due', "
    "'workflow_document_submitted', 'workflow_document_returned', "
    "'workflow_staff_approved', 'workflow_pending_provincial_approval', "
    "'workflow_document_approved', "
    "'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed'"
)

DELAY_REASON_CATEGORY_VALUES = (
    "'force_majeure', 'right_of_way', 'procurement_delay', 'weather', "
    "'funding_delay', 'design_change', 'other'"
)

EXCEPTION_CATEGORY_VALUES = (
    "'force_majeure', 'right_of_way', 'procurement_delay', 'weather', "
    "'funding_delay', 'design_change', 'scope_change', 'other'"
)


def upgrade():
    with op.batch_alter_table('notifications', schema=None) as batch_op:
        batch_op.drop_constraint('ck_notification_type', type_='check')
        batch_op.create_check_constraint(
            'ck_notification_type',
            f'notification_type IN ({NOTIFICATION_TYPE_VALUES})',
        )

    op.create_table(
        'monthly_progress_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('qaar_inspection_id', sa.Integer(), nullable=True),
        sa.Column('evidence_submission_id', sa.Integer(), nullable=True),
        sa.Column('reporting_period', sa.String(length=7), nullable=False),
        sa.Column('assessment_date', sa.Date(), nullable=True),
        sa.Column('physical_accomplishment_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('target_to_date_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('actual_to_date_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('variance_pct', sa.Numeric(6, 2), nullable=True),
        sa.Column('budget_utilization_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('financial_progress_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f"risk_level IS NULL OR risk_level IN ('none', 'minor', 'major', 'severe')",
            name='ck_monthly_progress_risk_level',
        ),
        sa.CheckConstraint(
            'target_to_date_pct IS NULL OR (target_to_date_pct >= 0 AND target_to_date_pct <= 100)',
            name='ck_monthly_progress_target_range',
        ),
        sa.CheckConstraint(
            'actual_to_date_pct IS NULL OR (actual_to_date_pct >= 0 AND actual_to_date_pct <= 100)',
            name='ck_monthly_progress_actual_range',
        ),
        sa.UniqueConstraint('project_id', 'reporting_period', name='uq_monthly_progress_project_period'),
        sa.UniqueConstraint('project_requirement_id', name='uq_monthly_progress_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['qaar_inspection_id'], ['qaar_inspections.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['evidence_submission_id'], ['submissions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_monthly_progress_reports_project_id'), 'monthly_progress_reports', ['project_id'], unique=False)
    op.create_index(op.f('ix_monthly_progress_reports_project_requirement_id'), 'monthly_progress_reports', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_monthly_progress_reports_qaar_inspection_id'), 'monthly_progress_reports', ['qaar_inspection_id'], unique=False)
    op.create_index(op.f('ix_monthly_progress_reports_reporting_period'), 'monthly_progress_reports', ['reporting_period'], unique=False)

    op.create_table(
        'form3_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('mov_submission_id', sa.Integer(), nullable=True),
        sa.Column('reporting_period', sa.String(length=7), nullable=False),
        sa.Column('delay_reason_category', sa.String(length=60), nullable=True),
        sa.Column('justification_text', sa.Text(), nullable=True),
        sa.Column('requested_exemption_start', sa.Date(), nullable=True),
        sa.Column('requested_exemption_end', sa.Date(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'delay_reason_category IS NULL OR delay_reason_category IN ({DELAY_REASON_CATEGORY_VALUES})',
            name='ck_form3_delay_reason_category',
        ),
        sa.CheckConstraint(
            'requested_exemption_start IS NULL OR requested_exemption_end IS NULL '
            'OR requested_exemption_end >= requested_exemption_start',
            name='ck_form3_exemption_date_order',
        ),
        sa.UniqueConstraint('project_requirement_id', name='uq_form3_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mov_submission_id'], ['submissions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_form3_requests_project_id'), 'form3_requests', ['project_id'], unique=False)
    op.create_index(op.f('ix_form3_requests_project_requirement_id'), 'form3_requests', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_form3_requests_reporting_period'), 'form3_requests', ['reporting_period'], unique=False)

    op.create_table(
        'project_exception_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('reporting_period', sa.String(length=7), nullable=False),
        sa.Column('exception_category', sa.String(length=60), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'exception_category IS NULL OR exception_category IN ({EXCEPTION_CATEGORY_VALUES})',
            name='ck_exception_report_category',
        ),
        sa.UniqueConstraint('project_requirement_id', name='uq_exception_report_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_project_exception_reports_project_id'), 'project_exception_reports', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_exception_reports_project_requirement_id'), 'project_exception_reports', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_project_exception_reports_reporting_period'), 'project_exception_reports', ['reporting_period'], unique=False)

    # Seed configurable slippage risk thresholds (Moderate/High boundaries), reusing
    # the existing SystemConfig key/value pattern instead of hard-coding percentages.
    now = sa.text("now()") if op.get_bind().dialect.name != 'sqlite' else sa.text("CURRENT_TIMESTAMP")
    system_configs = sa.table(
        'system_configs',
        sa.column('key', sa.String),
        sa.column('value', sa.Text),
        sa.column('value_type', sa.String),
        sa.column('description', sa.Text),
        sa.column('is_encrypted', sa.Boolean),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
    )
    from datetime import datetime, timezone
    seeded_at = datetime.now(timezone.utc)
    op.execute(
        system_configs.insert().values(
            key='monitoring.risk_threshold_moderate_pct',
            value='5',
            value_type='integer',
            description=(
                'Minimum negative slippage percentage (Target to Date - Actual to Date) '
                'at which a Monthly Progress Report is classified as Moderate Risk (minor).'
            ),
            is_encrypted=False,
            created_at=seeded_at,
            updated_at=seeded_at,
        )
    )
    op.execute(
        system_configs.insert().values(
            key='monitoring.risk_threshold_high_pct',
            value='15',
            value_type='integer',
            description=(
                'Minimum negative slippage percentage (Target to Date - Actual to Date) '
                'at which a Monthly Progress Report is classified as High Risk (severe) '
                'and may auto-trigger a Management Action Report.'
            ),
            is_encrypted=False,
            created_at=seeded_at,
            updated_at=seeded_at,
        )
    )


def downgrade():
    op.execute("DELETE FROM system_configs WHERE key IN ('monitoring.risk_threshold_moderate_pct', 'monitoring.risk_threshold_high_pct')")

    op.drop_index(op.f('ix_project_exception_reports_reporting_period'), table_name='project_exception_reports')
    op.drop_index(op.f('ix_project_exception_reports_project_requirement_id'), table_name='project_exception_reports')
    op.drop_index(op.f('ix_project_exception_reports_project_id'), table_name='project_exception_reports')
    op.drop_table('project_exception_reports')

    op.drop_index(op.f('ix_form3_requests_reporting_period'), table_name='form3_requests')
    op.drop_index(op.f('ix_form3_requests_project_requirement_id'), table_name='form3_requests')
    op.drop_index(op.f('ix_form3_requests_project_id'), table_name='form3_requests')
    op.drop_table('form3_requests')

    op.drop_index(op.f('ix_monthly_progress_reports_reporting_period'), table_name='monthly_progress_reports')
    op.drop_index(op.f('ix_monthly_progress_reports_qaar_inspection_id'), table_name='monthly_progress_reports')
    op.drop_index(op.f('ix_monthly_progress_reports_project_requirement_id'), table_name='monthly_progress_reports')
    op.drop_index(op.f('ix_monthly_progress_reports_project_id'), table_name='monthly_progress_reports')
    op.drop_table('monthly_progress_reports')

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
