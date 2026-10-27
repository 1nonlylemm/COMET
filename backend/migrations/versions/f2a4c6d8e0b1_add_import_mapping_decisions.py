"""add import mapping decisions

Revision ID: f2a4c6d8e0b1
Revises: d4e5f6a7b8c9
Create Date: 2026-04-30 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f2a4c6d8e0b1'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'import_mapping_decisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('program_cycle_id', sa.Integer(), nullable=True),
        sa.Column('import_template_id', sa.Integer(), nullable=True),
        sa.Column('created_from_batch_id', sa.Integer(), nullable=True),
        sa.Column('source_sheet_name', sa.String(length=255), nullable=False),
        sa.Column('source_column', sa.String(length=10), nullable=False),
        sa.Column('source_header', sa.String(length=500), nullable=True),
        sa.Column('normalized_source_header', sa.String(length=500), nullable=True),
        sa.Column('column_fingerprint', sa.String(length=160), nullable=False),
        sa.Column('classification', sa.String(length=40), server_default='context', nullable=False),
        sa.Column('canonical_label', sa.String(length=500), nullable=True),
        sa.Column('target_field', sa.String(length=255), nullable=True),
        sa.Column('suggested_role', sa.String(length=80), nullable=True),
        sa.Column('binding_target', sa.String(length=255), nullable=True),
        sa.Column('binding_config', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('requirement_metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('value_mapping_rules', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('trust_level', sa.String(length=30), server_default='confirmed', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('version_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('confirmed_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "classification IN ('project_field', 'lgu_field', 'cycle_field', 'requirement', 'context', 'ignored', 'calculated')",
            name='ck_import_mapping_decision_classification',
        ),
        sa.CheckConstraint(
            "trust_level IN ('suggested', 'confirmed')",
            name='ck_import_mapping_decision_trust_level',
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded', 'archived')",
            name='ck_import_mapping_decision_status',
        ),
        sa.ForeignKeyConstraint(['confirmed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_from_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['import_template_id'], ['import_templates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_cycle_id'], ['program_cycles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_import_mapping_decisions_column_fingerprint'), 'import_mapping_decisions', ['column_fingerprint'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_confirmed_by'), 'import_mapping_decisions', ['confirmed_by'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_created_from_batch_id'), 'import_mapping_decisions', ['created_from_batch_id'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_import_template_id'), 'import_mapping_decisions', ['import_template_id'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_normalized_source_header'), 'import_mapping_decisions', ['normalized_source_header'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_program_cycle_id'), 'import_mapping_decisions', ['program_cycle_id'], unique=False)
    op.create_index(op.f('ix_import_mapping_decisions_program_id'), 'import_mapping_decisions', ['program_id'], unique=False)

    with op.batch_alter_table('requirements', schema=None) as batch_op:
        batch_op.add_column(sa.Column('program_cycle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_from_mapping_decision_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source_label', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('source_sheet_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('source_column', sa.String(length=10), nullable=True))
        batch_op.create_foreign_key('fk_requirements_program_cycle_id', 'program_cycles', ['program_cycle_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_requirements_mapping_decision_id', 'import_mapping_decisions', ['created_from_mapping_decision_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index(batch_op.f('ix_requirements_program_cycle_id'), ['program_cycle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_requirements_created_from_mapping_decision_id'), ['created_from_mapping_decision_id'], unique=False)

    with op.batch_alter_table('workbook_columns', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_header', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('canonical_label', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('classification', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('mapping_decision_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_workbook_columns_mapping_decision_id', 'import_mapping_decisions', ['mapping_decision_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index(batch_op.f('ix_workbook_columns_classification'), ['classification'], unique=False)
        batch_op.create_index(batch_op.f('ix_workbook_columns_mapping_decision_id'), ['mapping_decision_id'], unique=False)


def downgrade():
    with op.batch_alter_table('workbook_columns', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_workbook_columns_mapping_decision_id'))
        batch_op.drop_index(batch_op.f('ix_workbook_columns_classification'))
        batch_op.drop_constraint('fk_workbook_columns_mapping_decision_id', type_='foreignkey')
        batch_op.drop_column('mapping_decision_id')
        batch_op.drop_column('classification')
        batch_op.drop_column('canonical_label')
        batch_op.drop_column('source_header')

    with op.batch_alter_table('requirements', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_requirements_created_from_mapping_decision_id'))
        batch_op.drop_index(batch_op.f('ix_requirements_program_cycle_id'))
        batch_op.drop_constraint('fk_requirements_mapping_decision_id', type_='foreignkey')
        batch_op.drop_constraint('fk_requirements_program_cycle_id', type_='foreignkey')
        batch_op.drop_column('source_column')
        batch_op.drop_column('source_sheet_name')
        batch_op.drop_column('source_label')
        batch_op.drop_column('created_from_mapping_decision_id')
        batch_op.drop_column('program_cycle_id')

    op.drop_index(op.f('ix_import_mapping_decisions_program_id'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_program_cycle_id'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_normalized_source_header'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_import_template_id'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_created_from_batch_id'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_confirmed_by'), table_name='import_mapping_decisions')
    op.drop_index(op.f('ix_import_mapping_decisions_column_fingerprint'), table_name='import_mapping_decisions')
    op.drop_table('import_mapping_decisions')
