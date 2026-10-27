"""add structured qaar monitoring

Revision ID: 0f4b8c2d6e10
Revises: d0e1f2a3b4c5
Create Date: 2026-05-19 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f4b8c2d6e10'
down_revision = 'd0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_kind', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('monitoring_applicability', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('qaar_category', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('subaybayan_project_code', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('subaybayan_url', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('nadai_received_at', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('subaybayan_enrolled_at', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('subaybayan_enrollment_status', sa.String(length=40), nullable=True))
        batch_op.create_index(batch_op.f('ix_projects_subaybayan_project_code'), ['subaybayan_project_code'], unique=False)

    op.create_table(
        'qaar_report_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('office_address', sa.Text(), nullable=True),
        sa.Column('program_name', sa.String(length=200), nullable=True),
        sa.Column('funded_year', sa.Integer(), nullable=True),
        sa.Column('implementing_unit', sa.String(length=200), nullable=True),
        sa.Column('monitoring_office', sa.String(length=200), nullable=True),
        sa.Column('project_id_text', sa.String(length=120), nullable=True),
        sa.Column('project_title', sa.String(length=300), nullable=True),
        sa.Column('national_subsidy', sa.Numeric(15, 2), nullable=True),
        sa.Column('project_location', sa.Text(), nullable=True),
        sa.Column('project_description', sa.Text(), nullable=True),
        sa.Column('planned_accomplishment_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('actual_accomplishment_pct', sa.Numeric(5, 2), nullable=True),
        sa.Column('actual_project_status', sa.String(length=100), nullable=True),
        sa.Column('actual_completion_date', sa.Date(), nullable=True),
        sa.Column('date_started', sa.Date(), nullable=True),
        sa.Column('target_completion_date', sa.Date(), nullable=True),
        sa.Column('lgu_counterpart', sa.Numeric(15, 2), nullable=True),
        sa.Column('liquidation', sa.Numeric(15, 2), nullable=True),
        sa.Column('contractor_name', sa.String(length=300), nullable=True),
        sa.Column('contractor_address', sa.Text(), nullable=True),
        sa.Column('owner_name', sa.String(length=200), nullable=True),
        sa.Column('owner_contact_number', sa.String(length=80), nullable=True),
        sa.Column('pcab_license', sa.String(length=120), nullable=True),
        sa.Column('contract_amount', sa.Numeric(15, 2), nullable=True),
        sa.Column('prepared_by_name', sa.String(length=200), nullable=True),
        sa.Column('prepared_by_position', sa.String(length=200), nullable=True),
        sa.Column('form_data', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('autofill_snapshot', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inspection_id'),
    )
    op.create_index(op.f('ix_qaar_report_summaries_inspection_id'), 'qaar_report_summaries', ['inspection_id'], unique=True)

    op.create_table(
        'qaar_project_management_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('check_key', sa.String(length=120), nullable=False),
        sa.Column('section', sa.String(length=120), nullable=True),
        sa.Column('label', sa.String(length=300), nullable=False),
        sa.Column('response', sa.String(length=30), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=80), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inspection_id', 'check_key', name='uq_qaar_pm_check_key'),
    )
    op.create_index(op.f('ix_qaar_project_management_checks_inspection_id'), 'qaar_project_management_checks', ['inspection_id'], unique=False)

    op.create_table(
        'qaar_work_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('item_code', sa.String(length=80), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity', sa.Numeric(15, 4), nullable=True),
        sa.Column('inspected_quantity', sa.Numeric(15, 4), nullable=True),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('unit_cost', sa.Numeric(15, 2), nullable=True),
        sa.Column('location', sa.Text(), nullable=True),
        sa.Column('source_catalog_row', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_qaar_work_items_inspection_id'), 'qaar_work_items', ['inspection_id'], unique=False)

    op.create_table(
        'qaar_work_findings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('work_item_id', sa.Integer(), nullable=True),
        sa.Column('defect_code', sa.String(length=80), nullable=True),
        sa.Column('defect_description', sa.Text(), nullable=True),
        sa.Column('quality_issue', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('location', sa.Text(), nullable=True),
        sa.Column('degree_of_defect', sa.String(length=40), nullable=True),
        sa.Column('rating_weight', sa.Numeric(8, 4), nullable=True),
        sa.Column('timeline', sa.String(length=200), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('source_catalog_row', sa.Integer(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("risk_level IS NULL OR risk_level IN ('minor', 'major', 'severe')", name='ck_qaar_work_finding_risk_level'),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['work_item_id'], ['qaar_work_items.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_qaar_work_findings_inspection_id'), 'qaar_work_findings', ['inspection_id'], unique=False)
    op.create_index(op.f('ix_qaar_work_findings_work_item_id'), 'qaar_work_findings', ['work_item_id'], unique=False)

    op.create_table(
        'qaar_health_safety_checks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('check_key', sa.String(length=120), nullable=False),
        sa.Column('label', sa.String(length=300), nullable=False),
        sa.Column('response', sa.String(length=30), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inspection_id', 'check_key', name='uq_qaar_health_safety_check_key'),
    )
    op.create_index(op.f('ix_qaar_health_safety_checks_inspection_id'), 'qaar_health_safety_checks', ['inspection_id'], unique=False)

    op.create_table(
        'qaar_generated_outputs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('inspection_id', sa.Integer(), nullable=False),
        sa.Column('generated_by', sa.Integer(), nullable=True),
        sa.Column('output_type', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=300), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='draft', nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('file_object_id', sa.Integer(), nullable=True),
        sa.Column('source_snapshot', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("output_type IN ('report_summary', 'project_management', 'quality_of_works', 'health_and_safety', 'findings_recommendations', 'aide_memoire', 'notice_of_defects', 'full_package')", name='ck_qaar_generated_output_type'),
        sa.CheckConstraint("status IN ('draft', 'generated', 'superseded', 'approved')", name='ck_qaar_generated_output_status'),
        sa.ForeignKeyConstraint(['file_object_id'], ['stored_objects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['generated_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_qaar_generated_outputs_file_object_id'), 'qaar_generated_outputs', ['file_object_id'], unique=False)
    op.create_index(op.f('ix_qaar_generated_outputs_generated_at'), 'qaar_generated_outputs', ['generated_at'], unique=False)
    op.create_index(op.f('ix_qaar_generated_outputs_generated_by'), 'qaar_generated_outputs', ['generated_by'], unique=False)
    op.create_index(op.f('ix_qaar_generated_outputs_inspection_id'), 'qaar_generated_outputs', ['inspection_id'], unique=False)

    op.create_table(
        'subaybayan_verifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('cycle_month', sa.String(length=7), nullable=False),
        sa.Column('lgu_encoded_status', sa.String(length=40), server_default='not_checked', nullable=False),
        sa.Column('lgu_encoded_at', sa.DateTime(), nullable=True),
        sa.Column('cmlgoo_verified_at', sa.DateTime(), nullable=True),
        sa.Column('po_validated_at', sa.DateTime(), nullable=True),
        sa.Column('ro_action_status', sa.String(length=40), server_default='pending', nullable=False),
        sa.Column('ro_action_at', sa.DateTime(), nullable=True),
        sa.Column('discrepancy_notes', sa.Text(), nullable=True),
        sa.Column('observations', sa.Text(), nullable=True),
        sa.Column('evidence_links', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('status', sa.String(length=30), server_default='open', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("lgu_encoded_status IN ('not_checked', 'not_encoded', 'encoded', 'incomplete', 'returned_for_rectification')", name='ck_subay_lgu_encoded_status'),
        sa.CheckConstraint("ro_action_status IN ('pending', 'approved', 'returned', 'not_required')", name='ck_subay_ro_action_status'),
        sa.CheckConstraint("status IN ('open', 'verified', 'validated', 'returned', 'closed')", name='ck_subay_verification_status'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'cycle_month', name='uq_subaybayan_verification_project_cycle'),
    )
    op.create_index(op.f('ix_subaybayan_verifications_cycle_month'), 'subaybayan_verifications', ['cycle_month'], unique=False)
    op.create_index(op.f('ix_subaybayan_verifications_project_id'), 'subaybayan_verifications', ['project_id'], unique=False)
    op.create_index(op.f('ix_subaybayan_verifications_verified_by'), 'subaybayan_verifications', ['verified_by'], unique=False)

    op.create_table(
        'management_action_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('inspection_id', sa.Integer(), nullable=True),
        sa.Column('verification_id', sa.Integer(), nullable=True),
        sa.Column('prepared_by', sa.Integer(), nullable=True),
        sa.Column('cycle_month', sa.String(length=7), nullable=False),
        sa.Column('risk_level', sa.String(length=20), server_default='minor', nullable=False),
        sa.Column('trigger_source', sa.String(length=40), server_default='manual', nullable=False),
        sa.Column('trigger_summary', sa.Text(), nullable=True),
        sa.Column('action_required', sa.Text(), nullable=True),
        sa.Column('responsible_office', sa.String(length=200), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='draft', nullable=False),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("risk_level IN ('none', 'minor', 'major', 'severe')", name='ck_management_action_risk_level'),
        sa.CheckConstraint("status IN ('draft', 'for_review', 'submitted', 'acted', 'closed')", name='ck_management_action_status'),
        sa.CheckConstraint("trigger_source IN ('manual', 'qaar', 'subaybayan', 'notice', 'monthly_monitoring')", name='ck_management_action_trigger_source'),
        sa.ForeignKeyConstraint(['inspection_id'], ['qaar_inspections.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['prepared_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verification_id'], ['subaybayan_verifications.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_management_action_reports_cycle_month'), 'management_action_reports', ['cycle_month'], unique=False)
    op.create_index(op.f('ix_management_action_reports_inspection_id'), 'management_action_reports', ['inspection_id'], unique=False)
    op.create_index(op.f('ix_management_action_reports_prepared_by'), 'management_action_reports', ['prepared_by'], unique=False)
    op.create_index(op.f('ix_management_action_reports_project_id'), 'management_action_reports', ['project_id'], unique=False)
    op.create_index(op.f('ix_management_action_reports_verification_id'), 'management_action_reports', ['verification_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_management_action_reports_verification_id'), table_name='management_action_reports')
    op.drop_index(op.f('ix_management_action_reports_project_id'), table_name='management_action_reports')
    op.drop_index(op.f('ix_management_action_reports_prepared_by'), table_name='management_action_reports')
    op.drop_index(op.f('ix_management_action_reports_inspection_id'), table_name='management_action_reports')
    op.drop_index(op.f('ix_management_action_reports_cycle_month'), table_name='management_action_reports')
    op.drop_table('management_action_reports')

    op.drop_index(op.f('ix_subaybayan_verifications_verified_by'), table_name='subaybayan_verifications')
    op.drop_index(op.f('ix_subaybayan_verifications_project_id'), table_name='subaybayan_verifications')
    op.drop_index(op.f('ix_subaybayan_verifications_cycle_month'), table_name='subaybayan_verifications')
    op.drop_table('subaybayan_verifications')

    op.drop_index(op.f('ix_qaar_generated_outputs_inspection_id'), table_name='qaar_generated_outputs')
    op.drop_index(op.f('ix_qaar_generated_outputs_generated_by'), table_name='qaar_generated_outputs')
    op.drop_index(op.f('ix_qaar_generated_outputs_generated_at'), table_name='qaar_generated_outputs')
    op.drop_index(op.f('ix_qaar_generated_outputs_file_object_id'), table_name='qaar_generated_outputs')
    op.drop_table('qaar_generated_outputs')

    op.drop_index(op.f('ix_qaar_health_safety_checks_inspection_id'), table_name='qaar_health_safety_checks')
    op.drop_table('qaar_health_safety_checks')

    op.drop_index(op.f('ix_qaar_work_findings_work_item_id'), table_name='qaar_work_findings')
    op.drop_index(op.f('ix_qaar_work_findings_inspection_id'), table_name='qaar_work_findings')
    op.drop_table('qaar_work_findings')

    op.drop_index(op.f('ix_qaar_work_items_inspection_id'), table_name='qaar_work_items')
    op.drop_table('qaar_work_items')

    op.drop_index(op.f('ix_qaar_project_management_checks_inspection_id'), table_name='qaar_project_management_checks')
    op.drop_table('qaar_project_management_checks')

    op.drop_index(op.f('ix_qaar_report_summaries_inspection_id'), table_name='qaar_report_summaries')
    op.drop_table('qaar_report_summaries')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_subaybayan_project_code'))
        batch_op.drop_column('subaybayan_enrollment_status')
        batch_op.drop_column('subaybayan_enrolled_at')
        batch_op.drop_column('nadai_received_at')
        batch_op.drop_column('subaybayan_url')
        batch_op.drop_column('subaybayan_project_code')
        batch_op.drop_column('qaar_category')
        batch_op.drop_column('monitoring_applicability')
        batch_op.drop_column('project_kind')
