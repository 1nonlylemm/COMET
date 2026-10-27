"""add document checker evaluation tables

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-06-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f8a9b0c1d2e3'
down_revision = 'e7f8a9b0c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_checker_evaluation_datasets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('dataset_type', sa.String(length=40), server_default='synthetic', nullable=False),
        sa.Column('version', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=40), server_default='draft', nullable=False),
        sa.Column('metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "dataset_type IN ('synthetic', 'demo', 'redacted_real', 'reviewer_adjudicated', 'holdout')",
            name='ck_document_checker_dataset_type',
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'locked', 'archived')",
            name='ck_document_checker_dataset_status',
        ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', 'version', name='uq_document_checker_dataset_name_version'),
    )
    op.create_index('ix_document_checker_evaluation_datasets_created_at', 'document_checker_evaluation_datasets', ['created_at'])
    op.create_index('ix_document_checker_evaluation_datasets_created_by', 'document_checker_evaluation_datasets', ['created_by'])

    op.create_table(
        'document_checker_evaluation_cases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('document_file_id', sa.Integer(), nullable=True),
        sa.Column('case_key', sa.String(length=160), nullable=False),
        sa.Column('document_family', sa.String(length=80), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=True),
        sa.Column('program_id', sa.Integer(), nullable=True),
        sa.Column('fiscal_year', sa.Integer(), nullable=True),
        sa.Column('ground_truth', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('pii_redacted', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('label_source', sa.String(length=80), nullable=True),
        sa.Column('label_confidence', sa.String(length=20), nullable=True),
        sa.Column('metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "label_confidence IS NULL OR label_confidence IN ('low', 'medium', 'high')",
            name='ck_document_checker_case_label_confidence',
        ),
        sa.CheckConstraint(
            'fiscal_year IS NULL OR (fiscal_year BETWEEN 2000 AND 2100)',
            name='ck_document_checker_case_fy_range',
        ),
        sa.ForeignKeyConstraint(['dataset_id'], ['document_checker_evaluation_datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_file_id'], ['document_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('dataset_id', 'case_key', name='uq_document_checker_case_dataset_key'),
    )
    op.create_index('ix_document_checker_evaluation_cases_created_at', 'document_checker_evaluation_cases', ['created_at'])
    op.create_index('ix_document_checker_evaluation_cases_dataset_id', 'document_checker_evaluation_cases', ['dataset_id'])
    op.create_index('ix_document_checker_evaluation_cases_document_family', 'document_checker_evaluation_cases', ['document_family'])
    op.create_index('ix_document_checker_evaluation_cases_document_file_id', 'document_checker_evaluation_cases', ['document_file_id'])
    op.create_index('ix_document_checker_evaluation_cases_fiscal_year', 'document_checker_evaluation_cases', ['fiscal_year'])
    op.create_index('ix_document_checker_evaluation_cases_program_id', 'document_checker_evaluation_cases', ['program_id'])
    op.create_index('ix_document_checker_evaluation_cases_requirement_id', 'document_checker_evaluation_cases', ['requirement_id'])

    op.create_table(
        'document_checker_evaluation_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('run_name', sa.String(length=180), nullable=False),
        sa.Column('status', sa.String(length=40), server_default='queued', nullable=False),
        sa.Column('checker_version', sa.String(length=80), nullable=True),
        sa.Column('rule_policy_version', sa.String(length=80), nullable=True),
        sa.Column('provider_config', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('reference_profile_snapshot', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('started_by', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('summary_metrics', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'completed_with_failures', 'failed', 'cancelled')",
            name='ck_document_checker_run_status',
        ),
        sa.ForeignKeyConstraint(['dataset_id'], ['document_checker_evaluation_datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['started_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_checker_evaluation_runs_created_at', 'document_checker_evaluation_runs', ['created_at'])
    op.create_index('ix_document_checker_evaluation_runs_dataset_id', 'document_checker_evaluation_runs', ['dataset_id'])
    op.create_index('ix_document_checker_evaluation_runs_started_at', 'document_checker_evaluation_runs', ['started_at'])
    op.create_index('ix_document_checker_evaluation_runs_started_by', 'document_checker_evaluation_runs', ['started_by'])
    op.create_index('ix_document_checker_evaluation_runs_status', 'document_checker_evaluation_runs', ['status'])

    op.create_table(
        'document_checker_evaluation_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('case_id', sa.Integer(), nullable=False),
        sa.Column('checker_result_id', sa.Integer(), nullable=True),
        sa.Column('expected_output', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('predicted_output', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('metric_breakdown', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('passed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('failure_reasons', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['case_id'], ['document_checker_evaluation_cases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['checker_result_id'], ['document_compliance_results.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['document_checker_evaluation_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'case_id', name='uq_document_checker_result_run_case'),
    )
    op.create_index('ix_document_checker_evaluation_results_case_id', 'document_checker_evaluation_results', ['case_id'])
    op.create_index('ix_document_checker_evaluation_results_checker_result_id', 'document_checker_evaluation_results', ['checker_result_id'])
    op.create_index('ix_document_checker_evaluation_results_created_at', 'document_checker_evaluation_results', ['created_at'])
    op.create_index('ix_document_checker_evaluation_results_passed', 'document_checker_evaluation_results', ['passed'])
    op.create_index('ix_document_checker_evaluation_results_run_id', 'document_checker_evaluation_results', ['run_id'])

    op.create_table(
        'document_checker_metric_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('dataset_id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('snapshot_type', sa.String(length=60), server_default='latest_run', nullable=False),
        sa.Column('metrics', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('gates', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "snapshot_type IN ('latest_run', 'official_gate', 'trend_point', 'manual_baseline')",
            name='ck_document_checker_snapshot_type',
        ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dataset_id'], ['document_checker_evaluation_datasets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['run_id'], ['document_checker_evaluation_runs.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_checker_metric_snapshots_created_at', 'document_checker_metric_snapshots', ['created_at'])
    op.create_index('ix_document_checker_metric_snapshots_created_by', 'document_checker_metric_snapshots', ['created_by'])
    op.create_index('ix_document_checker_metric_snapshots_dataset_id', 'document_checker_metric_snapshots', ['dataset_id'])
    op.create_index('ix_document_checker_metric_snapshots_run_id', 'document_checker_metric_snapshots', ['run_id'])


def downgrade():
    op.drop_index('ix_document_checker_metric_snapshots_run_id', table_name='document_checker_metric_snapshots')
    op.drop_index('ix_document_checker_metric_snapshots_dataset_id', table_name='document_checker_metric_snapshots')
    op.drop_index('ix_document_checker_metric_snapshots_created_by', table_name='document_checker_metric_snapshots')
    op.drop_index('ix_document_checker_metric_snapshots_created_at', table_name='document_checker_metric_snapshots')
    op.drop_table('document_checker_metric_snapshots')

    op.drop_index('ix_document_checker_evaluation_results_run_id', table_name='document_checker_evaluation_results')
    op.drop_index('ix_document_checker_evaluation_results_passed', table_name='document_checker_evaluation_results')
    op.drop_index('ix_document_checker_evaluation_results_created_at', table_name='document_checker_evaluation_results')
    op.drop_index('ix_document_checker_evaluation_results_checker_result_id', table_name='document_checker_evaluation_results')
    op.drop_index('ix_document_checker_evaluation_results_case_id', table_name='document_checker_evaluation_results')
    op.drop_table('document_checker_evaluation_results')

    op.drop_index('ix_document_checker_evaluation_runs_status', table_name='document_checker_evaluation_runs')
    op.drop_index('ix_document_checker_evaluation_runs_started_by', table_name='document_checker_evaluation_runs')
    op.drop_index('ix_document_checker_evaluation_runs_started_at', table_name='document_checker_evaluation_runs')
    op.drop_index('ix_document_checker_evaluation_runs_dataset_id', table_name='document_checker_evaluation_runs')
    op.drop_index('ix_document_checker_evaluation_runs_created_at', table_name='document_checker_evaluation_runs')
    op.drop_table('document_checker_evaluation_runs')

    op.drop_index('ix_document_checker_evaluation_cases_requirement_id', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_program_id', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_fiscal_year', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_document_file_id', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_document_family', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_dataset_id', table_name='document_checker_evaluation_cases')
    op.drop_index('ix_document_checker_evaluation_cases_created_at', table_name='document_checker_evaluation_cases')
    op.drop_table('document_checker_evaluation_cases')

    op.drop_index('ix_document_checker_evaluation_datasets_created_by', table_name='document_checker_evaluation_datasets')
    op.drop_index('ix_document_checker_evaluation_datasets_created_at', table_name='document_checker_evaluation_datasets')
    op.drop_table('document_checker_evaluation_datasets')
