from app.extensions import db
from datetime import datetime, timezone
import uuid
from sqlalchemy.sql import expression


class Submission(db.Model):
    __tablename__ = 'submissions'

    id = db.Column(db.Integer, primary_key=True)
    project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    description = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(50), nullable=False, server_default='dms_ingestion')
    current_version = db.Column(db.Integer, nullable=False, server_default='1')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            source.in_(['dms_ingestion', 'direct_upload', 'field_upload', 'api_push']),
            name='ck_submission_source'
        ),
    )

    versions = db.relationship('SubmissionVersion', backref='submission', lazy='dynamic',
                               order_by='SubmissionVersion.version_number')
    document_files = db.relationship('DocumentFile', backref='submission', lazy='dynamic')
    nlp_results = db.relationship('NlpScanResult', backref='submission', lazy='dynamic')
    google_drive_pushes = db.relationship('GoogleDrivePush', backref='submission', lazy='dynamic')

    def __repr__(self):
        return f'<Submission {self.id} v{self.current_version}>'


class SubmissionVersion(db.Model):
    __tablename__ = 'submission_versions'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    version_number = db.Column(db.Integer, nullable=False)
    original_filename = db.Column(db.String(500), nullable=False)
    stored_filename = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    stored_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('submission_id', 'version_number', name='uq_submission_version'),
    )

    stored_object = db.relationship('StoredObject')

    def __repr__(self):
        return f'<SubmissionVersion sub={self.submission_id} v{self.version_number}>'


class DocumentFile(db.Model):
    __tablename__ = 'document_files'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    file_name = db.Column(db.String(500), nullable=False)
    file_path = db.Column(db.String(1000), nullable=False)
    stored_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    file_size_bytes = db.Column(db.BigInteger, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    file_hash_sha256 = db.Column(db.String(64), nullable=True)
    is_primary = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    stored_object = db.relationship('StoredObject')

    def __repr__(self):
        return f'<DocumentFile {self.file_name}>'


class NlpScanResult(db.Model):
    __tablename__ = 'nlp_scan_results'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Original AI Suggestion (Immutable ground truth)
    original_suggested_project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    suggested_requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id', ondelete='SET NULL'), nullable=True)
    suggested_project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    
    # Final human-reviewed decision
    final_project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    
    confidence_score = db.Column(db.Numeric(5, 4), nullable=True)
    extracted_text = db.Column(db.Text, nullable=True)
    matched_keywords = db.Column(db.JSON, nullable=True)
    classification_label = db.Column(db.String(200), nullable=True)
    
    # Review State
    is_accepted = db.Column(db.Boolean, nullable=True) # Retaining for backward compat if needed, but transitioning to review_state
    review_state = db.Column(db.String(50), nullable=False, server_default='pending') # pending, accepted_as_is, accepted_with_override, rejected
    rejection_reason = db.Column(db.String(50), nullable=True) # wrong_match, unreadable, duplicate, wrong_project, other
    
    is_seed_data = db.Column(db.Boolean, nullable=False, server_default='0')
    
    scan_metadata = db.Column(db.JSON, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    review_notes = db.Column(db.Text, nullable=True)
    scanned_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    suggested_requirement = db.relationship('Requirement', foreign_keys=[suggested_requirement_id], backref='nlp_suggestions')
    suggested_project_requirement = db.relationship('ProjectRequirement', foreign_keys=[suggested_project_requirement_id], backref='nlp_suggestions')
    original_suggested_project_requirement = db.relationship('ProjectRequirement', foreign_keys=[original_suggested_project_requirement_id])
    final_project_requirement = db.relationship('ProjectRequirement', foreign_keys=[final_project_requirement_id])
    reviewer = db.relationship('User', backref='reviewed_nlp_scan_results')

    def __repr__(self):
        return f'<NlpScanResult sub={self.submission_id} conf={self.confidence_score}>'
