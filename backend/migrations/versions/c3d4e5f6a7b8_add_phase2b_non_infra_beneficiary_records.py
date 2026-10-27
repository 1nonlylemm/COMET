"""add phase 2b non-infra monitoring and beneficiary evidence records

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


TEMPLATE_TYPE_VALUES = (
    "'apm_template', 'infrastructure_monitoring_template', "
    "'non_infrastructure_monitoring_template', 'other_monitoring_template'"
)

EVIDENCE_TYPE_VALUES = (
    "'signed_distribution_list', 'acknowledgement_receipt', "
    "'beneficiary_tracking_record', 'turnover_photos', 'delivery_invoice'"
)


def upgrade():
    op.create_table(
        'non_infra_monitoring_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('template_type', sa.String(length=40), nullable=False),
        sa.Column('reporting_period', sa.String(length=7), nullable=True),
        sa.Column('items_verified_summary', sa.Text(), nullable=True),
        sa.Column('specifications_met', sa.Boolean(), nullable=True),
        sa.Column('remarks', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'template_type IN ({TEMPLATE_TYPE_VALUES})',
            name='ck_non_infra_monitoring_template_type',
        ),
        sa.UniqueConstraint('project_requirement_id', name='uq_non_infra_monitoring_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_non_infra_monitoring_records_project_id'), 'non_infra_monitoring_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_non_infra_monitoring_records_project_requirement_id'), 'non_infra_monitoring_records', ['project_requirement_id'], unique=False)
    op.create_index(op.f('ix_non_infra_monitoring_records_reporting_period'), 'non_infra_monitoring_records', ['reporting_period'], unique=False)

    op.create_table(
        'beneficiary_evidence_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('project_requirement_id', sa.Integer(), nullable=False),
        sa.Column('evidence_type', sa.String(length=40), nullable=False),
        sa.Column('beneficiary_count', sa.Integer(), nullable=True),
        sa.Column('distribution_date', sa.Date(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            f'evidence_type IN ({EVIDENCE_TYPE_VALUES})',
            name='ck_beneficiary_evidence_type',
        ),
        sa.CheckConstraint(
            'beneficiary_count IS NULL OR beneficiary_count >= 0',
            name='ck_beneficiary_evidence_count_non_negative',
        ),
        sa.UniqueConstraint('project_requirement_id', name='uq_beneficiary_evidence_project_requirement'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_beneficiary_evidence_records_project_id'), 'beneficiary_evidence_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_beneficiary_evidence_records_project_requirement_id'), 'beneficiary_evidence_records', ['project_requirement_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_beneficiary_evidence_records_project_requirement_id'), table_name='beneficiary_evidence_records')
    op.drop_index(op.f('ix_beneficiary_evidence_records_project_id'), table_name='beneficiary_evidence_records')
    op.drop_table('beneficiary_evidence_records')

    op.drop_index(op.f('ix_non_infra_monitoring_records_reporting_period'), table_name='non_infra_monitoring_records')
    op.drop_index(op.f('ix_non_infra_monitoring_records_project_requirement_id'), table_name='non_infra_monitoring_records')
    op.drop_index(op.f('ix_non_infra_monitoring_records_project_id'), table_name='non_infra_monitoring_records')
    op.drop_table('non_infra_monitoring_records')
