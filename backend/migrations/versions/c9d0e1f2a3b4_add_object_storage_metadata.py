"""add object storage metadata

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-05-16 17:45:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stored_objects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('storage_provider', sa.String(length=30), nullable=False),
        sa.Column('bucket_name', sa.String(length=255), nullable=True),
        sa.Column('object_key', sa.String(length=1000), nullable=False),
        sa.Column('original_filename', sa.String(length=500), nullable=True),
        sa.Column('content_type', sa.String(length=255), nullable=True),
        sa.Column('size_bytes', sa.BigInteger(), nullable=True),
        sa.Column('sha256_hash', sa.String(length=64), nullable=True),
        sa.Column('etag', sa.String(length=255), nullable=True),
        sa.Column('source_module', sa.String(length=100), nullable=True),
        sa.Column('legacy_file_path', sa.String(length=1000), nullable=True),
        sa.Column('object_metadata', sa.JSON(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_stored_objects_bucket_name'), 'stored_objects', ['bucket_name'], unique=False)
    op.create_index(op.f('ix_stored_objects_created_at'), 'stored_objects', ['created_at'], unique=False)
    op.create_index(op.f('ix_stored_objects_object_key'), 'stored_objects', ['object_key'], unique=False)
    op.create_index(op.f('ix_stored_objects_sha256_hash'), 'stored_objects', ['sha256_hash'], unique=False)
    op.create_index(op.f('ix_stored_objects_source_module'), 'stored_objects', ['source_module'], unique=False)
    op.create_index(op.f('ix_stored_objects_storage_provider'), 'stored_objects', ['storage_provider'], unique=False)
    op.create_index(op.f('ix_stored_objects_uploaded_by'), 'stored_objects', ['uploaded_by'], unique=False)

    with op.batch_alter_table('document_files', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stored_object_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_document_files_stored_object_id'), ['stored_object_id'], unique=False)
        batch_op.create_foreign_key('fk_document_files_stored_object_id_stored_objects', 'stored_objects', ['stored_object_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('submission_versions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stored_object_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_submission_versions_stored_object_id'), ['stored_object_id'], unique=False)
        batch_op.create_foreign_key('fk_submission_versions_stored_object_id_stored_objects', 'stored_objects', ['stored_object_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('program_guidelines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stored_object_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_program_guidelines_stored_object_id'), ['stored_object_id'], unique=False)
        batch_op.create_foreign_key('fk_program_guidelines_stored_object_id_stored_objects', 'stored_objects', ['stored_object_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('import_batches', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stored_object_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_import_batches_stored_object_id'), ['stored_object_id'], unique=False)
        batch_op.create_foreign_key('fk_import_batches_stored_object_id_stored_objects', 'stored_objects', ['stored_object_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('import_batches', schema=None) as batch_op:
        batch_op.drop_constraint('fk_import_batches_stored_object_id_stored_objects', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_import_batches_stored_object_id'))
        batch_op.drop_column('stored_object_id')

    with op.batch_alter_table('program_guidelines', schema=None) as batch_op:
        batch_op.drop_constraint('fk_program_guidelines_stored_object_id_stored_objects', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_program_guidelines_stored_object_id'))
        batch_op.drop_column('stored_object_id')

    with op.batch_alter_table('submission_versions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_submission_versions_stored_object_id_stored_objects', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_submission_versions_stored_object_id'))
        batch_op.drop_column('stored_object_id')

    with op.batch_alter_table('document_files', schema=None) as batch_op:
        batch_op.drop_constraint('fk_document_files_stored_object_id_stored_objects', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_document_files_stored_object_id'))
        batch_op.drop_column('stored_object_id')

    op.drop_index(op.f('ix_stored_objects_uploaded_by'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_storage_provider'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_source_module'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_sha256_hash'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_object_key'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_created_at'), table_name='stored_objects')
    op.drop_index(op.f('ix_stored_objects_bucket_name'), table_name='stored_objects')
    op.drop_table('stored_objects')
