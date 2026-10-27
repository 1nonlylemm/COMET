from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class SlaDeadline(db.Model):
    __tablename__ = 'sla_deadlines'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='CASCADE'), nullable=True, index=True)
    deadline_type = db.Column(db.String(50), nullable=False)
    trigger_date = db.Column(db.DateTime, nullable=False)
    deadline_date = db.Column(db.DateTime, nullable=False, index=True)
    sla_working_days = db.Column(db.Integer, nullable=False)
    is_resolved = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    resolved_at = db.Column(db.DateTime, nullable=True)
    escalation_triggered = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            deadline_type.in_([
                'notice_of_eligibility_5day',
                'standard_15day',
                'custom_sla',
                'rectification_period'
            ]),
            name='ck_sla_deadline_type'
        ),
        db.Index('idx_sla_deadline_unresolved', 'deadline_date', 'is_resolved'),
    )

    def __repr__(self):
        return f'<SlaDeadline prj={self.project_id} type={self.deadline_type}>'


class EscalationNotice(db.Model):
    __tablename__ = 'escalation_notices'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    parent_notice_id = db.Column(db.Integer, db.ForeignKey('escalation_notices.id', ondelete='SET NULL'), nullable=True, index=True)
    trigger_sla_id = db.Column(db.Integer, db.ForeignKey('sla_deadlines.id', ondelete='SET NULL'), nullable=True, index=True)
    trigger_project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notice_type = db.Column(db.String(20), nullable=False, index=True)
    notice_number = db.Column(db.Integer, nullable=False, server_default='1')
    title = db.Column(db.String(500), nullable=False)
    body_text = db.Column(db.Text, nullable=True)
    ai_generated_text = db.Column(db.Text, nullable=True)
    final_text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    generated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime, nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            notice_type.in_(['annex_e', 'annex_m', 'annex_n', 'annex_o', 'annex_l', 'reminder_letter']),
            name='ck_notice_type'
        ),
        db.CheckConstraint(
            status.in_(['draft', 'reviewed', 'sent', 'acknowledged', 'expired']),
            name='ck_notice_status'
        ),
        db.UniqueConstraint('project_id', 'notice_type', 'notice_number', name='uq_notice_project_type_number'),
        db.Index(
            'uq_notice_trigger_sla_type',
            'trigger_sla_id',
            'notice_type',
            unique=True,
            postgresql_where=db.text('trigger_sla_id IS NOT NULL'),
            sqlite_where=db.text('trigger_sla_id IS NOT NULL'),
        ),
    )

    parent_notice = db.relationship('EscalationNotice', remote_side=[id], backref='child_notices')
    trigger_sla = db.relationship('SlaDeadline', backref='triggered_notices')
    trigger_requirement = db.relationship('ProjectRequirement', backref='escalation_notices')
    legal_findings = db.relationship('LegalFinding', backref='notice', lazy='dynamic')
    recipients = db.relationship('NoticeRecipient', backref='notice', lazy='dynamic')

    def __repr__(self):
        return f'<EscalationNotice prj={self.project_id} {self.notice_type} n{self.notice_number}>'


class LegalFinding(db.Model):
    __tablename__ = 'legal_findings'

    id = db.Column(db.Integer, primary_key=True)
    notice_id = db.Column(db.Integer, db.ForeignKey('escalation_notices.id', ondelete='CASCADE'), nullable=False, index=True)
    qaar_inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='SET NULL'), nullable=True, index=True)
    informal_notes = db.Column(db.Text, nullable=True)
    formal_findings = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    agreements_timelines = db.Column(db.Text, nullable=True)
    ai_model_used = db.Column(db.String(100), nullable=True)
    ai_prompt_used = db.Column(db.Text, nullable=True)
    is_edited = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    qaar_inspection = db.relationship('QaarInspection', backref='legal_findings')

    def __repr__(self):
        return f'<LegalFinding notice={self.notice_id}>'


class NoticeRecipient(db.Model):
    __tablename__ = 'notice_recipients'

    id = db.Column(db.Integer, primary_key=True)
    notice_id = db.Column(db.Integer, db.ForeignKey('escalation_notices.id', ondelete='CASCADE'), nullable=False, index=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_name = db.Column(db.String(200), nullable=False)
    recipient_email = db.Column(db.String(255), nullable=True)
    recipient_role = db.Column(db.String(100), nullable=True)
    delivery_method = db.Column(db.String(50), nullable=False, server_default='pending_dispatch')
    delivery_status = db.Column(db.String(30), nullable=False, server_default='pending')
    sent_at = db.Column(db.DateTime, nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            delivery_method.in_(['pending_dispatch', 'email', 'physical_mail', 'magic_link', 'field_officer', 'dms', 'intranet', 'manual_print']),
            name='ck_delivery_method'
        ),
        db.CheckConstraint(
            delivery_status.in_(['pending', 'sent', 'delivered', 'acknowledged', 'failed']),
            name='ck_delivery_status'
        ),
    )

    def __repr__(self):
        return f'<NoticeRecipient notice={self.notice_id} lgu={self.lgu_id}>'
