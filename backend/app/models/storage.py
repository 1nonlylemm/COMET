from datetime import datetime, timezone

from app.extensions import db


class StoredObject(db.Model):
    __tablename__ = 'stored_objects'

    id = db.Column(db.Integer, primary_key=True)
    storage_provider = db.Column(db.String(30), nullable=False, index=True)
    bucket_name = db.Column(db.String(255), nullable=True, index=True)
    object_key = db.Column(db.String(1000), nullable=False, index=True)
    original_filename = db.Column(db.String(500), nullable=True)
    content_type = db.Column(db.String(255), nullable=True)
    size_bytes = db.Column(db.BigInteger, nullable=True)
    sha256_hash = db.Column(db.String(64), nullable=True, index=True)
    etag = db.Column(db.String(255), nullable=True)
    source_module = db.Column(db.String(100), nullable=True, index=True)
    legacy_file_path = db.Column(db.String(1000), nullable=True)
    object_metadata = db.Column(db.JSON, nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    uploader = db.relationship('User', backref='stored_objects')

    def __repr__(self):
        return f'<StoredObject {self.storage_provider}:{self.object_key}>'
