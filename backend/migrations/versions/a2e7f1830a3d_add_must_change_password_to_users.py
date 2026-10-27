"""add_must_change_password_to_users

Revision ID: a2e7f1830a3d
Revises: 61b0c3020bc2
Create Date: 2026-04-10 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2e7f1830a3d'
down_revision = '61b0c3020bc2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('must_change_password', sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('must_change_password')
