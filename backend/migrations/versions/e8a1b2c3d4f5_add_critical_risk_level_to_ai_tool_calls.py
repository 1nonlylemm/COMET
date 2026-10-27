"""add critical risk level to ck_ai_tool_call_risk_level

Revision ID: e8a1b2c3d4f5
Revises: 646874f6ee39
Create Date: 2026-09-02 05:08:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8a1b2c3d4f5'
down_revision = '646874f6ee39'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('ai_tool_calls', schema=None) as batch_op:
        batch_op.drop_constraint('ck_ai_tool_call_risk_level', type_='check')
        batch_op.create_check_constraint(
            'ck_ai_tool_call_risk_level',
            "risk_level IN ('low', 'medium', 'high', 'critical')"
        )


def downgrade():
    with op.batch_alter_table('ai_tool_calls', schema=None) as batch_op:
        batch_op.drop_constraint('ck_ai_tool_call_risk_level', type_='check')
        batch_op.create_check_constraint(
            'ck_ai_tool_call_risk_level',
            "risk_level IN ('low', 'medium', 'high')"
        )
