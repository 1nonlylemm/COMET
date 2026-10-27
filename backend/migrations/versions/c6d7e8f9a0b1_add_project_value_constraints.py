"""add project value constraints

Revision ID: c6d7e8f9a0b1
Revises: fa7c8e9d0b12
Create Date: 2026-05-05 12:00:00.000000
"""

from alembic import op


revision = 'c6d7e8f9a0b1'
down_revision = 'fa7c8e9d0b12'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_project_fiscal_year_range',
            'fiscal_year BETWEEN 2000 AND 2100',
        )
        batch_op.create_check_constraint(
            'ck_project_budget_non_negative',
            'budget_amount IS NULL OR budget_amount >= 0',
        )
        batch_op.create_check_constraint(
            'ck_project_completion_pct_range',
            'physical_completion_pct IS NULL OR (physical_completion_pct >= 0 AND physical_completion_pct <= 100)',
        )
        batch_op.create_check_constraint(
            'ck_project_target_date_order',
            'target_start_date IS NULL OR target_end_date IS NULL OR target_end_date >= target_start_date',
        )
        batch_op.create_check_constraint(
            'ck_project_actual_date_order',
            'actual_start_date IS NULL OR actual_end_date IS NULL OR actual_end_date >= actual_start_date',
        )


def downgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_constraint('ck_project_actual_date_order', type_='check')
        batch_op.drop_constraint('ck_project_target_date_order', type_='check')
        batch_op.drop_constraint('ck_project_completion_pct_range', type_='check')
        batch_op.drop_constraint('ck_project_budget_non_negative', type_='check')
        batch_op.drop_constraint('ck_project_fiscal_year_range', type_='check')
