"""add workbook workspaces

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-27 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workbook_workspaces',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('program_id', sa.Integer(), nullable=False),
        sa.Column('program_cycle_id', sa.Integer(), nullable=False),
        sa.Column('source_import_batch_id', sa.Integer(), nullable=True),
        sa.Column('active_import_template_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('schema_signature', sa.String(length=128), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('draft', 'active', 'archived')", name='ck_workbook_workspace_status'),
        sa.ForeignKeyConstraint(['active_import_template_id'], ['import_templates.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['program_cycle_id'], ['program_cycles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['program_id'], ['programs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_import_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('program_cycle_id', 'name', name='uq_workbook_workspace_cycle_name'),
    )
    op.create_index(op.f('ix_workbook_workspaces_active_import_template_id'), 'workbook_workspaces', ['active_import_template_id'], unique=False)
    op.create_index(op.f('ix_workbook_workspaces_program_cycle_id'), 'workbook_workspaces', ['program_cycle_id'], unique=False)
    op.create_index(op.f('ix_workbook_workspaces_program_id'), 'workbook_workspaces', ['program_id'], unique=False)
    op.create_index(op.f('ix_workbook_workspaces_schema_signature'), 'workbook_workspaces', ['schema_signature'], unique=False)
    op.create_index(op.f('ix_workbook_workspaces_source_import_batch_id'), 'workbook_workspaces', ['source_import_batch_id'], unique=False)

    op.create_table(
        'workbook_sheets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('source_sheet_name', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=False),
        sa.Column('sheet_type', sa.String(length=80), nullable=True),
        sa.Column('sheet_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_row', sa.Integer(), nullable=True),
        sa.Column('max_column', sa.Integer(), nullable=True),
        sa.Column('merged_ranges', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('is_visible', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workbook_workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'source_sheet_name', name='uq_workbook_sheet_workspace_source'),
    )
    op.create_index(op.f('ix_workbook_sheets_sheet_type'), 'workbook_sheets', ['sheet_type'], unique=False)
    op.create_index(op.f('ix_workbook_sheets_workspace_id'), 'workbook_sheets', ['workspace_id'], unique=False)

    op.create_table(
        'workbook_columns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sheet_id', sa.Integer(), nullable=False),
        sa.Column('source_column', sa.String(length=10), nullable=False),
        sa.Column('column_index', sa.Integer(), nullable=False),
        sa.Column('header_path', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('display_label', sa.String(length=500), nullable=True),
        sa.Column('normalized_header', sa.String(length=500), nullable=True),
        sa.Column('data_type', sa.String(length=40), server_default='text', nullable=False),
        sa.Column('number_format', sa.String(length=120), nullable=True),
        sa.Column('validation_rules', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('validation_options', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('binding_target', sa.String(length=255), server_default='import_only', nullable=False),
        sa.Column('binding_config', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('is_editable', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_required', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_formula', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('formula_policy', sa.String(length=40), server_default='manual', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sheet_id'], ['workbook_sheets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sheet_id', 'source_column', name='uq_workbook_column_sheet_source'),
    )
    op.create_index(op.f('ix_workbook_columns_normalized_header'), 'workbook_columns', ['normalized_header'], unique=False)
    op.create_index(op.f('ix_workbook_columns_sheet_id'), 'workbook_columns', ['sheet_id'], unique=False)

    op.create_table(
        'workbook_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sheet_id', sa.Integer(), nullable=False),
        sa.Column('source_row_number', sa.Integer(), nullable=False),
        sa.Column('source_row_key', sa.String(length=255), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('lgu_id', sa.Integer(), nullable=True),
        sa.Column('row_state', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('last_import_batch_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("row_state IN ('active', 'skipped', 'conflict', 'archived')", name='ck_workbook_row_state'),
        sa.ForeignKeyConstraint(['last_import_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lgu_id'], ['lgu_profiles.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sheet_id'], ['workbook_sheets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sheet_id', 'source_row_number', name='uq_workbook_row_sheet_source_row'),
    )
    op.create_index(op.f('ix_workbook_rows_last_import_batch_id'), 'workbook_rows', ['last_import_batch_id'], unique=False)
    op.create_index(op.f('ix_workbook_rows_lgu_id'), 'workbook_rows', ['lgu_id'], unique=False)
    op.create_index(op.f('ix_workbook_rows_project_id'), 'workbook_rows', ['project_id'], unique=False)
    op.create_index(op.f('ix_workbook_rows_sheet_id'), 'workbook_rows', ['sheet_id'], unique=False)
    op.create_index(op.f('ix_workbook_rows_source_row_key'), 'workbook_rows', ['source_row_key'], unique=False)

    op.create_table(
        'workbook_cells',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('row_id', sa.Integer(), nullable=False),
        sa.Column('column_id', sa.Integer(), nullable=False),
        sa.Column('cell_ref', sa.String(length=20), nullable=False),
        sa.Column('raw_value', sa.JSON(), nullable=True),
        sa.Column('typed_value', sa.JSON(), nullable=True),
        sa.Column('display_value', sa.String(length=1000), nullable=True),
        sa.Column('formula', sa.Text(), nullable=True),
        sa.Column('cached_formula_value', sa.JSON(), nullable=True),
        sa.Column('source_value', sa.JSON(), nullable=True),
        sa.Column('current_value', sa.JSON(), nullable=True),
        sa.Column('value_type', sa.String(length=40), server_default='text', nullable=False),
        sa.Column('validation_state', sa.String(length=30), server_default='valid', nullable=False),
        sa.Column('validation_messages', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('is_dirty', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('last_edited_by', sa.Integer(), nullable=True),
        sa.Column('last_edited_at', sa.DateTime(), nullable=True),
        sa.Column('last_import_batch_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("validation_state IN ('valid', 'warning', 'error')", name='ck_workbook_cell_validation_state'),
        sa.ForeignKeyConstraint(['column_id'], ['workbook_columns.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['last_edited_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['last_import_batch_id'], ['import_batches.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['row_id'], ['workbook_rows.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('row_id', 'column_id', name='uq_workbook_cell_row_column'),
    )
    op.create_index(op.f('ix_workbook_cells_cell_ref'), 'workbook_cells', ['cell_ref'], unique=False)
    op.create_index(op.f('ix_workbook_cells_column_id'), 'workbook_cells', ['column_id'], unique=False)
    op.create_index(op.f('ix_workbook_cells_last_import_batch_id'), 'workbook_cells', ['last_import_batch_id'], unique=False)
    op.create_index(op.f('ix_workbook_cells_row_id'), 'workbook_cells', ['row_id'], unique=False)

    op.create_table(
        'workbook_cell_changes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cell_id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('binding_target', sa.String(length=255), nullable=True),
        sa.Column('old_value', sa.JSON(), nullable=True),
        sa.Column('new_value', sa.JSON(), nullable=True),
        sa.Column('change_source', sa.String(length=50), nullable=False),
        sa.Column('changed_by', sa.Integer(), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('audit_log_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['audit_log_id'], ['audit_logs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['cell_id'], ['workbook_cells.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workbook_workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workbook_cell_changes_audit_log_id'), 'workbook_cell_changes', ['audit_log_id'], unique=False)
    op.create_index(op.f('ix_workbook_cell_changes_cell_id'), 'workbook_cell_changes', ['cell_id'], unique=False)
    op.create_index(op.f('ix_workbook_cell_changes_changed_at'), 'workbook_cell_changes', ['changed_at'], unique=False)
    op.create_index(op.f('ix_workbook_cell_changes_changed_by'), 'workbook_cell_changes', ['changed_by'], unique=False)
    op.create_index(op.f('ix_workbook_cell_changes_project_id'), 'workbook_cell_changes', ['project_id'], unique=False)
    op.create_index(op.f('ix_workbook_cell_changes_workspace_id'), 'workbook_cell_changes', ['workspace_id'], unique=False)

    op.create_table(
        'workbook_conflicts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('cell_id', sa.Integer(), nullable=False),
        sa.Column('import_batch_id', sa.Integer(), nullable=False),
        sa.Column('source_value', sa.JSON(), nullable=True),
        sa.Column('current_value', sa.JSON(), nullable=True),
        sa.Column('conflict_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='open', nullable=False),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('open', 'keep_comet', 'accept_import', 'resolved', 'ignored')", name='ck_workbook_conflict_status'),
        sa.ForeignKeyConstraint(['cell_id'], ['workbook_cells.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['import_batch_id'], ['import_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workbook_workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workbook_conflicts_cell_id'), 'workbook_conflicts', ['cell_id'], unique=False)
    op.create_index(op.f('ix_workbook_conflicts_import_batch_id'), 'workbook_conflicts', ['import_batch_id'], unique=False)
    op.create_index(op.f('ix_workbook_conflicts_workspace_id'), 'workbook_conflicts', ['workspace_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_workbook_conflicts_workspace_id'), table_name='workbook_conflicts')
    op.drop_index(op.f('ix_workbook_conflicts_import_batch_id'), table_name='workbook_conflicts')
    op.drop_index(op.f('ix_workbook_conflicts_cell_id'), table_name='workbook_conflicts')
    op.drop_table('workbook_conflicts')

    op.drop_index(op.f('ix_workbook_cell_changes_workspace_id'), table_name='workbook_cell_changes')
    op.drop_index(op.f('ix_workbook_cell_changes_project_id'), table_name='workbook_cell_changes')
    op.drop_index(op.f('ix_workbook_cell_changes_changed_by'), table_name='workbook_cell_changes')
    op.drop_index(op.f('ix_workbook_cell_changes_changed_at'), table_name='workbook_cell_changes')
    op.drop_index(op.f('ix_workbook_cell_changes_cell_id'), table_name='workbook_cell_changes')
    op.drop_index(op.f('ix_workbook_cell_changes_audit_log_id'), table_name='workbook_cell_changes')
    op.drop_table('workbook_cell_changes')

    op.drop_index(op.f('ix_workbook_cells_row_id'), table_name='workbook_cells')
    op.drop_index(op.f('ix_workbook_cells_last_import_batch_id'), table_name='workbook_cells')
    op.drop_index(op.f('ix_workbook_cells_column_id'), table_name='workbook_cells')
    op.drop_index(op.f('ix_workbook_cells_cell_ref'), table_name='workbook_cells')
    op.drop_table('workbook_cells')

    op.drop_index(op.f('ix_workbook_rows_source_row_key'), table_name='workbook_rows')
    op.drop_index(op.f('ix_workbook_rows_sheet_id'), table_name='workbook_rows')
    op.drop_index(op.f('ix_workbook_rows_project_id'), table_name='workbook_rows')
    op.drop_index(op.f('ix_workbook_rows_lgu_id'), table_name='workbook_rows')
    op.drop_index(op.f('ix_workbook_rows_last_import_batch_id'), table_name='workbook_rows')
    op.drop_table('workbook_rows')

    op.drop_index(op.f('ix_workbook_columns_sheet_id'), table_name='workbook_columns')
    op.drop_index(op.f('ix_workbook_columns_normalized_header'), table_name='workbook_columns')
    op.drop_table('workbook_columns')

    op.drop_index(op.f('ix_workbook_sheets_workspace_id'), table_name='workbook_sheets')
    op.drop_index(op.f('ix_workbook_sheets_sheet_type'), table_name='workbook_sheets')
    op.drop_table('workbook_sheets')

    op.drop_index(op.f('ix_workbook_workspaces_source_import_batch_id'), table_name='workbook_workspaces')
    op.drop_index(op.f('ix_workbook_workspaces_schema_signature'), table_name='workbook_workspaces')
    op.drop_index(op.f('ix_workbook_workspaces_program_id'), table_name='workbook_workspaces')
    op.drop_index(op.f('ix_workbook_workspaces_program_cycle_id'), table_name='workbook_workspaces')
    op.drop_index(op.f('ix_workbook_workspaces_active_import_template_id'), table_name='workbook_workspaces')
    op.drop_table('workbook_workspaces')
