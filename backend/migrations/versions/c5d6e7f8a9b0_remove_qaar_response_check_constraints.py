"""Remove fixed QAAR response check constraints.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-22 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c5d6e7f8a9b0'
down_revision = 'b4c5d6e7f8a9'
branch_labels = None
depends_on = None


def _check_constraint_exists(table_name, constraint_name):
    inspector = sa.inspect(op.get_bind())
    return any(
        constraint.get('name') == constraint_name
        for constraint in inspector.get_check_constraints(table_name)
    )


def _drop_check_constraint_if_exists(table_name, constraint_name):
    if _check_constraint_exists(table_name, constraint_name):
        op.drop_constraint(constraint_name, table_name, type_='check')


def _create_check_constraint_if_missing(table_name, constraint_name, condition):
    if not _check_constraint_exists(table_name, constraint_name):
        op.create_check_constraint(constraint_name, table_name, condition)


def upgrade():
    _drop_check_constraint_if_exists(
        'qaar_project_management_checks',
        'ck_qaar_pm_check_response',
    )
    _drop_check_constraint_if_exists(
        'qaar_health_safety_checks',
        'ck_qaar_health_safety_response',
    )


def downgrade():
    _create_check_constraint_if_missing(
        'qaar_health_safety_checks',
        'ck_qaar_health_safety_response',
        "response IS NULL OR response IN ('yes', 'no', 'not_applicable', 'not_observed', 'partial')",
    )
    _create_check_constraint_if_missing(
        'qaar_project_management_checks',
        'ck_qaar_pm_check_response',
        "response IS NULL OR response IN ('yes', 'no', 'not_applicable', 'not_observed', 'partial')",
    )
