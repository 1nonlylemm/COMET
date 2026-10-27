"""Expand QAAR check key lengths.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd6e7f8a9b0c1'
down_revision = 'c5d6e7f8a9b0'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'qaar_project_management_checks',
        'check_key',
        existing_type=sa.String(length=120),
        type_=sa.String(length=255),
        existing_nullable=False,
    )
    op.alter_column(
        'qaar_health_safety_checks',
        'check_key',
        existing_type=sa.String(length=120),
        type_=sa.String(length=255),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'qaar_health_safety_checks',
        'check_key',
        existing_type=sa.String(length=255),
        type_=sa.String(length=120),
        existing_nullable=False,
    )
    op.alter_column(
        'qaar_project_management_checks',
        'check_key',
        existing_type=sa.String(length=255),
        type_=sa.String(length=120),
        existing_nullable=False,
    )
