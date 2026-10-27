"""add system admin role

Revision ID: f9b0c1d2e3f4
Revises: f8a9b0c1d2e3
Create Date: 2026-06-05 22:00:00.000000
"""

from alembic import op


revision = 'f9b0c1d2e3f4'
down_revision = 'f8a9b0c1d2e3'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint('ck_user_role', 'users', type_='check')
    op.create_check_constraint(
        'ck_user_role',
        'users',
        "role IN ('system_admin', 'admin', 'staff', 'field_officer')",
    )


def downgrade():
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'system_admin'")
    op.drop_constraint('ck_user_role', 'users', type_='check')
    op.create_check_constraint(
        'ck_user_role',
        'users',
        "role IN ('admin', 'staff', 'field_officer')",
    )
