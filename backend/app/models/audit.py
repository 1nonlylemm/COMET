from datetime import datetime, timezone
from app.extensions import db
from app.utils.hash_audit import build_audit_entry, verify_chain_integrity as verify_hash_chain_integrity
from sqlalchemy.sql import expression


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    entity_type = db.Column(db.String(100), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    old_value = db.Column(db.JSON, nullable=True)
    new_value = db.Column(db.JSON, nullable=True)
    record_hash = db.Column(db.String(64), nullable=False, unique=True, index=True)
    previous_hash = db.Column(db.String(64), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    @classmethod
    def create_chain_entry(cls, user_id, action, entity_type, entity_id, old_value=None, new_value=None, ip_address=None, user_agent=None):
        log = cls(**build_audit_entry(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address,
            user_agent=user_agent,
        ))
        db.session.add(log)
        return log

    @classmethod
    def verify_chain_integrity(cls):
        logs = cls.query.order_by(cls.id.asc()).all()
        is_valid, _ = verify_hash_chain_integrity(logs)
        return is_valid

    def __repr__(self):
        return f'<AuditLog {self.action} {self.entity_type}:{self.entity_id}>'


class AuditIntegrityIncident(db.Model):
    __tablename__ = 'audit_integrity_incidents'

    id = db.Column(db.Integer, primary_key=True)
    status = db.Column(db.String(30), nullable=False, server_default='open', index=True)
    broken_at_id = db.Column(db.Integer, db.ForeignKey('audit_logs.id', ondelete='SET NULL'), nullable=True, index=True)
    mismatch_type = db.Column(db.String(40), nullable=False, server_default='unknown')
    expected_hash = db.Column(db.String(64), nullable=True)
    actual_hash = db.Column(db.String(64), nullable=True)
    expected_previous_hash = db.Column(db.String(64), nullable=True)
    actual_previous_hash = db.Column(db.String(64), nullable=True)
    opened_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    opened_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    investigation_notes = db.Column(db.Text, nullable=True)
    resolution_type = db.Column(db.String(40), nullable=True)
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            status.in_(['open', 'resolved', 'rebaselined']),
            name='ck_audit_integrity_incident_status',
        ),
        db.CheckConstraint(
            mismatch_type.in_(['record_hash_mismatch', 'previous_hash_mismatch', 'unknown']),
            name='ck_audit_integrity_incident_mismatch_type',
        ),
        db.CheckConstraint(
            "resolution_type IS NULL OR resolution_type IN ('restored_original', 'restored_backup', 'rebaselined', 'false_alarm')",
            name='ck_audit_integrity_incident_resolution_type',
        ),
    )

    broken_entry = db.relationship('AuditLog', foreign_keys=[broken_at_id])
    opener = db.relationship('User', foreign_keys=[opened_by], backref='opened_audit_integrity_incidents')
    resolver = db.relationship('User', foreign_keys=[resolved_by], backref='resolved_audit_integrity_incidents')

    def __repr__(self):
        return f'<AuditIntegrityIncident {self.id} status={self.status}>'


class AuditIntegrityCheckpoint(db.Model):
    __tablename__ = 'audit_integrity_checkpoints'

    id = db.Column(db.Integer, primary_key=True)
    incident_id = db.Column(db.Integer, db.ForeignKey('audit_integrity_incidents.id', ondelete='CASCADE'), nullable=False, index=True)
    checkpoint_audit_log_id = db.Column(db.Integer, db.ForeignKey('audit_logs.id', ondelete='SET NULL'), nullable=True, index=True)
    checkpoint_hash = db.Column(db.String(64), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    incident = db.relationship('AuditIntegrityIncident', backref=db.backref('checkpoints', lazy='dynamic'))
    checkpoint_entry = db.relationship('AuditLog', foreign_keys=[checkpoint_audit_log_id])
    creator = db.relationship('User', foreign_keys=[created_by], backref='created_audit_integrity_checkpoints')

    def __repr__(self):
        return f'<AuditIntegrityCheckpoint {self.id} incident={self.incident_id}>'


class ChangeStatusRequest(db.Model):
    __tablename__ = 'change_status_requests'

    id = db.Column(db.Integer, primary_key=True)
    project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='CASCADE'), nullable=False, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    current_status = db.Column(db.String(30), nullable=False)
    requested_status = db.Column(db.String(30), nullable=False)
    justification = db.Column(db.Text, nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    review_decision = db.Column(db.String(20), nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, server_default='pending')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            status.in_(['pending', 'approved', 'rejected']),
            name='ck_change_request_status'
        ),
    )

    requester = db.relationship('User', backref='submitted_change_requests', foreign_keys=[requested_by])
    reviewer = db.relationship('User', backref='reviewed_change_requests', foreign_keys=[reviewed_by])

    def __repr__(self):
        return f'<ChangeStatusRequest {self.id} pr={self.project_requirement_id}>'


class GeneratedReport(db.Model):
    __tablename__ = 'generated_reports'

    id = db.Column(db.Integer, primary_key=True)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    report_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(500), nullable=False)
    parameters = db.Column(db.JSON, nullable=True)
    file_path = db.Column(db.String(1000), nullable=True)
    file_name = db.Column(db.String(500), nullable=True)
    file_format = db.Column(db.String(20), nullable=False, server_default='pdf')
    file_size_bytes = db.Column(db.BigInteger, nullable=True)
    is_archived = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            report_type.in_(['annex_l', 'compliance_summary', 'analytics', 'custom', 'submission_history']),
            name='ck_report_type'
        ),
        db.CheckConstraint(
            file_format.in_(['pdf', 'xlsx', 'csv', 'docx']),
            name='ck_report_format'
        ),
    )

    generator = db.relationship('User', backref='generated_reports')

    def __repr__(self):
        return f'<GeneratedReport {self.report_type}: {self.title}>'


class SystemConfig(db.Model):
    __tablename__ = 'system_configs'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(200), nullable=False, unique=True, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), nullable=False, server_default='string')
    description = db.Column(db.Text, nullable=True)
    is_encrypted = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            value_type.in_(['string', 'integer', 'boolean', 'json', 'secret']),
            name='ck_config_value_type'
        ),
    )

    updater = db.relationship('User', backref='updated_configs')

    def __repr__(self):
        return f'<SystemConfig {self.key}>'
