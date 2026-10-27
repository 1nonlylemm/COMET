"""add workflow comments

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-05-07 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7e8f9a0b1c2'
down_revision = 'c6d7e8f9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workflow_comments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('project_requirement_id', sa.Integer(), nullable=True),
        sa.Column('lgu_id', sa.Integer(), nullable=True),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('visibility', sa.String(length=30), server_default='internal', nullable=False),
        sa.Column('comment_type', sa.String(length=50), server_default='comment', nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('project', 'project_requirement', 'sla_deadline', 'qaar_inspection', 'escalation_notice')",
            name='ck_workflow_comment_entity_type',
        ),
        sa.CheckConstraint(
            "visibility IN ('internal', 'field_visible', 'staff_only')",
            name='ck_workflow_comment_visibility',
        ),
        sa.CheckConstraint(
            "comment_type IN ('comment', 'field_follow_up', 'submission_update', 'clarification', 'acknowledgement', 'review_note')",
            name='ck_workflow_comment_type',
        ),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['lgu_id'], ['lgu_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_requirement_id'], ['project_requirements.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_workflow_comments_author_id'), 'workflow_comments', ['author_id'], unique=False)
    op.create_index(op.f('ix_workflow_comments_created_at'), 'workflow_comments', ['created_at'], unique=False)
    op.create_index(op.f('ix_workflow_comments_entity_id'), 'workflow_comments', ['entity_id'], unique=False)
    op.create_index(op.f('ix_workflow_comments_entity_type'), 'workflow_comments', ['entity_type'], unique=False)
    op.create_index(op.f('ix_workflow_comments_lgu_id'), 'workflow_comments', ['lgu_id'], unique=False)
    op.create_index(op.f('ix_workflow_comments_project_id'), 'workflow_comments', ['project_id'], unique=False)
    op.create_index(
        op.f('ix_workflow_comments_project_requirement_id'),
        'workflow_comments',
        ['project_requirement_id'],
        unique=False,
    )
    op.create_index('idx_workflow_comment_entity', 'workflow_comments', ['entity_type', 'entity_id'], unique=False)


def downgrade():
    op.drop_index('idx_workflow_comment_entity', table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_project_requirement_id'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_project_id'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_lgu_id'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_entity_type'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_entity_id'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_created_at'), table_name='workflow_comments')
    op.drop_index(op.f('ix_workflow_comments_author_id'), table_name='workflow_comments')
    op.drop_table('workflow_comments')
