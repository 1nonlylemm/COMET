"""add_unique_index_for_null_source_project_identity

Revision ID: b7d2e4f6a8c0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-07 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7d2e4f6a8c0'
down_revision = 'f4a5b6c7d8e9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'uq_projects_null_source_identity',
        'projects',
        ['lgu_id', 'fiscal_year', sa.text('lower(trim(project_name))')],
        unique=True,
        postgresql_where=sa.text('source_project_code IS NULL'),
        sqlite_where=sa.text('source_project_code IS NULL'),
    )


def downgrade():
    op.drop_index('uq_projects_null_source_identity', table_name='projects')
