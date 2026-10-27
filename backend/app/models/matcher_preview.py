from datetime import datetime, timezone

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MatcherPreviewJob(db.Model):
    __tablename__ = 'matcher_preview_jobs'

    id = db.Column(db.String(32), primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True)
    status = db.Column(db.String(16), nullable=False, default='queued', index=True)
    payload = db.Column(db.JSON, nullable=False)
    lease_token = db.Column(db.String(32), nullable=True)
    lease_expires_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
