"""add program cycles and workbook imports

Revision ID: e8f4a1b2c3d5
Revises: d2a9c6e8b4f1
Create Date: 2026-04-26 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f4a1b2c3d5'
down_revision = 'd2a9c6e8b4f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'program_cycles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('cloned_from_cycle_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('fiscal_year', sa.Integer(), nullable=False),
        sa.Column('cycle_code', sa.String(length=80), nullable=False),
        sa.Column('source_template_name', sa.String(length=200), nullable=True),
        sa.Column('import_profile', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('field_schema', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cloned_from_cycle_id'], ['program_cycles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_id', 'fiscal_year', 'cycle_code', name='uq_program_cycle_year_code'),
    )
    op.create_index(op.f('ix_program_cycles_cloned_from_cycle_id'), 'program_cycles', ['cloned_from_cycle_id'], unique=False)
    op.create_index(op.f('ix_program_cycles_fiscal_year'), 'program_cycles', ['fiscal_year'], unique=False)
    op.create_index(op.f('ix_program_cycles_program_id'), 'program_cycles', ['program_id'], unique=False)

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('program_cycle_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source_project_code', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('source_row_key', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('source_sheet_name', sa.String(length=255), nullable=True))
        batch_op.create_foreign_key('fk_projects_program_cycle_id', 'program_cycles', ['program_cycle_id'], ['id'], ondelete='SET NULL')
        batch_op.drop_constraint('uq_project_lgu_program_year', type_='unique')
        batch_op.create_unique_constraint('uq_project_cycle_source_code', ['program_cycle_id', 'source_project_code'])
        batch_op.create_index(batch_op.f('ix_projects_program_cycle_id'), ['program_cycle_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_source_project_code'), ['source_project_code'], unique=False)
        batch_op.create_index(batch_op.f('ix_projects_source_row_key'), ['source_row_key'], unique=False)

    op.create_table(
        'import_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('program_cycle_id', sa.Integer(), nullable=True),
        sa.Column('cloned_from_template_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('file_type', sa.String(length=20), nullable=False),
        sa.Column('version_number', sa.Integer(), server_default='1', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='draft', nullable=False),
        sa.Column('schema_signature', sa.String(length=128), nullable=True),
        sa.Column('sheet_mappings', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('column_mappings', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('transform_rules', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('locked_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("file_type IN ('csv', 'xlsx', 'xls')", name='ck_import_template_file_type'),
        sa.CheckConstraint("status IN ('draft', 'active', 'superseded', 'archived')", name='ck_import_template_status'),
        sa.ForeignKeyConstraint(['cloned_from_template_id'], ['import_templates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_cycle_id'], ['program_cycles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_import_templates_cloned_from_template_id'), 'import_templates', ['cloned_from_template_id'], unique=False)
    op.create_index(op.f('ix_import_templates_program_cycle_id'), 'import_templates', ['program_cycle_id'], unique=False)
    op.create_index(op.f('ix_import_templates_program_id'), 'import_templates', ['program_id'], unique=False)
    op.create_index(op.f('ix_import_templates_schema_signature'), 'import_templates', ['schema_signature'], unique=False)

    op.create_table(
        'import_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('program_cycle_id', sa.Integer(), nullable=True),
        sa.Column('import_template_id', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('original_file_name', sa.String(length=255), nullable=False),
        sa.Column('stored_file_path', sa.String(length=500), nullable=False),
        sa.Column('file_hash', sa.String(length=128), nullable=False),
        sa.Column('file_type', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='profiled', nullable=False),
        sa.Column('workbook_profile', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('mapping_preview', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('preview_summary', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('committed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("file_type IN ('csv', 'xlsx', 'xls')", name='ck_import_batch_file_type'),
        sa.CheckConstraint("status IN ('uploaded', 'profiled', 'mapped', 'previewed', 'committed', 'failed', 'cancelled')", name='ck_import_batch_status'),
        sa.ForeignKeyConstraint(['import_template_id'], ['import_templates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_cycle_id'], ['program_cycles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_import_batches_file_hash'), 'import_batches', ['file_hash'], unique=False)
    op.create_index(op.f('ix_import_batches_import_template_id'), 'import_batches', ['import_template_id'], unique=False)
    op.create_index(op.f('ix_import_batches_program_cycle_id'), 'import_batches', ['program_cycle_id'], unique=False)
    op.create_index(op.f('ix_import_batches_program_id'), 'import_batches', ['program_id'], unique=False)

    op.create_table(
        'import_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=False),
        sa.Column('sheet_name', sa.String(length=255), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('row_key', sa.String(length=255), nullable=True),
        sa.Column('raw_data', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('mapped_data', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('validation_errors', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('action', sa.String(length=30), nullable=True),
        sa.Column('committed_entity_type', sa.String(length=50), nullable=True),
        sa.Column('committed_entity_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("action IS NULL OR action IN ('create_project', 'update_project', 'skip', 'error')", name='ck_import_row_action'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('import_batch_id', 'sheet_name', 'row_number', name='uq_import_row_batch_sheet_row'),
    )
    op.create_index(op.f('ix_import_rows_import_batch_id'), 'import_rows', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_import_rows_row_key'), 'import_rows', ['row_key'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_import_rows_row_key'), table_name='import_rows')
    op.drop_index(op.f('ix_import_rows_import_batch_id'), table_name='import_rows')
    op.drop_table('import_rows')

    op.drop_index(op.f('ix_import_batches_program_id'), table_name='import_batches')
    op.drop_index(op.f('ix_import_batches_program_cycle_id'), table_name='import_batches')
    op.drop_index(op.f('ix_import_batches_import_template_id'), table_name='import_batches')
    op.drop_index(op.f('ix_import_batches_file_hash'), table_name='import_batches')
    op.drop_table('import_batches')

    op.drop_index(op.f('ix_import_templates_schema_signature'), table_name='import_templates')
    op.drop_index(op.f('ix_import_templates_program_id'), table_name='import_templates')
    op.drop_index(op.f('ix_import_templates_program_cycle_id'), table_name='import_templates')
    op.drop_index(op.f('ix_import_templates_cloned_from_template_id'), table_name='import_templates')
    op.drop_table('import_templates')

    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_source_row_key'))
        batch_op.drop_index(batch_op.f('ix_projects_source_project_code'))
        batch_op.drop_index(batch_op.f('ix_projects_program_cycle_id'))
        batch_op.drop_constraint('uq_project_cycle_source_code', type_='unique')
        batch_op.drop_constraint('fk_projects_program_cycle_id', type_='foreignkey')
        batch_op.create_unique_constraint('uq_project_lgu_program_year', ['lgu_id', 'program_id', 'fiscal_year'])
        batch_op.drop_column('source_sheet_name')
        batch_op.drop_column('source_row_key')
        batch_op.drop_column('source_project_code')
        batch_op.drop_column('program_cycle_id')

    op.drop_index(op.f('ix_program_cycles_program_id'), table_name='program_cycles')
    op.drop_index(op.f('ix_program_cycles_fiscal_year'), table_name='program_cycles')
    op.drop_index(op.f('ix_program_cycles_cloned_from_cycle_id'), table_name='program_cycles')
    op.drop_table('program_cycles')
