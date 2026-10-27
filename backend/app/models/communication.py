from app.extensions import db
from datetime import datetime, timezone
import uuid
from sqlalchemy.sql import expression


class MagicLink(db.Model):
    __tablename__ = 'magic_links'

    id = db.Column(db.Integer, primary_key=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    notice_id = db.Column(db.Integer, db.ForeignKey('escalation_notices.id', ondelete='SET NULL'), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    intended_recipient_name = db.Column(db.String(200), nullable=True)
    intended_recipient_role = db.Column(db.String(100), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    is_used = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    used_at = db.Column(db.DateTime, nullable=True)
    access_count = db.Column(db.Integer, nullable=False, server_default='0')
    last_accessed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    notice = db.relationship(
        'EscalationNotice',
        backref=db.backref('magic_links', lazy='dynamic', order_by='MagicLink.created_at.desc()'),
        foreign_keys=[notice_id],
    )
    creator = db.relationship(
        'User',
        backref=db.backref('created_magic_links', lazy='dynamic'),
        foreign_keys=[created_by],
    )

    @classmethod
    def generate_token(cls):
        return uuid.uuid4().hex

    @property
    def is_expired(self):
        if self.expires_at is None:
            return True
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires_at

    def __repr__(self):
        return f'<MagicLink lgu={self.lgu_id} expired={self.is_expired}>'


class CommunicationLog(db.Model):
    __tablename__ = 'communication_logs'

    id = db.Column(db.Integer, primary_key=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    sent_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    communication_type = db.Column(db.String(50), nullable=False, index=True)
    channel = db.Column(db.String(50), nullable=False, server_default='email')
    subject = db.Column(db.String(500), nullable=True)
    body = db.Column(db.Text, nullable=True)
    recipient_email = db.Column(db.String(255), nullable=True)
    recipient_name = db.Column(db.String(200), nullable=True)
    recipient_destination = db.Column(db.String(255), nullable=True)
    recipient_office = db.Column(db.String(255), nullable=True)
    reference_no = db.Column(db.String(120), nullable=True)
    related_notice_id = db.Column(db.Integer, db.ForeignKey('escalation_notices.id', ondelete='SET NULL'), nullable=True)
    magic_link_id = db.Column(db.Integer, db.ForeignKey('magic_links.id', ondelete='SET NULL'), nullable=True)
    delivery_status = db.Column(db.String(30), nullable=False, server_default='pending')
    sent_at = db.Column(db.DateTime, nullable=True)
    posted_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            communication_type.in_([
                'escalation_notice', 'reminder', 'magic_link_dispatch', 'status_update', 'report'
            ]),
            name='ck_communication_type'
        ),
        db.CheckConstraint(
            delivery_status.in_(['pending', 'sent', 'delivered', 'failed', 'bounced']),
            name='ck_comm_delivery_status'
        ),
        db.CheckConstraint(
            channel.in_(['email', 'dms', 'intranet', 'manual_print', 'magic_link']),
            name='ck_communication_channel'
        ),
    )

    related_notice = db.relationship('EscalationNotice', backref='communications')
    magic_link = db.relationship('MagicLink', backref='communications')
    sender = db.relationship(
        'User',
        backref=db.backref('sent_communications', lazy='dynamic'),
        foreign_keys=[sent_by],
    )

    def __repr__(self):
        return f'<CommunicationLog {self.communication_type} lgu={self.lgu_id}>'


class WorkflowComment(db.Model):
    __tablename__ = 'workflow_comments'

    id = db.Column(db.Integer, primary_key=True)
    entity_type = db.Column(db.String(50), nullable=False, index=True)
    entity_id = db.Column(db.Integer, nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    visibility = db.Column(db.String(30), nullable=False, server_default='internal')
    comment_type = db.Column(db.String(50), nullable=False, server_default='comment')
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint(
            entity_type.in_([
                'project', 'project_requirement', 'sla_deadline',
                'qaar_inspection', 'escalation_notice'
            ]),
            name='ck_workflow_comment_entity_type',
        ),
        db.CheckConstraint(
            visibility.in_(['internal', 'field_visible', 'staff_only']),
            name='ck_workflow_comment_visibility',
        ),
        db.CheckConstraint(
            comment_type.in_([
                'comment', 'field_follow_up', 'submission_update',
                'clarification', 'acknowledgement', 'review_note'
            ]),
            name='ck_workflow_comment_type',
        ),
        db.Index('idx_workflow_comment_entity', 'entity_type', 'entity_id'),
    )

    project = db.relationship('Project', backref=db.backref('workflow_comments', lazy='dynamic'))
    project_requirement = db.relationship(
        'ProjectRequirement',
        backref=db.backref('workflow_comments', lazy='dynamic'),
    )
    lgu = db.relationship('LguProfile', backref=db.backref('workflow_comments', lazy='dynamic'))
    author = db.relationship(
        'User',
        backref=db.backref('workflow_comments', lazy='dynamic'),
        foreign_keys=[author_id],
    )

    def __repr__(self):
        return f'<WorkflowComment {self.entity_type}:{self.entity_id}>'


class ProgramGuideline(db.Model):
    __tablename__ = 'program_guidelines'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    title = db.Column(db.String(500), nullable=False)
    guideline_type = db.Column(db.String(50), nullable=False)
    reference_number = db.Column(db.String(100), nullable=True)
    issuing_body = db.Column(db.String(200), nullable=True)
    effective_date = db.Column(db.Date, nullable=True)
    is_current = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    file_path = db.Column(db.String(1000), nullable=True)
    file_name = db.Column(db.String(500), nullable=True)
    stored_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            guideline_type.in_(['memorandum', 'circular', 'annex', 'local_budget_circular', 'omnibus_guideline', 'other']),
            name='ck_guideline_type'
        ),
    )

    stored_object = db.relationship('StoredObject')

    def __repr__(self):
        return f'<ProgramGuideline {self.title}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    notification_type = db.Column(db.String(50), nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    message = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='normal', server_default='normal')
    action_url = db.Column(db.String(500), nullable=True)
    dedup_key = db.Column(db.String(255), nullable=True, unique=True, index=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    read_at = db.Column(db.DateTime, nullable=True)
    related_entity_type = db.Column(db.String(100), nullable=True)
    related_entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            notification_type.in_([
                'requirement_privilege_override', 'mar_privilege_override',
                'sla_warning', 'sla_breached', 'escalation_generated',
                'submission_received',
                'notice_pending_release', 'notice_pending_receipt', 'notice_follow_up_due',
                'workflow_document_submitted', 'workflow_document_returned',
                'workflow_staff_approved', 'workflow_pending_provincial_approval',
                'workflow_document_approved',
                'mar_generated', 'mar_submitted', 'mar_acted', 'mar_closed', 'project_reopened',
                'requirement_missing_reminder', 'submission_unreviewed_reminder',
                'revision_pending_reminder', 'resubmission_unreviewed_reminder',
                'provincial_approval_reminder',
                'security_alert',
                'compliance_breach',
            ]),
            name='ck_notification_type'
        ),
        db.CheckConstraint(
            priority.in_(['low', 'normal', 'high', 'critical']),
            name='ck_notification_priority'
        ),
    )

    deliveries = db.relationship(
        'NotificationDelivery',
        backref='notification',
        cascade='all, delete-orphan',
        lazy='dynamic',
    )

    def __repr__(self):
        return f'<Notification {self.notification_type} user={self.user_id} priority={self.priority}>'


class NotificationDelivery(db.Model):
    __tablename__ = 'notification_deliveries'

    id = db.Column(db.Integer, primary_key=True)
    notification_id = db.Column(
        db.Integer,
        db.ForeignKey('notifications.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    channel = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='pending', server_default='pending')
    attempted_at = db.Column(db.DateTime, nullable=True)
    sent_at = db.Column(db.DateTime, nullable=True)
    failed_at = db.Column(db.DateTime, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    provider_message_id = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.UniqueConstraint('notification_id', 'channel', name='uq_notification_delivery_channel'),
        db.CheckConstraint(channel.in_(['in_app', 'email']), name='ck_delivery_channel'),
        db.CheckConstraint(status.in_(['pending', 'sent', 'failed']), name='ck_delivery_status'),
    )

    def __repr__(self):
        return f'<NotificationDelivery notif={self.notification_id} {self.channel}:{self.status}>'


class UserNotificationPreference(db.Model):
    __tablename__ = 'user_notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    email_critical_alerts = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_deadline_reminders = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_review_reminders = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_workflow_notifications = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    email_daily_digest = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    in_app_critical_alerts = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    in_app_deadline_reminders = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    in_app_review_reminders = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    in_app_workflow_notifications = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f'<UserNotificationPreference user={self.user_id}>'

