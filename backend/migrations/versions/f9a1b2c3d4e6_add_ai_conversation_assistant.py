"""add ai conversation assistant

Revision ID: f9a1b2c3d4e6
Revises: e8f4a1b2c3d5
Create Date: 2026-04-26 18:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9a1b2c3d4e6'
down_revision = 'e8f4a1b2c3d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ai_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), server_default='Assistant Conversation', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='active', nullable=False),
        sa.Column('context', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived')", name='ck_ai_conversation_status'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_conversations_user_id'), 'ai_conversations', ['user_id'], unique=False)

    op.create_table(
        'ai_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('response_type', sa.String(length=30), server_default='text', nullable=False),
        sa.Column('display_payload', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('ai_provider_used', sa.String(length=50), nullable=True),
        sa.Column('ai_model_used', sa.String(length=120), nullable=True),
        sa.Column('prompt_snapshot', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name='ck_ai_message_role'),
        sa.CheckConstraint(
            "response_type IN ('text', 'tool_result', 'confirmation', 'error')",
            name='ck_ai_message_response_type',
        ),
        sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_messages_conversation_id'), 'ai_messages', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_ai_messages_created_at'), 'ai_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_messages_user_id'), 'ai_messages', ['user_id'], unique=False)

    op.create_table(
        'ai_tool_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=True),
        sa.Column('requested_by', sa.Integer(), nullable=True),
        sa.Column('executed_by', sa.Integer(), nullable=True),
        sa.Column('tool_name', sa.String(length=100), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('risk_level', sa.String(length=20), server_default='low', nullable=False),
        sa.Column('requires_confirmation', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('status', sa.String(length=30), server_default='planned', nullable=False),
        sa.Column('input_data', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('output_data', sa.JSON(), server_default='{}', nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("risk_level IN ('low', 'medium', 'high')", name='ck_ai_tool_call_risk_level'),
        sa.CheckConstraint(
            "status IN ('planned', 'pending_confirmation', 'completed', 'failed', 'cancelled')",
            name='ck_ai_tool_call_status',
        ),
        sa.ForeignKeyConstraint(['conversation_id'], ['ai_conversations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['executed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['message_id'], ['ai_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ai_tool_calls_conversation_id'), 'ai_tool_calls', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_created_at'), 'ai_tool_calls', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_executed_by'), 'ai_tool_calls', ['executed_by'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_message_id'), 'ai_tool_calls', ['message_id'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_requested_by'), 'ai_tool_calls', ['requested_by'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_status'), 'ai_tool_calls', ['status'], unique=False)
    op.create_index(op.f('ix_ai_tool_calls_tool_name'), 'ai_tool_calls', ['tool_name'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_ai_tool_calls_tool_name'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_status'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_requested_by'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_message_id'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_executed_by'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_created_at'), table_name='ai_tool_calls')
    op.drop_index(op.f('ix_ai_tool_calls_conversation_id'), table_name='ai_tool_calls')
    op.drop_table('ai_tool_calls')

    op.drop_index(op.f('ix_ai_messages_user_id'), table_name='ai_messages')
    op.drop_index(op.f('ix_ai_messages_created_at'), table_name='ai_messages')
    op.drop_index(op.f('ix_ai_messages_conversation_id'), table_name='ai_messages')
    op.drop_table('ai_messages')

    op.drop_index(op.f('ix_ai_conversations_user_id'), table_name='ai_conversations')
    op.drop_table('ai_conversations')
