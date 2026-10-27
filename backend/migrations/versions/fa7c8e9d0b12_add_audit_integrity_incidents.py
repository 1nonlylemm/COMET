"""add audit integrity incidents

Revision ID: fa7c8e9d0b12
Revises: a9c4d2e7f8b1
Create Date: 2026-05-01 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fa7c8e9d0b12'
down_revision = 'a9c4d2e7f8b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'audit_integrity_incidents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=30), server_default='open', nullable=False),
        sa.Column('broken_at_id', sa.Integer(), nullable=True),
        sa.Column('mismatch_type', sa.String(length=40), server_default='unknown', nullable=False),
        sa.Column('expected_hash', sa.String(length=64), nullable=True),
        sa.Column('actual_hash', sa.String(length=64), nullable=True),
        sa.Column('expected_previous_hash', sa.String(length=64), nullable=True),
        sa.Column('actual_previous_hash', sa.String(length=64), nullable=True),
        sa.Column('opened_by', sa.Integer(), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=False),
        sa.Column('investigation_notes', sa.Text(), nullable=True),
        sa.Column('resolution_type', sa.String(length=40), nullable=True),
        sa.Column('resolution_notes', sa.Text(), nullable=True),
        sa.Column('resolved_by', sa.Integer(), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "mismatch_type IN ('record_hash_mismatch', 'previous_hash_mismatch', 'unknown')",
            name='ck_audit_integrity_incident_mismatch_type',
        ),
        sa.CheckConstraint(
            "resolution_type IS NULL OR resolution_type IN ('restored_original', 'restored_backup', 'rebaselined', 'false_alarm')",
            name='ck_audit_integrity_incident_resolution_type',
        ),
        sa.CheckConstraint(
            "status IN ('open', 'resolved', 'rebaselined')",
            name='ck_audit_integrity_incident_status',
        ),
        sa.ForeignKeyConstraint(['broken_at_id'], ['audit_logs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['opened_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_integrity_incidents_broken_at_id'), 'audit_integrity_incidents', ['broken_at_id'], unique=False)
    op.create_index(op.f('ix_audit_integrity_incidents_opened_at'), 'audit_integrity_incidents', ['opened_at'], unique=False)
    op.create_index(op.f('ix_audit_integrity_incidents_opened_by'), 'audit_integrity_incidents', ['opened_by'], unique=False)
    op.create_index(op.f('ix_audit_integrity_incidents_status'), 'audit_integrity_incidents', ['status'], unique=False)

    op.create_table(
        'audit_integrity_checkpoints',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('incident_id', sa.Integer(), nullable=False),
        sa.Column('checkpoint_audit_log_id', sa.Integer(), nullable=True),
        sa.Column('checkpoint_hash', sa.String(length=64), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['checkpoint_audit_log_id'], ['audit_logs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['incident_id'], ['audit_integrity_incidents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_integrity_checkpoints_checkpoint_audit_log_id'), 'audit_integrity_checkpoints', ['checkpoint_audit_log_id'], unique=False)
    op.create_index(op.f('ix_audit_integrity_checkpoints_created_at'), 'audit_integrity_checkpoints', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_integrity_checkpoints_created_by'), 'audit_integrity_checkpoints', ['created_by'], unique=False)
    op.create_index(op.f('ix_audit_integrity_checkpoints_incident_id'), 'audit_integrity_checkpoints', ['incident_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_audit_integrity_checkpoints_incident_id'), table_name='audit_integrity_checkpoints')
    op.drop_index(op.f('ix_audit_integrity_checkpoints_created_by'), table_name='audit_integrity_checkpoints')
    op.drop_index(op.f('ix_audit_integrity_checkpoints_created_at'), table_name='audit_integrity_checkpoints')
    op.drop_index(op.f('ix_audit_integrity_checkpoints_checkpoint_audit_log_id'), table_name='audit_integrity_checkpoints')
    op.drop_table('audit_integrity_checkpoints')

    op.drop_index(op.f('ix_audit_integrity_incidents_status'), table_name='audit_integrity_incidents')
    op.drop_index(op.f('ix_audit_integrity_incidents_opened_by'), table_name='audit_integrity_incidents')
    op.drop_index(op.f('ix_audit_integrity_incidents_opened_at'), table_name='audit_integrity_incidents')
    op.drop_index(op.f('ix_audit_integrity_incidents_broken_at_id'), table_name='audit_integrity_incidents')
    op.drop_table('audit_integrity_incidents')
