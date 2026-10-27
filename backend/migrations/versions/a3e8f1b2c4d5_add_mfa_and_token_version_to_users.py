"""add mfa and token version to users

Revision ID: a3e8f1b2c4d5
Revises: c2e3f4a5b6c7
Create Date: 2026-09-07 01:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3e8f1b2c4d5'
down_revision = 'c2e3f4a5b6c7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'users',
        sa.Column('token_version', sa.Integer(), nullable=False, server_default='1')
    )
    op.add_column(
        'users',
        sa.Column('mfa_enabled', sa.Boolean(), nullable=False, server_default='false')
    )
    op.add_column(
        'users',
        sa.Column('mfa_secret', sa.String(length=255), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('mfa_type', sa.String(length=20), nullable=True, server_default='totp')
    )
    op.add_column(
        'users',
        sa.Column('last_mfa_verified_at', sa.DateTime(), nullable=True)
    )
    op.add_column(
        'users',
        sa.Column('last_step_up_at', sa.DateTime(), nullable=True)
    )

    op.create_table(
        'mfa_recovery_codes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(op.f('ix_mfa_recovery_codes_user_id'), 'mfa_recovery_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_mfa_recovery_codes_code_hash'), 'mfa_recovery_codes', ['code_hash'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_mfa_recovery_codes_code_hash'), table_name='mfa_recovery_codes')
    op.drop_index(op.f('ix_mfa_recovery_codes_user_id'), table_name='mfa_recovery_codes')
    op.drop_table('mfa_recovery_codes')

    op.drop_column('users', 'last_step_up_at')
    op.drop_column('users', 'last_mfa_verified_at')
    op.drop_column('users', 'mfa_type')
    op.drop_column('users', 'mfa_secret')
    op.drop_column('users', 'mfa_enabled')
    op.drop_column('users', 'token_version')
