from app.extensions import db
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from sqlalchemy.sql import expression
from app.constants.roles import INTERNAL_USER_ROLES


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, server_default='staff')
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        server_default=expression.true(),
    )
    must_change_password = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    can_approve_technical_documents = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    can_close_management_actions = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    token_version = db.Column(
        db.Integer,
        nullable=False,
        default=1,
        server_default='1',
    )
    mfa_enabled = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=expression.false(),
    )
    mfa_secret = db.Column(db.String(255), nullable=True)
    mfa_type = db.Column(db.String(20), nullable=True, default='totp')
    last_mfa_verified_at = db.Column(db.DateTime, nullable=True)
    last_step_up_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(role.in_(INTERNAL_USER_ROLES), name='ck_user_role'),
    )

    submissions = db.relationship('Submission', backref='uploader', lazy='dynamic')
    qaar_inspections = db.relationship('QaarInspection', backref='inspector', lazy='dynamic')
    escalation_notices = db.relationship('EscalationNotice', foreign_keys='EscalationNotice.generated_by', backref=db.backref('generator', lazy='select'), lazy='dynamic')
    # ChangeStatusRequest relationships are defined on the model itself
    # (requester/reviewer with explicit foreign_keys) — no need to define them here
    audit_logs = db.relationship('AuditLog', backref='actor', lazy='dynamic')
    gdrive_pushes = db.relationship('GoogleDrivePush', foreign_keys='GoogleDrivePush.pushed_by', backref=db.backref('pusher', lazy='select'), lazy='dynamic')
    guidelines_uploaded = db.relationship('ProgramGuideline', foreign_keys='ProgramGuideline.uploaded_by', backref=db.backref('uploader', lazy='select'), lazy='dynamic')
    recovery_codes = db.relationship('MfaRecoveryCode', backref='user', cascade='all, delete-orphan', lazy='dynamic')
    notification_preference = db.relationship('UserNotificationPreference', backref='user', uselist=False, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def full_name(self):
        return f'{self.first_name} {self.last_name}'

    def __repr__(self):
        return f'<User {self.email} ({self.role})>'


class PasswordReset(db.Model):
    __tablename__ = 'password_resets'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    token = db.Column(db.String(255), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='password_resets')

    @classmethod
    def generate_token(cls):
        return str(uuid.uuid4())

    def __repr__(self):
        return f'<PasswordReset user_id={self.user_id}>'


class MfaRecoveryCode(db.Model):
    __tablename__ = 'mfa_recovery_codes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    code_hash = db.Column(db.String(64), nullable=False, index=True)
    used_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<MfaRecoveryCode user_id={self.user_id} used={bool(self.used_at)}>'
