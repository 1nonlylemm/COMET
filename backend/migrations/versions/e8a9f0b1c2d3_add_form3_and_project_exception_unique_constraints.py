"""add form3 and project exception unique constraints

Revision ID: e8a9f0b1c2d3
Revises: b7d2e4f6a8c0
Create Date: 2026-10-08 18:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8a9f0b1c2d3'
down_revision = 'b7d2e4f6a8c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        'uq_form3_request_project_period',
        'form3_requests',
        ['project_id', 'reporting_period'],
    )
    op.create_unique_constraint(
        'uq_project_exception_project_period',
        'project_exception_reports',
        ['project_id', 'reporting_period'],
    )


def downgrade():
    op.drop_constraint('uq_project_exception_project_period', 'project_exception_reports', type_='unique')
    op.drop_constraint('uq_form3_request_project_period', 'form3_requests', type_='unique')
