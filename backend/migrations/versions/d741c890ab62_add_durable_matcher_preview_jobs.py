"""Add durable Matcher preview state and worker leases.

Revision ID: d741c890ab62
Revises: b5c6d7e8f9a0
"""
from alembic import op
import sqlalchemy as sa

revision = 'd741c890ab62'
down_revision = 'b5c6d7e8f9a0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('matcher_preview_jobs',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('owner_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('object_id', sa.Integer(), sa.ForeignKey('stored_objects.id', ondelete='SET NULL')),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('lease_token', sa.String(32)),
        sa.Column('lease_expires_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False))
    for name in ('owner_id', 'status', 'lease_expires_at', 'updated_at', 'expires_at'):
        op.create_index('ix_matcher_preview_jobs_' + name, 'matcher_preview_jobs', [name])


def downgrade():
    op.drop_table('matcher_preview_jobs')
