"""Phase 2C Completion Matrix structured records.

Backs the five closeout document types tracked by the expanded Completion
Matrix: Final Statement of Work Accomplished (Final SWA), Final Inspection
Report (FIR), Certificate of Final Acceptance (COFA), Final Statement of
Receipts and Disbursements (Final SORD), and Proof of Return of
Funds/Reversion. Each row is backed 1:1 by a dedicated `ProjectRequirement`
(tagged with the matching, already-reserved `document_category`) so the
existing Phase 1 shared document workflow (`requirement_workflow_service`)
drives its Draft -> Submitted -> Under Verification -> Staff Approved ->
Pending Provincial Approval -> Approved lifecycle exactly like the Phase 2A
and Phase 2B structured records. Evidence continues to go through the
existing `submission_service` / Evidence Intake pipeline -- this model only
holds the small amount of structured business data the Completion Matrix
needs (mainly the conditional/not-applicable state for Proof of Return of
Funds).

Verification/approval status for closeout is always derived from the
backing `ProjectRequirement.workflow_status` (`approved`), never from an
independent boolean flag, per the Phase 2C requirement that approved DMS
evidence -- not checkboxes -- is the proof of verification.

Final SWA applicability continues to be governed by the existing
`CompletionMilestone.is_final_swa_applicable` flag (computed from the
project's program type) rather than being duplicated here, per the
instruction to keep `CompletionMilestone` as the project-level aggregate.
FIR, COFA, and Final SORD are treated as required for every project that
has reached the completion phase, consistent with how Certificate of
Completion and Annex J are already treated as universally required in
`completion_service._assert_ready_for_final_approval`.

Proof of Return of Funds is the one document type in this set whose
applicability is genuinely ambiguous: the PDMU Manual and current COMET
requirements do not define a concrete, computable rule for when "unspent
funds" exist (e.g. based on `budget_amount` vs. actual disbursement, which
COMET does not currently track). Rather than inventing that rule, this
model exposes an explicit, human-confirmed `applicability` field that
defaults to `pending_confirmation` (treated as required/blocking for
closeout, the conservative default) until a Staff or Provincial Admin user
explicitly marks it `required` or `not_applicable` with a reason. This
keeps the applicability decision configurable and clearly flagged for
confirmation rather than automatically inferred.
"""
from app.extensions import db
from datetime import datetime, timezone


DOCUMENT_TYPES = (
    'final_swa',
    'final_inspection_report',
    'certificate_of_final_acceptance',
    'final_sord',
    'proof_of_return_of_funds',
)

# Only Proof of Return of Funds supports a genuine conditional/not-applicable
# state today; the other four document types are always required once a
# project reaches the completion phase (Final SWA's applicability is
# additionally gated by CompletionMilestone.is_final_swa_applicable at the
# service layer, not stored redundantly here).
APPLICABILITY_STATES = (
    'required',
    'pending_confirmation',
    'not_applicable',
)


class CompletionDocumentRecord(db.Model):
    """One Completion Matrix row for a single closeout document type."""
    __tablename__ = 'completion_document_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    document_type = db.Column(db.String(60), nullable=False, index=True)
    applicability = db.Column(db.String(30), nullable=False, server_default='required')
    applicability_reason = db.Column(db.Text, nullable=True)
    applicability_set_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    applicability_set_at = db.Column(db.DateTime, nullable=True)
    returned_amount = db.Column(db.Numeric(15, 2), nullable=True)
    receipt_number = db.Column(db.String(100), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "document_type IN ("
            "'final_swa', 'final_inspection_report', 'certificate_of_final_acceptance', "
            "'final_sord', 'proof_of_return_of_funds'"
            ")",
            name='ck_completion_document_type',
        ),
        db.CheckConstraint(
            "applicability IN ('required', 'pending_confirmation', 'not_applicable')",
            name='ck_completion_document_applicability',
        ),
        db.UniqueConstraint('project_id', 'document_type', name='uq_completion_document_project_type'),
    )

    project = db.relationship('Project', backref=db.backref('completion_document_records', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('completion_document_record', uselist=False))
    applicability_setter = db.relationship('User', foreign_keys=[applicability_set_by])
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<CompletionDocumentRecord prj={self.project_id} type={self.document_type}>'
