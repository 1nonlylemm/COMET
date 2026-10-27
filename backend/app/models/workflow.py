"""Shared document workflow transition history.

This model backs the Phase 1 shared workflow state machine (Draft ->
Submitted -> Under Verification -> Staff Approved -> Pending Provincial
Approval -> Approved, with a Returned for Revision -> Resubmitted branch)
that is reused across every new document type (Monthly Progress Report,
Form 3, Form 3 MOV, Project Exception Report, APM Template, Non-Infra
Monitoring Evidence, Signed Distribution List, Acknowledgement Receipt,
Beneficiary Tracking Record, Turnover Photos, Delivery Invoice, Final SWA,
FIR, COFA, Final SORD, Proof of Return of Funds).

It intentionally does not duplicate the DMS submission/storage models; it
only records the workflow transition history for a `ProjectRequirement`.
"""
from app.extensions import db
from datetime import datetime, timezone


WORKFLOW_STATES = (
    'draft',
    'submitted',
    'under_verification',
    'staff_approved',
    'pending_provincial_approval',
    'approved',
    'returned_for_revision',
    'resubmitted',
)


class RequirementWorkflowTransition(db.Model):
    __tablename__ = 'requirement_workflow_transitions'

    id = db.Column(db.Integer, primary_key=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    from_status = db.Column(db.String(30), nullable=True)
    to_status = db.Column(db.String(30), nullable=False)
    action = db.Column(db.String(30), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.CheckConstraint(
            "to_status IN ("
            "'draft', 'submitted', 'under_verification', 'staff_approved', "
            "'pending_provincial_approval', 'approved', 'returned_for_revision', 'resubmitted'"
            ")",
            name='ck_workflow_transition_to_status',
        ),
        db.CheckConstraint(
            "action IN ("
            "'submit', 'verify', 'staff_approve', 'provincial_approve', "
            "'return_for_revision', 'resubmit'"
            ")",
            name='ck_workflow_transition_action',
        ),
    )

    actor = db.relationship('User', backref=db.backref('workflow_transitions', lazy='dynamic'))

    def __repr__(self):
        return f'<RequirementWorkflowTransition req={self.project_requirement_id} {self.from_status}->{self.to_status}>'


DEFICIENCY_CATEGORIES = (
    'missing_attachment',
    'missing_signature_notarization',
    'cross_document_inconsistency',
    'costing_dupa_defect',
    'missing_statutory_clearance',
    'program_specific_non_conformity',
    'financial_reconciliation_defect',
    'scan_quality_defect',
    'other_documented_defect',
)

DEFICIENCY_RESOLUTION_STATES = (
    'open',
    'resolved',
    'waived',
)


class RequirementDeficiency(db.Model):
    __tablename__ = 'requirement_deficiencies'

    id = db.Column(db.Integer, primary_key=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    submission_id = db.Column(
        db.Integer,
        db.ForeignKey('submissions.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    submission_version_id = db.Column(
        db.Integer,
        db.ForeignKey('submission_versions.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    resolved_submission_version_id = db.Column(
        db.Integer,
        db.ForeignKey('submission_versions.id', ondelete='SET NULL'),
        nullable=True,
    )

    category = db.Column(db.String(100), nullable=False)
    finding_observation = db.Column(db.Text, nullable=False)
    corrective_instruction = db.Column(db.Text, nullable=False)

    resolution_state = db.Column(db.String(20), nullable=False, server_default='open', index=True)
    resolution_notes = db.Column(db.Text, nullable=True)

    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    resolved_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        db.CheckConstraint(
            "category IN ("
            "'missing_attachment', 'missing_signature_notarization', "
            "'cross_document_inconsistency', 'costing_dupa_defect', "
            "'missing_statutory_clearance', 'program_specific_non_conformity', "
            "'financial_reconciliation_defect', 'scan_quality_defect', "
            "'other_documented_defect'"
            ")",
            name='ck_deficiency_category',
        ),
        db.CheckConstraint(
            "resolution_state IN ('open', 'resolved', 'waived')",
            name='ck_deficiency_resolution_state',
        ),
        db.Index('idx_deficiencies_state', 'project_requirement_id', 'resolution_state'),
        db.Index('idx_deficiencies_requirement', 'project_requirement_id'),
        db.Index('idx_deficiencies_submission', 'submission_id'),
        db.Index('idx_deficiencies_version', 'submission_version_id'),
    )

    project_requirement = db.relationship(
        'ProjectRequirement',
        backref=db.backref('deficiencies', lazy='dynamic', cascade='all, delete-orphan'),
    )
    submission = db.relationship('Submission', backref=db.backref('deficiencies', lazy='dynamic'))
    submission_version = db.relationship('SubmissionVersion', foreign_keys=[submission_version_id])
    resolved_submission_version = db.relationship('SubmissionVersion', foreign_keys=[resolved_submission_version_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_user_id])

    def __repr__(self):
        return f'<RequirementDeficiency id={self.id} req={self.project_requirement_id} cat={self.category} state={self.resolution_state}>'

