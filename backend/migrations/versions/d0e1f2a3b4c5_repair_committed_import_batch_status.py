"""Repair committed import batch status drift.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-05-17
"""

from alembic import op


revision = 'd0e1f2a3b4c5'
down_revision = 'c9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE import_batches
        SET status = 'committed'
        WHERE committed_at IS NOT NULL
          AND status <> 'committed'
        """
    )


def downgrade():
    pass
