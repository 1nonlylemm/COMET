"""add_dispatch_and_magic_link_metadata

Revision ID: c7b0c1d9f4f2
Revises: a2e7f1830a3d
Create Date: 2026-04-11 09:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7b0c1d9f4f2'
down_revision = 'a2e7f1830a3d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('magic_links', schema=None) as batch_op:
        batch_op.add_column(sa.Column('notice_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('intended_recipient_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('intended_recipient_role', sa.String(length=100), nullable=True))
        batch_op.create_index(batch_op.f('ix_magic_links_notice_id'), ['notice_id'], unique=False)
        batch_op.create_foreign_key('fk_magic_links_notice_id', 'escalation_notices', ['notice_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_magic_links_created_by', 'users', ['created_by'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('communication_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('channel', sa.String(length=50), server_default='email', nullable=False))
        batch_op.add_column(sa.Column('recipient_destination', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('recipient_office', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('reference_no', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('posted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('remarks', sa.Text(), nullable=True))
        batch_op.alter_column('recipient_email', existing_type=sa.String(length=255), nullable=True)
        batch_op.create_check_constraint(
            'ck_communication_channel',
            "channel IN ('email', 'dms', 'intranet', 'manual_print', 'magic_link')",
        )

    with op.batch_alter_table('notice_recipients', schema=None) as batch_op:
        batch_op.drop_constraint('ck_delivery_method', type_='check')
        batch_op.create_check_constraint(
            'ck_delivery_method',
            "delivery_method IN ('email', 'physical_mail', 'magic_link', 'field_officer', 'dms', 'intranet', 'manual_print')",
        )


def downgrade():
    with op.batch_alter_table('notice_recipients', schema=None) as batch_op:
        batch_op.drop_constraint('ck_delivery_method', type_='check')
        batch_op.create_check_constraint(
            'ck_delivery_method',
            "delivery_method IN ('email', 'physical_mail', 'magic_link', 'field_officer')",
        )

    with op.batch_alter_table('communication_logs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_communication_channel', type_='check')
        batch_op.alter_column('recipient_email', existing_type=sa.String(length=255), nullable=False)
        batch_op.drop_column('remarks')
        batch_op.drop_column('posted_at')
        batch_op.drop_column('reference_no')
        batch_op.drop_column('recipient_office')
        batch_op.drop_column('recipient_destination')
        batch_op.drop_column('channel')

    with op.batch_alter_table('magic_links', schema=None) as batch_op:
        batch_op.drop_constraint('fk_magic_links_created_by', type_='foreignkey')
        batch_op.drop_constraint('fk_magic_links_notice_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_magic_links_notice_id'))
        batch_op.drop_column('intended_recipient_role')
        batch_op.drop_column('intended_recipient_name')
        batch_op.drop_column('created_by')
        batch_op.drop_column('notice_id')
