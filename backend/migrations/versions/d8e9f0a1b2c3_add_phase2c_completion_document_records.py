"""add phase 2c completion document records

Revision ID: d8e9f0a1b2c3
Revises: c3d4e5f6a7b8
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd8e9f0a1b2c3'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


DOCUMENT_TYPE_VALUES = (
    "'final_swa', 'final_inspection_report', 'certificate_of_final_acceptance', "
    "'final_sord', 'proof_of_return_of_funds'"
)

APPLICABILITY_VALUES = "'required', 'pending_confirmation', 'not_applicable'"


def upgrade():
    op.create_table(
        'completion_document_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('document_type', sa.String(length=60), nullable=False),
        sa.Column('applicability', sa.String(length=30), nullable=False, server_default='required'),
        sa.Column('applicability_reason', sa.Text(), nullable=True),
        sa.Column('applicability_set_by', sa.Integer(), nullable=True),
        sa.Column('applicability_set_at', sa.DateTime(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'document_type IN ({DOCUMENT_TYPE_VALUES})',
            name='ck_completion_document_type',
        ),
        sa.CheckConstraint(
            f'applicability IN ({APPLICABILITY_VALUES})',
            name='ck_completion_document_applicability',
        ),
        sa.UniqueConstraint('project_id', 'document_type', name='uq_completion_document_project_type'),
        sa.UniqueConstraint('project_requirement_id', name='uq_completion_document_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['applicability_set_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_completion_document_records_project_id'), 'completion_document_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_completion_document_records_project_requirement_id'), 'completion_document_records', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_completion_document_records_document_type'), 'completion_document_records', ['document_type'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_completion_document_records_document_type'), table_name='completion_document_records')
    op.drop_index(op.f('ix_completion_document_records_project_requirement_id'), table_name='completion_document_records')
    op.drop_index(op.f('ix_completion_document_records_project_id'), table_name='completion_document_records')
    op.drop_table('completion_document_records')
