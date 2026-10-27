from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class CompletionMilestone(db.Model):
    __tablename__ = 'completion_milestones'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    physical_completion_pct = db.Column(db.Numeric(5, 2), nullable=False, server_default='0')
    has_certificate_of_completion = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    is_final_swa_applicable = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    final_swa_applicability_reason = db.Column(db.Text, nullable=True)
    has_final_swa = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    has_annex_j = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    certificate_verified_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    swa_verified_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    annex_j_verified_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    certificate_verified_at = db.Column(db.DateTime, nullable=True)
    swa_verified_at = db.Column(db.DateTime, nullable=True)
    annex_j_verified_at = db.Column(db.DateTime, nullable=True)
    punchlist_items_total = db.Column(db.Integer, nullable=True)
    punchlist_items_resolved = db.Column(db.Integer, nullable=True)
    punchlist_notes = db.Column(db.Text, nullable=True)
    is_vault_ready = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    vault_locked_at = db.Column(db.DateTime, nullable=True)
    final_approval_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    final_approval_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    certificate_verifier = db.relationship('User', foreign_keys=[certificate_verified_by], backref='certificate_verified_completions')
    swa_verifier = db.relationship('User', foreign_keys=[swa_verified_by], backref='swa_verified_completions')
    annex_j_verifier = db.relationship('User', foreign_keys=[annex_j_verified_by], backref='annex_j_verified_completions')
    final_approver = db.relationship('User', foreign_keys=[final_approval_by], backref='approved_completions')

    def __repr__(self):
        return f'<CompletionMilestone prj={self.project_id} pct={self.physical_completion_pct}>'


class GoogleDrivePush(db.Model):
    __tablename__ = 'google_drive_pushes'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='SET NULL'), nullable=True, index=True)
    pushed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    drive_folder_id = db.Column(db.String(500), nullable=True)
    drive_folder_url = db.Column(db.String(1000), nullable=True)
    destination_path = db.Column(db.String(1000), nullable=True)
    files_count = db.Column(db.Integer, nullable=False, server_default='0')
    total_size_bytes = db.Column(db.BigInteger, nullable=True)
    push_status = db.Column(db.String(30), nullable=False, server_default='pending')
    error_message = db.Column(db.Text, nullable=True)
    api_response_metadata = db.Column(db.JSON, nullable=True)
    pushed_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            push_status.in_(['pending', 'in_progress', 'completed', 'failed']),
            name='ck_gdrive_push_status'
        ),
    )

    def __repr__(self):
        return f'<GoogleDrivePush prj={self.project_id} status={self.push_status}>'
