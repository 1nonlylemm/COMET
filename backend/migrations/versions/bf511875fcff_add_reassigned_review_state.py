"""add_reassignment_reason

Revision ID: bf511875fcff
Revises: 7ca71a81372f
Create Date: 2026-08-21 06:06:53.150793

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bf511875fcff'
down_revision = 'b1c2d3e4f5g9'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('nlp_scan_results', sa.Column('reassignment_reason', sa.String(length=250), nullable=True))

def downgrade():
    op.drop_column('nlp_scan_results', 'reassignment_reason')
