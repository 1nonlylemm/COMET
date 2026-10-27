"""Expand QAAR project management inputs.

Revision ID: b4c5d6e7f8a9
Revises: a3b5c8d1e2f4
Create Date: 2026-05-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b4c5d6e7f8a9'
down_revision = 'a3b5c8d1e2f4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'qaar_project_management_checks',
        sa.Column('form_data', sa.JSON(), server_default='{}', nullable=True),
    )
    op.alter_column(
        'qaar_project_management_checks',
        'response',
        existing_type=sa.String(length=30),
        type_=sa.String(length=300),
        existing_nullable=True,
    )
    op.alter_column(
        'qaar_health_safety_checks',
        'response',
        existing_type=sa.String(length=30),
        type_=sa.String(length=300),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        'qaar_health_safety_checks',
        'response',
        existing_type=sa.String(length=300),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
    op.alter_column(
        'qaar_project_management_checks',
        'response',
        existing_type=sa.String(length=300),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
    op.drop_column('qaar_project_management_checks', 'form_data')
