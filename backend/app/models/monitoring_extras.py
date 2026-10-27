"""Phase 2A structured monitoring records.

These models back the Monthly Progress Report, Form 3 (Justification for
Project Delay), and Project Exception Report features described in
phase2a-plan.md. Each record is linked to a dedicated `ProjectRequirement`
row (tagged with the matching `document_category`) so that the existing
Phase 1 shared document workflow (`requirement_workflow_service`) drives
its Draft -> Submitted -> Under Verification -> Staff Approved -> Pending
Provincial Approval -> Approved lifecycle, including the Returned for
Revision -> Resubmitted branch. Evidence upload continues to go through
the existing `submission_service` / Evidence Intake pipeline; these models
only hold the structured business data.
"""
from app.extensions import db
from datetime import datetime, timezone


class MonthlyProgressReport(db.Model):
    """Monthly physical/financial progress record for a project.

    Reuses the same risk_level vocabulary as `ManagementActionReport`
    (none/minor/major/severe) for consistency across the monitoring domain.
    `variance_pct` and `risk_level` are always computed server-side by
    `monthly_progress_service` and must never be accepted directly from a
    client request.
    """
    __tablename__ = 'monthly_progress_reports'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    qaar_inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='SET NULL'), nullable=True, index=True)
    evidence_submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='SET NULL'), nullable=True)
    reporting_period = db.Column(db.String(7), nullable=False, index=True)
    assessment_date = db.Column(db.Date, nullable=True)
    self_reported_actual_pct = db.Column(db.Numeric(5, 2), nullable=True)
    target_to_date_pct = db.Column(db.Numeric(5, 2), nullable=True)
    has_data_discrepancy = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
    discrepancy_delta = db.Column(db.Numeric(5, 2), nullable=True)
    actual_to_date_pct = db.Column(db.Numeric(5, 2), nullable=True)
    variance_pct = db.Column(db.Numeric(6, 2), nullable=True)
    budget_utilization_pct = db.Column(db.Numeric(5, 2), nullable=True)
    financial_progress_amount = db.Column(db.Numeric(15, 2), nullable=True)
    risk_level = db.Column(db.String(20), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('project_id', 'reporting_period', name='uq_monthly_progress_project_period'),
        db.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('none', 'minor', 'major', 'severe')",
            name='ck_monthly_progress_risk_level',
        ),
        db.CheckConstraint(
            "target_to_date_pct IS NULL OR (target_to_date_pct >= 0 AND target_to_date_pct <= 100)",
            name='ck_monthly_progress_target_range',
        ),
        db.CheckConstraint(
            "actual_to_date_pct IS NULL OR (actual_to_date_pct >= 0 AND actual_to_date_pct <= 100)",
            name='ck_monthly_progress_actual_range',
        ),
    )

    project = db.relationship('Project', backref=db.backref('monthly_progress_reports', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('monthly_progress_report', uselist=False))
    qaar_inspection = db.relationship('QaarInspection', backref=db.backref('monthly_progress_reports', lazy='dynamic'))
    evidence_submission = db.relationship('Submission')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<MonthlyProgressReport prj={self.project_id} period={self.reporting_period}>'


class Form3Request(db.Model):
    """Form 3 - Justification for Project Delay.

    When its backing `ProjectRequirement.workflow_status` reaches
    `approved`, the covered `reporting_period` is treated by
    `monitoring_service.evaluate_monthly_monitoring_risk_trigger` as an
    approved exemption that suppresses automatic MAR escalation for that
    period.
    """
    __tablename__ = 'form3_requests'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    mov_submission_id = db.Column(db.Integer, db.ForeignKey('submissions.id', ondelete='SET NULL'), nullable=True)
    reporting_period = db.Column(db.String(7), nullable=False, index=True)
    delay_reason_category = db.Column(db.String(60), nullable=True)
    justification_text = db.Column(db.Text, nullable=True)
    requested_exemption_start = db.Column(db.Date, nullable=True)
    requested_exemption_end = db.Column(db.Date, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('project_id', 'reporting_period', name='uq_form3_request_project_period'),
        db.CheckConstraint(
            "delay_reason_category IS NULL OR delay_reason_category IN ("
            "'force_majeure', 'right_of_way', 'procurement_delay', 'weather', "
            "'funding_delay', 'design_change', 'other'"
            ")",
            name='ck_form3_delay_reason_category',
        ),
        db.CheckConstraint(
            "requested_exemption_start IS NULL OR requested_exemption_end IS NULL "
            "OR requested_exemption_end >= requested_exemption_start",
            name='ck_form3_exemption_date_order',
        ),
    )

    project = db.relationship('Project', backref=db.backref('form3_requests', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('form3_request', uselist=False))
    mov_submission = db.relationship('Submission')
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<Form3Request prj={self.project_id} period={self.reporting_period}>'


class ProjectExceptionReport(db.Model):
    """Project Exception Report - contextual documentation of unusual
    project conditions or deviations. Unlike Form 3, an approved exception
    report never suppresses risk tagging or MAR escalation; it is purely
    informational documentation of the project timeline.
    """
    __tablename__ = 'project_exception_reports'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    reporting_period = db.Column(db.String(7), nullable=False, index=True)
    exception_category = db.Column(db.String(60), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('project_id', 'reporting_period', name='uq_project_exception_project_period'),
        db.CheckConstraint(
            "exception_category IS NULL OR exception_category IN ("
            "'force_majeure', 'right_of_way', 'procurement_delay', 'weather', "
            "'funding_delay', 'design_change', 'scope_change', 'other'"
            ")",
            name='ck_exception_report_category',
        ),
    )

    project = db.relationship('Project', backref=db.backref('project_exception_reports', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('exception_report', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<ProjectExceptionReport prj={self.project_id} period={self.reporting_period}>'


class NonInfraMonitoringRecord(db.Model):
    """Non-Infrastructure Monitoring / APM Template submission.

    Covers the Non-Infra Monitoring Templates (PDMU Manual Implementation
    Stage: "Non-infrastructure projects - Accomplish the monitoring
    templates (Appendix 1-19), whichever is applicable") and the APM
    Template document type from the confirmed Phase 2B requirements.
    `template_type` determines which already-reserved document_category
    the backing `ProjectRequirement` uses: 'apm_template' maps to
    document_category='apm_template'; every other template_type maps to
    document_category='non_infra_monitoring_evidence'. Like Monthly
    Progress Report (Phase 2A), this record is project-type-agnostic at
    the data-model level and is not hard-gated by project_kind.
    """
    __tablename__ = 'non_infra_monitoring_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    template_type = db.Column(db.String(40), nullable=False)
    appendix_reference = db.Column(db.String(50), nullable=True)
    reporting_period = db.Column(db.String(7), nullable=True, index=True)
    items_verified_summary = db.Column(db.Text, nullable=True)
    specifications_met = db.Column(db.Boolean, nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "template_type IN ("
            "'apm_template', 'infrastructure_monitoring_template', "
            "'non_infrastructure_monitoring_template', 'other_monitoring_template'"
            ")",
            name='ck_non_infra_monitoring_template_type',
        ),
    )

    project = db.relationship('Project', backref=db.backref('non_infra_monitoring_records', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('non_infra_monitoring_record', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<NonInfraMonitoringRecord prj={self.project_id} type={self.template_type}>'


class BeneficiaryEvidenceRecord(db.Model):
    """Beneficiary tracking / delivery evidence for Non-Infrastructure projects.

    `evidence_type` covers the five Phase 2B evidence document types, each
    already reserved on the shared workflow's document_category CHECK
    constraint since Phase 1: Signed Distribution List, Acknowledgement
    Receipt, Beneficiary Tracking Record, Turnover Photos, Delivery
    Invoice. `document_category` on the backing ProjectRequirement is set
    to the same value as `evidence_type` (1:1 mapping), avoiding any new
    CHECK constraint changes.
    """
    __tablename__ = 'beneficiary_evidence_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    project_requirement_id = db.Column(
        db.Integer,
        db.ForeignKey('project_requirements.id', ondelete='CASCADE'),
        nullable=False,
        unique=True,
        index=True,
    )
    evidence_type = db.Column(db.String(40), nullable=False)
    appendix_reference = db.Column(db.String(50), nullable=True)
    beneficiary_count = db.Column(db.Integer, nullable=True)
    distribution_date = db.Column(db.Date, nullable=True)
    reference_number = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "evidence_type IN ("
            "'signed_distribution_list', 'acknowledgement_receipt', "
            "'beneficiary_tracking_record', 'turnover_photos', 'delivery_invoice'"
            ")",
            name='ck_beneficiary_evidence_type',
        ),
        db.CheckConstraint(
            "beneficiary_count IS NULL OR beneficiary_count >= 0",
            name='ck_beneficiary_evidence_count_non_negative',
        ),
    )

    project = db.relationship('Project', backref=db.backref('beneficiary_evidence_records', lazy='dynamic'))
    project_requirement = db.relationship('ProjectRequirement', backref=db.backref('beneficiary_evidence_record', uselist=False))
    creator = db.relationship('User', foreign_keys=[created_by])

    def __repr__(self):
        return f'<BeneficiaryEvidenceRecord prj={self.project_id} type={self.evidence_type}>'
