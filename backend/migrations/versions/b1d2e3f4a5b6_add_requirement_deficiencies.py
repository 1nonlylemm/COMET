"""add requirement_deficiencies table for documentary review workflow

Revision ID: b1d2e3f4a5b6
Revises: a7c8e9f1d2b3
Create Date: 2026-09-05 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1d2e3f4a5b6'
down_revision = 'a7c8e9f1d2b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'requirement_deficiencies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('submission_id', sa.Integer(), nullable=True),
        sa.Column('submission_version_id', sa.Integer(), nullable=True),
        sa.Column('resolved_submission_version_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('finding_observation', sa.Text(), nullable=False),
        sa.Column('corrective_instruction', sa.Text(), nullable=False),
        sa.Column('resolution_state', sa.String(length=20), server_default='open', nullable=False),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_by_user_id', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_submission_version_id'], ['submission_versions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submission_id'], ['submissions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['submission_version_id'], ['submission_versions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "category IN ("
            "'missing_attachment', 'missing_signature_notarization', "
            "'cross_document_inconsistency', 'costing_dupa_defect', "
            "'missing_statutory_clearance', 'program_specific_non_conformity', "
            "'financial_reconciliation_defect', 'scan_quality_defect', "
            "'other_documented_defect'"
            ")",
            name='ck_deficiency_category',
        ),
        sa.CheckConstraint(
            "resolution_state IN ('open', 'resolved', 'waived')",
            name='ck_deficiency_resolution_state',
        ),
    )
    op.create_index('idx_deficiencies_requirement', 'requirement_deficiencies', ['project_requirement_id'], unique=False)
    op.create_index('idx_deficiencies_submission', 'requirement_deficiencies', ['submission_id'], unique=False)
    op.create_index('idx_deficiencies_version', 'requirement_deficiencies', ['submission_version_id'], unique=False)
    op.create_index('idx_deficiencies_state', 'requirement_deficiencies', ['project_requirement_id', 'resolution_state'], unique=False)


def downgrade():
    op.drop_index('idx_deficiencies_state', table_name='requirement_deficiencies')
    op.drop_index('idx_deficiencies_version', table_name='requirement_deficiencies')
    op.drop_index('idx_deficiencies_submission', table_name='requirement_deficiencies')
    op.drop_index('idx_deficiencies_requirement', table_name='requirement_deficiencies')
    op.drop_table('requirement_deficiencies')
