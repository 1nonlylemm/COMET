"""add role aware user scope assignments

Revision ID: b8c9d0e1f2a3
Revises: e1f2a3b4c5d6
Create Date: 2026-05-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c9d0e1f2a3'
down_revision = 'e1f2a3b4c5d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_scope_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=20), server_default='cluster', nullable=False),
        sa.Column('cluster_id', sa.Integer(), nullable=True),
        sa.Column('lgu_id', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.CheckConstraint("scope_type IN ('cluster', 'lgu')", name='ck_user_scope_type'),
        sa.CheckConstraint(
            "((scope_type = 'cluster' AND cluster_id IS NOT NULL AND lgu_id IS NULL) OR "
            "(scope_type = 'lgu' AND lgu_id IS NOT NULL AND cluster_id IS NULL))",
            name='ck_user_scope_target',
        ),
        sa.ForeignKeyConstraint(['cluster_id'], ['lgu_clusters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['lgu_id'], ['lgu_profiles.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'scope_type', 'cluster_id', name='uq_user_scope_cluster'),
        sa.UniqueConstraint('user_id', 'scope_type', 'lgu_id', name='uq_user_scope_lgu'),
    )
    with op.batch_alter_table('user_scope_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_scope_assignments_cluster_id'), ['cluster_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_scope_assignments_lgu_id'), ['lgu_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_scope_assignments_scope_type'), ['scope_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_user_scope_assignments_user_id'), ['user_id'], unique=False)

    op.execute(
        """
        INSERT INTO user_scope_assignments (user_id, scope_type, cluster_id, lgu_id, assigned_at, is_active)
        SELECT sla.user_id, 'cluster', sla.cluster_id, NULL::integer, sla.assigned_at, sla.is_active
        FROM staff_lgu_assignments AS sla
        JOIN users AS users_table ON users_table.id = sla.user_id
        WHERE users_table.role <> 'field_officer'
        """
    )
    op.execute(
        """
        INSERT INTO user_scope_assignments (user_id, scope_type, cluster_id, lgu_id, assigned_at, is_active)
        SELECT DISTINCT sla.user_id, 'lgu', NULL::integer, lgu_profiles.id, sla.assigned_at, sla.is_active
        FROM staff_lgu_assignments AS sla
        JOIN users AS users_table ON users_table.id = sla.user_id
        JOIN lgu_profiles ON lgu_profiles.cluster_id = sla.cluster_id
        WHERE users_table.role = 'field_officer'
        """
    )

    op.drop_table('staff_lgu_assignments')


def downgrade():
    op.create_table(
        'staff_lgu_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('cluster_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(['cluster_id'], ['lgu_clusters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'cluster_id', name='uq_staff_cluster'),
    )
    with op.batch_alter_table('staff_lgu_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_staff_lgu_assignments_cluster_id'), ['cluster_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_staff_lgu_assignments_user_id'), ['user_id'], unique=False)

    op.execute(
        """
        INSERT INTO staff_lgu_assignments (user_id, cluster_id, assigned_at, is_active)
        SELECT user_id, cluster_id, assigned_at, is_active
        FROM user_scope_assignments
        WHERE scope_type = 'cluster'
        """
    )
    op.execute(
        """
        INSERT INTO staff_lgu_assignments (user_id, cluster_id, assigned_at, is_active)
        SELECT DISTINCT scopes.user_id, lgu_profiles.cluster_id, scopes.assigned_at, scopes.is_active
        FROM user_scope_assignments AS scopes
        JOIN lgu_profiles ON lgu_profiles.id = scopes.lgu_id
        WHERE scopes.scope_type = 'lgu' AND lgu_profiles.cluster_id IS NOT NULL
        """
    )

    op.drop_table('user_scope_assignments')
