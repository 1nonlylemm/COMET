"""add document compliance checker

Revision ID: 1c3d5e7f9a2b
Revises: 0f4b8c2d6e10
Create Date: 2026-05-19 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '1c3d5e7f9a2b'
down_revision = '0f4b8c2d6e10'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_reference_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_uri', sa.String(length=700), nullable=False),
        sa.Column('reference_origin', sa.String(length=30), nullable=False),
        sa.Column('reference_type', sa.String(length=50), nullable=False),
        sa.Column('checker_reference_type', sa.String(length=50), server_default='guideline_basis', nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=True),
        sa.Column('program_cycle_id', sa.Integer(), nullable=True),
        sa.Column('requirement_id', sa.Integer(), nullable=True),
        sa.Column('requirement_name', sa.String(length=300), nullable=True),
        sa.Column('requirement_type', sa.String(length=50), nullable=True),
        sa.Column('phase_name', sa.String(length=100), nullable=True),
        sa.Column('fiscal_year', sa.Integer(), nullable=True),
        sa.Column('project_kind', sa.String(length=50), nullable=True),
        sa.Column('status', sa.String(length=30), server_default='draft', nullable=False),
        sa.Column('effective_from', sa.Date(), nullable=True),
        sa.Column('effective_to', sa.Date(), nullable=True),
        sa.Column('profile_metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('fiscal_year IS NULL OR (fiscal_year BETWEEN 2000 AND 2100)', name='ck_doc_ref_profile_fy_range'),
        sa.CheckConstraint(
            "checker_reference_type IN ("
            "'official_template', 'accepted_sample', 'returned_sample', "
            "'guideline_basis', 'logo_letterhead_reference', 'validation_checklist'"
            ")",
            name='ck_doc_ref_profile_checker_type',
        ),
        sa.CheckConstraint("reference_origin IN ('guideline', 'template')", name='ck_doc_ref_profile_origin'),
        sa.CheckConstraint("status IN ('draft', 'active', 'superseded', 'archived')", name='ck_doc_ref_profile_status'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_cycle_id'], ['program_cycles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('reference_uri', name='uq_doc_ref_profile_reference_uri'),
    )
    op.create_index(op.f('ix_document_reference_profiles_reference_uri'), 'document_reference_profiles', ['reference_uri'], unique=False)
    op.create_index(op.f('ix_document_reference_profiles_program_id'), 'document_reference_profiles', ['program_id'], unique=False)
    op.create_index(op.f('ix_document_reference_profiles_program_cycle_id'), 'document_reference_profiles', ['program_cycle_id'], unique=False)
    op.create_index(op.f('ix_document_reference_profiles_requirement_id'), 'document_reference_profiles', ['requirement_id'], unique=False)
    op.create_index(op.f('ix_document_reference_profiles_requirement_name'), 'document_reference_profiles', ['requirement_name'], unique=False)
    op.create_index(op.f('ix_document_reference_profiles_fiscal_year'), 'document_reference_profiles', ['fiscal_year'], unique=False)
    op.create_index(
        'idx_doc_ref_profile_lookup',
        'document_reference_profiles',
        ['program_id', 'requirement_id', 'fiscal_year', 'status'],
        unique=False,
    )

    op.create_table(
        'document_compliance_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=False),
        sa.Column('document_file_id', sa.Integer(), nullable=True),
        sa.Column('project_requirement_id', sa.Integer(), nullable=True),
        sa.Column('score', sa.Numeric(precision=5, scale=2), server_default='0', nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('recommended_action', sa.String(length=40), nullable=False),
        sa.Column('reference_basis', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('findings', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('extracted_fields', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('suggested_return_notes', sa.Text(), nullable=True),
        sa.Column('checker_version', sa.String(length=40), server_default='document_compliance_v1', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "recommended_action IN ('approve_ready', 'review_required', 'return_for_revision', 'manual_review')",
            name='ck_doc_compliance_recommended_action',
        ),
        sa.CheckConstraint('score >= 0 AND score <= 100', name='ck_doc_compliance_score_range'),
        sa.CheckConstraint(
            "status IN ('ready_for_approval', 'review_required', 'likely_return', 'invalid_evidence', 'check_failed')",
            name='ck_doc_compliance_status',
        ),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['document_file_id'], ['document_files.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_document_compliance_results_created_at'), 'document_compliance_results', ['created_at'], unique=False)
    op.create_index(op.f('ix_document_compliance_results_document_file_id'), 'document_compliance_results', ['document_file_id'], unique=False)
    op.create_index(op.f('ix_document_compliance_results_project_requirement_id'), 'document_compliance_results', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_document_compliance_results_submission_id'), 'document_compliance_results', ['submission_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_document_compliance_results_submission_id'), table_name='document_compliance_results')
    op.drop_index(op.f('ix_document_compliance_results_project_requirement_id'), table_name='document_compliance_results')
    op.drop_index(op.f('ix_document_compliance_results_document_file_id'), table_name='document_compliance_results')
    op.drop_index(op.f('ix_document_compliance_results_created_at'), table_name='document_compliance_results')
    op.drop_table('document_compliance_results')

    op.drop_index('idx_doc_ref_profile_lookup', table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_fiscal_year'), table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_requirement_name'), table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_requirement_id'), table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_program_cycle_id'), table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_program_id'), table_name='document_reference_profiles')
    op.drop_index(op.f('ix_document_reference_profiles_reference_uri'), table_name='document_reference_profiles')
    op.drop_table('document_reference_profiles')
