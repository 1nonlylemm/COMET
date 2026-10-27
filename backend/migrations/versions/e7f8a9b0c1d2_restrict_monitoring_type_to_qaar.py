"""Restrict implementation monitoring records to QAAR.

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-05-22 00:00:00.000000
"""

from alembic import op


revision = 'e7f8a9b0c1d2'
down_revision = 'd6e7f8a9b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "UPDATE qaar_inspections "
        "SET monitoring_type = 'qaar' "
        "WHERE monitoring_type IS NULL OR monitoring_type <> 'qaar'"
    )
    op.execute('ALTER TABLE qaar_inspections DROP CONSTRAINT IF EXISTS ck_qaar_monitoring_type')
    op.create_check_constraint(
        'ck_qaar_monitoring_type',
        'qaar_inspections',
        "monitoring_type IN ('qaar')",
    )


def downgrade():
    op.execute('ALTER TABLE qaar_inspections DROP CONSTRAINT IF EXISTS ck_qaar_monitoring_type')
    op.create_check_constraint(
        'ck_qaar_monitoring_type',
        'qaar_inspections',
        "monitoring_type IN ('qaar', 'aide_memoire', 'site_validation', 'follow_up')",
    )
