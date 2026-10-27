"""expand developer A operational surfaces

Revision ID: d2a9c6e8b4f1
Revises: b7c9d1e2f3a4
Create Date: 2026-04-26 14:35:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2a9c6e8b4f1'
down_revision = 'b7c9d1e2f3a4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('qaar_inspections', schema=None) as batch_op:
        batch_op.add_column(sa.Column('monitoring_type', sa.String(length=30), server_default='qaar', nullable=False))
        batch_op.add_column(sa.Column('observation_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('agreement_summary', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('transmittal_status', sa.String(length=30), server_default='not_required', nullable=False))
        batch_op.add_column(sa.Column('transmittal_reference', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('transmitted_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('monthly_cycle_tag', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('monthly_cycle_note', sa.Text(), nullable=True))
        batch_op.create_check_constraint(
            'ck_qaar_monitoring_type',
            "monitoring_type IN ('qaar', 'aide_memoire', 'site_validation', 'follow_up')",
        )
        batch_op.create_check_constraint(
            'ck_qaar_transmittal_status',
            "transmittal_status IN ('not_required', 'pending', 'transmitted', 'acknowledged')",
        )


def downgrade():
    with op.batch_alter_table('qaar_inspections', schema=None) as batch_op:
        batch_op.drop_constraint('ck_qaar_transmittal_status', type_='check')
        batch_op.drop_constraint('ck_qaar_monitoring_type', type_='check')
        batch_op.drop_column('monthly_cycle_note')
        batch_op.drop_column('monthly_cycle_tag')
        batch_op.drop_column('transmitted_at')
        batch_op.drop_column('transmittal_reference')
        batch_op.drop_column('transmittal_status')
        batch_op.drop_column('agreement_summary')
        batch_op.drop_column('observation_summary')
        batch_op.drop_column('monitoring_type')
