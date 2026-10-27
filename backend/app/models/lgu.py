from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class LguCluster(db.Model):
    __tablename__ = 'lgu_clusters'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    lgus = db.relationship('LguProfile', backref='cluster', lazy='dynamic')
    staff_assignments = db.relationship('UserScopeAssignment', backref='cluster', lazy='dynamic')

    def __repr__(self):
        return f'<LguCluster {self.name}>'


class LguProfile(db.Model):
    __tablename__ = 'lgu_profiles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    municipality = db.Column(db.String(200), nullable=False)
    province = db.Column(db.String(200), nullable=False, server_default='Laguna')
    cluster_id = db.Column(db.Integer, db.ForeignKey('lgu_clusters.id', ondelete='SET NULL'), nullable=True, index=True)
    mayor_name = db.Column(db.String(200), nullable=True)
    mayor_email = db.Column(db.String(255), nullable=True)
    contact_person = db.Column(db.String(200), nullable=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(50), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    projects = db.relationship('Project', backref='lgu', lazy='dynamic')
    magic_links = db.relationship('MagicLink', backref='lgu', lazy='dynamic')
    communication_logs = db.relationship('CommunicationLog', backref='lgu', lazy='dynamic')
    notice_recipients = db.relationship('NoticeRecipient', backref='lgu', lazy='dynamic')
    user_scope_assignments = db.relationship('UserScopeAssignment', backref='lgu', lazy='dynamic')

    def __repr__(self):
        return f'<LguProfile {self.name}>'


class UserScopeAssignment(db.Model):
    __tablename__ = 'user_scope_assignments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    scope_type = db.Column(db.String(20), nullable=False, default='cluster', server_default='cluster', index=True)
    cluster_id = db.Column(db.Integer, db.ForeignKey('lgu_clusters.id', ondelete='CASCADE'), nullable=True, index=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=True, index=True)
    assigned_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())

    user = db.relationship('User', backref='lgu_assignments')

    __table_args__ = (
        db.CheckConstraint(
            "scope_type IN ('cluster', 'lgu')",
            name='ck_user_scope_type',
        ),
        db.CheckConstraint(
            "((scope_type = 'cluster' AND cluster_id IS NOT NULL AND lgu_id IS NULL) OR "
            "(scope_type = 'lgu' AND lgu_id IS NOT NULL AND cluster_id IS NULL))",
            name='ck_user_scope_target',
        ),
        db.UniqueConstraint('user_id', 'scope_type', 'cluster_id', name='uq_user_scope_cluster'),
        db.UniqueConstraint('user_id', 'scope_type', 'lgu_id', name='uq_user_scope_lgu'),
    )

    def __init__(self, *args, **kwargs):
        if 'scope_type' not in kwargs:
            kwargs['scope_type'] = 'lgu' if kwargs.get('lgu_id') is not None else 'cluster'
        super().__init__(*args, **kwargs)

    def __repr__(self):
        target = self.cluster_id if self.scope_type == 'cluster' else self.lgu_id
        return f'<UserScopeAssignment user={self.user_id} {self.scope_type}={target}>'


StaffLguAssignment = UserScopeAssignment
