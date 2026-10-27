"""Make non-empty project codes globally unique, ignoring case and outer spaces.

Revision ID: a6b7c8d9e0f1
Revises: e5f6a7b8c9d0
"""
from alembic import op
import sqlalchemy as sa

revision = 'a6b7c8d9e0f1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    # Do not silently rename established references or merge existing projects.
    duplicates = op.get_bind().execute(sa.text("""
        SELECT lower(trim(source_project_code)) AS code, count(*) AS total
        FROM projects
        WHERE source_project_code IS NOT NULL AND trim(source_project_code) <> ''
        GROUP BY lower(trim(source_project_code))
        HAVING count(*) > 1
        ORDER BY lower(trim(source_project_code))
        LIMIT 20
    """)).fetchall()
    if duplicates:
        codes = ', '.join(f'{row.code} ({row.total} projects)' for row in duplicates)
        raise RuntimeError(
            'Cannot enforce unique project codes. Resolve existing duplicate codes '
            f'before rerunning this migration: {codes}'
        )
    op.create_index(
        'uq_projects_source_code',
        'projects',
        [sa.text('lower(trim(source_project_code))')],
        unique=True,
        postgresql_where=sa.text("source_project_code IS NOT NULL AND trim(source_project_code) <> ''"),
        sqlite_where=sa.text("source_project_code IS NOT NULL AND trim(source_project_code) <> ''"),
    )


def downgrade():
    op.drop_index('uq_projects_source_code', table_name='projects')
