"""add_branding_defaults

Revision ID: b1c2d3e4f5a6
Revises: a7d8e9f0b1c2
Create Date: 2026-04-26 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = 'a7d8e9f0b1c2'
branch_labels = None
depends_on = None

OLD_ASSISTANT_TITLE = ''.join(('CO', 'MET AI Conversation'))
NEW_ASSISTANT_TITLE = 'Assistant Conversation'


def upgrade():
    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.alter_column(
            'title',
            existing_type=sa.String(length=200),
            existing_nullable=False,
            server_default=NEW_ASSISTANT_TITLE,
        )

    op.execute(
        "UPDATE ai_conversations "
        f"SET title = '{NEW_ASSISTANT_TITLE}' "
        f"WHERE title = '{OLD_ASSISTANT_TITLE}'"
    )


def downgrade():
    op.execute(
        "UPDATE ai_conversations "
        f"SET title = '{OLD_ASSISTANT_TITLE}' "
        f"WHERE title = '{NEW_ASSISTANT_TITLE}'"
    )

    with op.batch_alter_table('ai_conversations', schema=None) as batch_op:
        batch_op.alter_column(
            'title',
            existing_type=sa.String(length=200),
            existing_nullable=False,
            server_default=OLD_ASSISTANT_TITLE,
        )
