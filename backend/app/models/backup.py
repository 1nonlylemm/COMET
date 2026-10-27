from datetime import datetime, timezone

from app.extensions import db


class DbBackupRecord(db.Model):
    __tablename__ = 'db_backup_records'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False, index=True)
    stored_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    status = db.Column(db.String(32), nullable=False, default='completed', index=True)
    byte_size = db.Column(db.BigInteger, nullable=False, default=0)
    sha256_checksum = db.Column(db.String(64), nullable=True, index=True)
    trigger_type = db.Column(db.String(32), nullable=False, default='manual', index=True)
    storage_provider = db.Column(db.String(32), nullable=False, default='local')
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    duration_seconds = db.Column(db.Float, nullable=False, default=0.0)
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    stored_object = db.relationship('StoredObject', backref='db_backup_records')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'stored_object_id': self.stored_object_id,
            'status': self.status,
            'byte_size': self.byte_size,
            'sha256_checksum': self.sha256_checksum,
            'trigger_type': self.trigger_type,
            'storage_provider': self.storage_provider,
            'created_by_user_id': self.created_by_user_id,
            'created_by_name': f"{self.created_by.first_name} {self.created_by.last_name}".strip() if self.created_by else 'System / Scheduled',
            'duration_seconds': round(self.duration_seconds or 0.0, 2),
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f'<DbBackupRecord {self.id}:{self.filename} ({self.status})>'
