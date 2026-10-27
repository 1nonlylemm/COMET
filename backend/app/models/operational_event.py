from datetime import datetime, timezone
from app.extensions import db


class SystemOperationalEvent(db.Model):
    __tablename__ = 'system_operational_events'

    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    severity = db.Column(db.String(20), nullable=False)
    component = db.Column(db.String(50), nullable=False)
    event_name = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(2000), nullable=False)
    request_id = db.Column(db.String(64), nullable=True, index=True)
    operation_id = db.Column(db.String(64), nullable=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    context_data = db.Column(db.JSON, nullable=True)
    traceback = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.Index('ix_operational_events_severity_timestamp', 'severity', 'timestamp'),
        db.Index('ix_operational_events_component_timestamp', 'component', 'timestamp'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'severity': self.severity,
            'component': self.component,
            'event_name': self.event_name,
            'message': self.message,
            'request_id': self.request_id,
            'operation_id': self.operation_id,
            'user_id': self.user_id,
            'context_data': self.context_data or {},
            'traceback': self.traceback,
        }

    def to_summary_dict(self):
        from app.logging_config import sanitize_text
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'severity': self.severity,
            'component': self.component,
            'event_name': self.event_name,
            'message': sanitize_text(self.message) if self.message else '',
            'request_id': self.request_id,
            'operation_id': self.operation_id,
            'user_id': self.user_id,
        }

    def to_detail_dict(self):
        from app.logging_config import redact_sensitive_data, sanitize_text, sanitize_traceback
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'severity': self.severity,
            'component': self.component,
            'event_name': self.event_name,
            'message': sanitize_text(self.message) if self.message else '',
            'request_id': self.request_id,
            'operation_id': self.operation_id,
            'user_id': self.user_id,
            'context_data': redact_sensitive_data(self.context_data or {}, max_depth=3) if isinstance(self.context_data, dict) else (self.context_data or {}),
            'traceback': sanitize_traceback(self.traceback) if self.traceback else None,
        }

    def __repr__(self):
        return f'<SystemOperationalEvent {self.id} [{self.severity}] {self.component}:{self.event_name}>'
