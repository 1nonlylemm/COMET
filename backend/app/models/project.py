from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=False, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    project_name = db.Column(db.String(300), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False, index=True)
    source_project_code = db.Column(db.String(120), nullable=True, index=True)
    source_row_key = db.Column(db.String(255), nullable=True, index=True)
    source_sheet_name = db.Column(db.String(255), nullable=True)
    current_phase = db.Column(db.String(50), nullable=False, server_default='pre_implementation')
    overall_status = db.Column(db.String(50), nullable=False, server_default='not_yet_started')
    budget_amount = db.Column(db.Numeric(15, 2), nullable=True)
    target_start_date = db.Column(db.Date, nullable=True)
    target_end_date = db.Column(db.Date, nullable=True)
    actual_start_date = db.Column(db.Date, nullable=True)
    actual_end_date = db.Column(db.Date, nullable=True)
    physical_completion_pct = db.Column(db.Numeric(5, 2), nullable=True, server_default='0')
    project_kind = db.Column(db.String(50), nullable=True)
    monitoring_applicability = db.Column(db.String(50), nullable=True)
    qaar_category = db.Column(db.String(10), nullable=True)
    subaybayan_project_code = db.Column(db.String(120), nullable=True, index=True)
    subaybayan_url = db.Column(db.String(500), nullable=True)
    nadai_received_at = db.Column(db.Date, nullable=True)
    subaybayan_enrolled_at = db.Column(db.Date, nullable=True)
    subaybayan_enrollment_status = db.Column(db.String(40), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    custom_fields = db.Column(db.JSON, nullable=True, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "current_phase IN ('pre_implementation', 'implementation', 'completion')",
            name='ck_project_current_phase'
        ),
        db.CheckConstraint(
            "overall_status IN ('not_yet_started', 'ongoing', 'completed', 'cancelled')",
            name='ck_project_overall_status'
        ),
        db.CheckConstraint(
            "fiscal_year BETWEEN 2000 AND 2100",
            name='ck_project_fiscal_year_range'
        ),
        db.CheckConstraint(
            "budget_amount IS NULL OR budget_amount >= 0",
            name='ck_project_budget_non_negative'
        ),
        db.CheckConstraint(
            "physical_completion_pct IS NULL OR (physical_completion_pct >= 0 AND physical_completion_pct <= 100)",
            name='ck_project_completion_pct_range'
        ),
        db.CheckConstraint(
            "target_start_date IS NULL OR target_end_date IS NULL OR target_end_date >= target_start_date",
            name='ck_project_target_date_order'
        ),
        db.CheckConstraint(
            "actual_start_date IS NULL OR actual_end_date IS NULL OR actual_end_date >= actual_start_date",
            name='ck_project_actual_date_order'
        ),
        db.UniqueConstraint('program_cycle_id', 'source_project_code', name='uq_project_cycle_source_code'),
        db.Index(
            'uq_projects_source_code',
            db.text('lower(trim(source_project_code))'),
            unique=True,
            postgresql_where=db.text("source_project_code IS NOT NULL AND trim(source_project_code) <> ''"),
            sqlite_where=db.text("source_project_code IS NOT NULL AND trim(source_project_code) <> ''"),
        ),
        db.Index(
            'uq_projects_null_source_identity',
            'lgu_id',
            'fiscal_year',
            db.text('lower(trim(project_name))'),
            unique=True,
            postgresql_where=db.text('source_project_code IS NULL'),
            sqlite_where=db.text('source_project_code IS NULL'),
        ),
    )

    project_requirements = db.relationship('ProjectRequirement', backref='project', lazy='dynamic',
                                           order_by='ProjectRequirement.sort_order')
    sla_deadlines = db.relationship('SlaDeadline', backref='project', lazy='dynamic')
    escalation_notices = db.relationship('EscalationNotice', backref='project', lazy='dynamic')
    beneficiary_records = db.relationship('BeneficiaryRecord', backref='project', lazy='dynamic')
    qaar_inspections = db.relationship('QaarInspection', backref='project', lazy='dynamic')
    subaybayan_verifications = db.relationship('SubaybayanVerification', backref='project', lazy='dynamic')
    management_actions = db.relationship('ManagementActionReport', backref='project', lazy='dynamic')
    completion = db.relationship('CompletionMilestone', backref='project', uselist=False)
    google_drive_pushes = db.relationship('GoogleDrivePush', backref='project', lazy='dynamic')
    magic_links = db.relationship('MagicLink', backref='project', lazy='dynamic')
    phase_logs = db.relationship('ProjectPhaseLog', backref='project', lazy='dynamic',
                                  order_by='ProjectPhaseLog.transitioned_at')

    def __repr__(self):
        return f'<Project {self.project_name} (FY{self.fiscal_year})>'


class ProjectRequirement(db.Model):
    __tablename__ = 'project_requirements'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    requirement_name = db.Column(db.String(300), nullable=False)
    requirement_type = db.Column(db.String(50), nullable=False, server_default='document')
    document_category = db.Column(db.String(60), nullable=True, index=True)
    annex_reference = db.Column(db.String(50), nullable=True)
    is_mandatory = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    has_sla = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    sla_days = db.Column(db.Integer, nullable=True)
    phase_name = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(30), nullable=False, server_default='pending')
    workflow_status = db.Column(db.String(30), nullable=True, index=True)
    workflow_submitted_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    workflow_submitted_at = db.Column(db.DateTime, nullable=True)
    workflow_staff_reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    workflow_staff_approved_at = db.Column(db.DateTime, nullable=True)
    workflow_provincial_reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    workflow_approved_at = db.Column(db.DateTime, nullable=True)
    workflow_return_reason = db.Column(db.Text, nullable=True)
    workflow_returned_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    workflow_returned_at = db.Column(db.DateTime, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    waived_reason = db.Column(db.Text, nullable=True)
    applicability = db.Column(db.String(30), nullable=False, default='applicable', server_default='applicable')
    applicability_reason = db.Column(db.Text, nullable=True)
    applicability_set_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    applicability_set_at = db.Column(db.DateTime, nullable=True)
    custom_fields = db.Column(db.JSON, nullable=True, server_default='{}')
    last_action_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)
    has_privilege_override = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'under_review', 'compliant', 'non_compliant', 'waived')",
            name='ck_project_req_status'
        ),
        db.CheckConstraint(
            "requirement_type IN ('document', 'certificate', 'resolution', 'financial', 'engineering', 'inspection', 'other')",
            name='ck_project_req_type'
        ),
        db.CheckConstraint(
            "document_category IS NULL OR document_category IN ("
            "'monthly_progress_report', 'form_3', 'form_3_mov', 'project_exception_report', "
            "'apm_template', 'non_infra_monitoring_evidence', 'signed_distribution_list', "
            "'acknowledgement_receipt', 'beneficiary_tracking_record', 'turnover_photos', "
            "'delivery_invoice', 'final_swa', 'final_inspection_report', "
            "'certificate_of_final_acceptance', 'final_sord', 'proof_of_return_of_funds'"
            ")",
            name='ck_project_req_document_category'
        ),
        db.CheckConstraint(
            "workflow_status IS NULL OR workflow_status IN ("
            "'draft', 'submitted', 'under_verification', 'staff_approved', "
            "'pending_provincial_approval', 'approved', 'returned_for_revision', 'resubmitted'"
            ")",
            name='ck_project_req_workflow_status'
        ),
        db.CheckConstraint(
            "applicability IN ('applicable', 'not_applicable')",
            name='ck_project_req_applicability',
        ),
        db.Index('idx_project_req_project_status', 'project_id', 'status'),
        db.Index('idx_project_req_workflow_status', 'workflow_status'),
    )

    submissions = db.relationship('Submission', backref='project_requirement', lazy='dynamic')
    sla_deadlines = db.relationship('SlaDeadline', backref='project_requirement', lazy='dynamic')
    change_requests = db.relationship('ChangeStatusRequest', backref='project_requirement', lazy='dynamic')
    google_drive_pushes = db.relationship('GoogleDrivePush', backref='project_requirement', lazy='dynamic')
    last_action_user = db.relationship('User', backref='last_actions', foreign_keys=[last_action_by])
    workflow_submitted_by_user = db.relationship('User', foreign_keys=[workflow_submitted_by])
    workflow_staff_reviewer = db.relationship('User', foreign_keys=[workflow_staff_reviewer_id])
    workflow_provincial_reviewer = db.relationship('User', foreign_keys=[workflow_provincial_reviewer_id])
    workflow_returned_by_user = db.relationship('User', foreign_keys=[workflow_returned_by])
    applicability_setter = db.relationship('User', foreign_keys=[applicability_set_by])
    workflow_transitions = db.relationship(
        'RequirementWorkflowTransition',
        backref='project_requirement',
        lazy='dynamic',
        order_by='RequirementWorkflowTransition.created_at',
    )

    def __repr__(self):
        return f'<ProjectRequirement prj={self.project_id} "{self.requirement_name}" status={self.status}>'


class ProjectPhaseLog(db.Model):
    __tablename__ = 'project_phase_logs'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    from_phase = db.Column(db.String(50), nullable=False)
    to_phase = db.Column(db.String(50), nullable=False)
    transitioned_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    transitioned_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "from_phase IN ('pre_implementation', 'implementation', 'completion')",
            name='ck_phase_log_from'
        ),
        db.CheckConstraint(
            "to_phase IN ('pre_implementation', 'implementation', 'completion')",
            name='ck_phase_log_to'
        ),
    )

    transitioned_by_user = db.relationship('User', backref='phase_transitions')

    def __repr__(self):
        return f'<ProjectPhaseLog prj={self.project_id} {self.from_phase}→{self.to_phase}>'
