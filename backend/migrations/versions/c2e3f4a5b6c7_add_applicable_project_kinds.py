"""add applicable_project_kinds to requirements

Revision ID: c2e3f4a5b6c7
Revises: b1d2e3f4a5b6
Create Date: 2026-09-06 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2e3f4a5b6c7'
down_revision = 'd4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'requirements',
        sa.Column('applicable_project_kinds', sa.JSON(), nullable=False, server_default='["infrastructure"]')
    )


def downgrade():
    op.drop_column('requirements', 'applicable_project_kinds')
