"""align_notice_recipients_with_dispatch_workflow

Revision ID: e4b7a1d2c9f0
Revises: c7b0c1d9f4f2
Create Date: 2026-04-11 15:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4b7a1d2c9f0'
down_revision = 'c7b0c1d9f4f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('notice_recipients', schema=None) as batch_op:
        batch_op.alter_column(
            'recipient_email',
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch_op.alter_column(
            'delivery_method',
            existing_type=sa.String(length=50),
            server_default='pending_dispatch',
            existing_nullable=False,
        )
        batch_op.drop_constraint('ck_delivery_method', type_='check')
        batch_op.create_check_constraint(
            'ck_delivery_method',
            "delivery_method IN ('pending_dispatch', 'email', 'physical_mail', 'magic_link', 'field_officer', 'dms', 'intranet', 'manual_print')",
        )


def downgrade():
    with op.batch_alter_table('notice_recipients', schema=None) as batch_op:
        batch_op.drop_constraint('ck_delivery_method', type_='check')
        batch_op.create_check_constraint(
            'ck_delivery_method',
            "delivery_method IN ('email', 'physical_mail', 'magic_link', 'field_officer', 'dms', 'intranet', 'manual_print')",
        )
        batch_op.alter_column(
            'delivery_method',
            existing_type=sa.String(length=50),
            server_default='email',
            existing_nullable=False,
        )
        batch_op.alter_column(
            'recipient_email',
            existing_type=sa.String(length=255),
            nullable=False,
        )
