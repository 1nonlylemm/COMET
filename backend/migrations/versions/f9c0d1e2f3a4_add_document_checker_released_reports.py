"""add document checker released reports

Revision ID: f9c0d1e2f3a4
Revises: f9b0c1d2e3f4
Create Date: 2026-06-06 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f9c0d1e2f3a4'
down_revision = 'f9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'document_checker_released_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=40), server_default='released', nullable=False),
        sa.Column('report_version', sa.String(length=80), server_default='v1', nullable=False),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('released_by', sa.Integer(), nullable=True),
        sa.Column('released_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('released', 'revoked')",
            name='ck_document_checker_released_report_status',
        ),
        sa.ForeignKeyConstraint(
            ['released_by'],
            ['users.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['run_id'],
            ['document_checker_evaluation_runs.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', name='uq_document_checker_released_report_run'),
    )
    op.create_index(
        'ix_document_checker_released_reports_created_at',
        'document_checker_released_reports',
        ['created_at'],
    )
    op.create_index(
        'ix_document_checker_released_reports_released_at',
        'document_checker_released_reports',
        ['released_at'],
    )
    op.create_index(
        'ix_document_checker_released_reports_released_by',
        'document_checker_released_reports',
        ['released_by'],
    )
    op.create_index(
        'ix_document_checker_released_reports_status',
        'document_checker_released_reports',
        ['status'],
    )


def downgrade():
    op.drop_index('ix_document_checker_released_reports_status', table_name='document_checker_released_reports')
    op.drop_index('ix_document_checker_released_reports_released_by', table_name='document_checker_released_reports')
    op.drop_index('ix_document_checker_released_reports_released_at', table_name='document_checker_released_reports')
    op.drop_index('ix_document_checker_released_reports_created_at', table_name='document_checker_released_reports')
    op.drop_table('document_checker_released_reports')
