"""add ai guardrail events

Revision ID: a7d8e9f0b1c2
Revises: f9a1b2c3d4e6
Create Date: 2026-04-26 19:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7d8e9f0b1c2'
down_revision = 'f9a1b2c3d4e6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_guardrail_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('decision', sa.String(length=30), nullable=False),
        sa.Column('category', sa.String(length=60), nullable=False),
        sa.Column('severity', sa.String(length=20), server_default='low', nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('matched_rules', sa.JSON(), server_default='[]', nullable=True),
        sa.Column('prompt_preview', sa.String(length=500), nullable=True),
        sa.Column('prompt_hash', sa.String(length=64), nullable=True),
        sa.Column('provider_called', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('metadata', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['ai_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_guardrail_events_category'), 'ai_guardrail_events', ['category'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_conversation_id'), 'ai_guardrail_events', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_created_at'), 'ai_guardrail_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_decision'), 'ai_guardrail_events', ['decision'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_message_id'), 'ai_guardrail_events', ['message_id'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_prompt_hash'), 'ai_guardrail_events', ['prompt_hash'], unique=False)
    op.create_index(op.f('ix_ai_guardrail_events_user_id'), 'ai_guardrail_events', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ai_guardrail_events_user_id'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_prompt_hash'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_message_id'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_decision'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_created_at'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_conversation_id'), table_name='ai_guardrail_events')
    op.drop_index(op.f('ix_ai_guardrail_events_category'), table_name='ai_guardrail_events')
    op.drop_table('ai_guardrail_events')
