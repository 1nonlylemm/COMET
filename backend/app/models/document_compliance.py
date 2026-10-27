from app.extensions import db
from datetime import datetime, timezone


class DocumentReferenceProfile(db.Model):
    __tablename__ = 'document_reference_profiles'

    id = db.Column(db.Integer, primary_key=True)
    reference_uri = db.Column(db.String(700), nullable=False, index=True)
    reference_origin = db.Column(db.String(30), nullable=False)
    reference_type = db.Column(db.String(50), nullable=False)
    checker_reference_type = db.Column(db.String(50), nullable=False, server_default='guideline_basis')
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='SET NULL'), nullable=True, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    requirement_name = db.Column(db.String(300), nullable=True, index=True)
    requirement_type = db.Column(db.String(50), nullable=True)
    phase_name = db.Column(db.String(100), nullable=True)
    fiscal_year = db.Column(db.Integer, nullable=True, index=True)
    project_kind = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    effective_from = db.Column(db.Date, nullable=True)
    effective_to = db.Column(db.Date, nullable=True)
    profile_metadata = db.Column(db.JSON, nullable=True, server_default='{}')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint(
            "reference_origin IN ('guideline', 'template')",
            name='ck_doc_ref_profile_origin',
        ),
        db.CheckConstraint(
            "checker_reference_type IN ("
            "'official_template', 'accepted_sample', 'returned_sample', "
            "'guideline_basis', 'logo_letterhead_reference', 'validation_checklist'"
            ")",
            name='ck_doc_ref_profile_checker_type',
        ),
        db.CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'archived')",
            name='ck_doc_ref_profile_status',
        ),
        db.CheckConstraint(
            'fiscal_year IS NULL OR (fiscal_year BETWEEN 2000 AND 2100)',
            name='ck_doc_ref_profile_fy_range',
        ),
        db.Index('idx_doc_ref_profile_lookup', 'program_id', 'requirement_id', 'fiscal_year', 'status'),
        db.UniqueConstraint('reference_uri', name='uq_doc_ref_profile_reference_uri'),
    )

    program = db.relationship('Program', backref=db.backref('document_reference_profiles', lazy='dynamic'))
    program_cycle = db.relationship('ProgramCycle', backref=db.backref('document_reference_profiles', lazy='dynamic'))
    requirement = db.relationship('Requirement', backref=db.backref('document_reference_profiles', lazy='dynamic'))
    creator = db.relationship('User', backref=db.backref('document_reference_profiles', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentReferenceProfile {self.reference_uri} {self.status}>'


class DocumentComplianceResult(db.Model):
    __tablename__ = 'document_compliance_results'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='CASCADE'), nullable=False, index=True)
    document_file_id = db.Column(db.Integer, db.ForeignKey('document_files.id', ondelete='SET NULL'), nullable=True, index=True)
    project_requirement_id = db.Column(db.Integer, db.ForeignKey('project_requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    score = db.Column(db.Numeric(5, 2), nullable=False, server_default='0')
    status = db.Column(db.String(30), nullable=False)
    recommended_action = db.Column(db.String(40), nullable=False)
    reference_basis = db.Column(db.JSON, nullable=True, server_default='{}')
    findings = db.Column(db.JSON, nullable=True, server_default='[]')
    extracted_fields = db.Column(db.JSON, nullable=True, server_default='{}')
    score_details = db.Column(db.JSON, nullable=True, server_default='{}')
    suggested_return_notes = db.Column(db.Text, nullable=True)
    checker_version = db.Column(db.String(40), nullable=False, server_default='document_compliance_v1')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('ready_for_approval', 'review_required', 'likely_return', 'invalid_evidence', 'check_failed')",
            name='ck_doc_compliance_status',
        ),
        db.CheckConstraint(
            "recommended_action IN ('approve_ready', 'review_required', 'return_for_revision', 'manual_review')",
            name='ck_doc_compliance_recommended_action',
        ),
        db.CheckConstraint('score >= 0 AND score <= 100', name='ck_doc_compliance_score_range'),
    )

    submission = db.relationship(
        'Submission',
        backref=db.backref(
            'compliance_results',
            lazy='dynamic',
            order_by='DocumentComplianceResult.created_at.desc()',
        ),
    )
    document_file = db.relationship('DocumentFile', backref=db.backref('compliance_results', lazy='dynamic'))
    project_requirement = db.relationship(
        'ProjectRequirement',
        backref=db.backref('document_compliance_results', lazy='dynamic'),
    )
    creator = db.relationship('User', backref=db.backref('document_compliance_results', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentComplianceResult sub={self.submission_id} score={self.score}>'
