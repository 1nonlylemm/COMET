from datetime import datetime, timezone

from sqlalchemy.sql import expression

from app.extensions import db


class AiConversation(db.Model):
    __tablename__ = 'ai_conversations'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False, server_default='Assistant Conversation')
    status = db.Column(db.String(30), nullable=False, server_default='active')
    context = db.Column(db.JSON, nullable=True, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint("status IN ('active', 'archived')", name='ck_ai_conversation_status'),
    )

    user = db.relationship('User', backref=db.backref('ai_conversations', lazy='dynamic'))
    messages = db.relationship(
        'AiMessage',
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='AiMessage.created_at.asc()',
    )
    tool_calls = db.relationship(
        'AiToolCall',
        backref='conversation',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='AiToolCall.created_at.asc()',
    )

    def __repr__(self):
        return f'<AiConversation {self.id} user={self.user_id}>'


class AiMessage(db.Model):
    __tablename__ = 'ai_messages'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)
    response_type = db.Column(db.String(30), nullable=False, server_default='text')
    display_payload = db.Column(db.JSON, nullable=True, server_default='{}')
    ai_provider_used = db.Column(db.String(50), nullable=True)
    ai_model_used = db.Column(db.String(120), nullable=True)
    prompt_snapshot = db.Column(db.Text, nullable=True)
    attachment_stored_object_id = db.Column(
        db.Integer,
        db.ForeignKey('stored_objects.id', ondelete='SET NULL'),
        nullable=True,
    )
    attachment_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.CheckConstraint("role IN ('user', 'assistant', 'system', 'tool')", name='ck_ai_message_role'),
        db.CheckConstraint(
            "response_type IN ('text', 'tool_result', 'confirmation', 'error')",
            name='ck_ai_message_response_type',
        ),
    )

    user = db.relationship('User', backref=db.backref('ai_messages', lazy='dynamic'))

    def __repr__(self):
        return f'<AiMessage {self.id} role={self.role}>'


class AiToolCall(db.Model):
    __tablename__ = 'ai_tool_calls'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey('ai_conversations.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    message_id = db.Column(db.Integer, db.ForeignKey('ai_messages.id', ondelete='SET NULL'), nullable=True, index=True)
    requested_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    executed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    tool_name = db.Column(db.String(100), nullable=False, index=True)
    reason = db.Column(db.Text, nullable=True)
    risk_level = db.Column(db.String(20), nullable=False, server_default='low')
    requires_confirmation = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    status = db.Column(db.String(30), nullable=False, server_default='planned', index=True)
    input_data = db.Column(db.JSON, nullable=True, server_default='{}')
    output_data = db.Column(db.JSON, nullable=True, server_default='{}')
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    confirmed_at = db.Column(db.DateTime, nullable=True)
    executed_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.CheckConstraint("risk_level IN ('low', 'medium', 'high', 'critical')", name='ck_ai_tool_call_risk_level'),
        db.CheckConstraint(
            "status IN ('planned', 'pending_confirmation', 'completed', 'failed', 'cancelled')",
            name='ck_ai_tool_call_status',
        ),
    )

    assistant_message = db.relationship('AiMessage', backref=db.backref('tool_calls', lazy='dynamic'))
    requester = db.relationship('User', foreign_keys=[requested_by], backref='requested_ai_tool_calls')
    executor = db.relationship('User', foreign_keys=[executed_by], backref='executed_ai_tool_calls')

    def __repr__(self):
        return f'<AiToolCall {self.tool_name} status={self.status}>'


class AiGuardrailEvent(db.Model):
    __tablename__ = 'ai_guardrail_events'

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey('ai_conversations.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    message_id = db.Column(db.Integer, db.ForeignKey('ai_messages.id', ondelete='SET NULL'), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    decision = db.Column(db.String(30), nullable=False, index=True)
    category = db.Column(db.String(60), nullable=False, index=True)
    severity = db.Column(db.String(20), nullable=False, server_default='low')
    reason = db.Column(db.Text, nullable=True)
    matched_rules = db.Column(db.JSON, nullable=True, server_default='[]')
    prompt_preview = db.Column(db.String(500), nullable=True)
    prompt_hash = db.Column(db.String(64), nullable=True, index=True)
    provider_called = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    event_metadata = db.Column('metadata', db.JSON, nullable=True, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    conversation = db.relationship('AiConversation', backref=db.backref('guardrail_events', lazy='dynamic'))
    message = db.relationship('AiMessage', backref=db.backref('guardrail_events', lazy='dynamic'))
    user = db.relationship('User', backref=db.backref('ai_guardrail_events', lazy='dynamic'))

    def __repr__(self):
        return f'<AiGuardrailEvent {self.decision}:{self.category}>'
