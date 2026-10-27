from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class QaarInspection(db.Model):
    __tablename__ = 'qaar_inspections'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    inspected_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    inspection_date = db.Column(db.Date, nullable=False, index=True)
    monitoring_type = db.Column(db.String(30), nullable=False, server_default='qaar')
    physical_accomplishment_pct = db.Column(db.Numeric(5, 2), nullable=True)
    observation_summary = db.Column(db.Text, nullable=True)
    findings = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    agreement_summary = db.Column(db.Text, nullable=True)
    issues_identified = db.Column(db.Text, nullable=True)
    is_site_visit = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    aide_memoire_text = db.Column(db.Text, nullable=True)
    annex_d_reference = db.Column(db.String(100), nullable=True)
    transmittal_status = db.Column(db.String(30), nullable=False, server_default='not_required')
    transmittal_reference = db.Column(db.String(120), nullable=True)
    transmitted_at = db.Column(db.DateTime, nullable=True)
    monthly_cycle_tag = db.Column(db.String(20), nullable=True)
    monthly_cycle_note = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            monitoring_type.in_(['qaar']),
            name='ck_qaar_monitoring_type'
        ),
        db.CheckConstraint(
            transmittal_status.in_(['not_required', 'pending', 'transmitted', 'acknowledged']),
            name='ck_qaar_transmittal_status'
        ),
        db.CheckConstraint(
            status.in_(['draft', 'submitted', 'reviewed', 'approved', 'flagged']),
            name='ck_qaar_status'
        ),
    )

    def __repr__(self):
        return f'<QaarInspection prj={self.project_id} date={self.inspection_date}>'


class QaarReportSummary(db.Model):
    __tablename__ = 'qaar_report_summaries'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, unique=True, index=True)
    office_address = db.Column(db.Text, nullable=True)
    program_name = db.Column(db.String(200), nullable=True)
    funded_year = db.Column(db.Integer, nullable=True)
    implementing_unit = db.Column(db.String(200), nullable=True)
    monitoring_office = db.Column(db.String(200), nullable=True)
    project_id_text = db.Column(db.String(120), nullable=True)
    project_title = db.Column(db.String(300), nullable=True)
    national_subsidy = db.Column(db.Numeric(15, 2), nullable=True)
    project_location = db.Column(db.Text, nullable=True)
    project_description = db.Column(db.Text, nullable=True)
    planned_accomplishment_pct = db.Column(db.Numeric(5, 2), nullable=True)
    actual_accomplishment_pct = db.Column(db.Numeric(5, 2), nullable=True)
    actual_project_status = db.Column(db.String(100), nullable=True)
    actual_completion_date = db.Column(db.Date, nullable=True)
    date_started = db.Column(db.Date, nullable=True)
    target_completion_date = db.Column(db.Date, nullable=True)
    lgu_counterpart = db.Column(db.Numeric(15, 2), nullable=True)
    liquidation = db.Column(db.Numeric(15, 2), nullable=True)
    contractor_name = db.Column(db.String(300), nullable=True)
    contractor_address = db.Column(db.Text, nullable=True)
    owner_name = db.Column(db.String(200), nullable=True)
    owner_contact_number = db.Column(db.String(80), nullable=True)
    pcab_license = db.Column(db.String(120), nullable=True)
    contract_amount = db.Column(db.Numeric(15, 2), nullable=True)
    prepared_by_name = db.Column(db.String(200), nullable=True)
    prepared_by_position = db.Column(db.String(200), nullable=True)
    form_data = db.Column(db.JSON, nullable=True, server_default='{}')
    autofill_snapshot = db.Column(db.JSON, nullable=True, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    inspection = db.relationship('QaarInspection', backref=db.backref('report_summary', uselist=False, cascade='all, delete-orphan'))


class QaarProjectManagementCheck(db.Model):
    __tablename__ = 'qaar_project_management_checks'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, index=True)
    check_key = db.Column(db.String(255), nullable=False)
    section = db.Column(db.String(120), nullable=True)
    label = db.Column(db.String(300), nullable=False)
    response = db.Column(db.String(300), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    form_data = db.Column(db.JSON, nullable=True, server_default='{}')
    source = db.Column(db.String(80), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('inspection_id', 'check_key', name='uq_qaar_pm_check_key'),
    )

    inspection = db.relationship('QaarInspection', backref=db.backref('project_management_checks', lazy='dynamic', cascade='all, delete-orphan'))


class QaarWorkItem(db.Model):
    __tablename__ = 'qaar_work_items'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, index=True)
    item_code = db.Column(db.String(80), nullable=True)
    description = db.Column(db.Text, nullable=True)
    quantity = db.Column(db.Numeric(15, 4), nullable=True)
    inspected_quantity = db.Column(db.Numeric(15, 4), nullable=True)
    unit = db.Column(db.String(50), nullable=True)
    unit_cost = db.Column(db.Numeric(15, 2), nullable=True)
    location = db.Column(db.Text, nullable=True)
    source_catalog_row = db.Column(db.Integer, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    inspection = db.relationship('QaarInspection', backref=db.backref('work_items', lazy='dynamic', cascade='all, delete-orphan'))


class QaarWorkFinding(db.Model):
    __tablename__ = 'qaar_work_findings'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, index=True)
    work_item_id = db.Column(db.Integer, db.ForeignKey('qaar_work_items.id', ondelete='SET NULL'), nullable=True, index=True)
    defect_code = db.Column(db.String(80), nullable=True)
    defect_description = db.Column(db.Text, nullable=True)
    quality_issue = db.Column(db.Text, nullable=True)
    recommendation = db.Column(db.Text, nullable=True)
    location = db.Column(db.Text, nullable=True)
    degree_of_defect = db.Column(db.String(40), nullable=True)
    rating_weight = db.Column(db.Numeric(8, 4), nullable=True)
    timeline = db.Column(db.String(200), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    source_catalog_row = db.Column(db.Integer, nullable=True)
    risk_level = db.Column(db.String(20), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "risk_level IS NULL OR risk_level IN ('minor', 'major', 'severe')",
            name='ck_qaar_work_finding_risk_level',
        ),
    )

    inspection = db.relationship('QaarInspection', backref=db.backref('work_findings', lazy='dynamic', cascade='all, delete-orphan'))
    work_item = db.relationship('QaarWorkItem', backref=db.backref('findings', lazy='dynamic'))


class QaarHealthSafetyCheck(db.Model):
    __tablename__ = 'qaar_health_safety_checks'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, index=True)
    check_key = db.Column(db.String(255), nullable=False)
    label = db.Column(db.String(300), nullable=False)
    response = db.Column(db.String(300), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('inspection_id', 'check_key', name='uq_qaar_health_safety_check_key'),
    )

    inspection = db.relationship('QaarInspection', backref=db.backref('health_safety_checks', lazy='dynamic', cascade='all, delete-orphan'))


class QaarGeneratedOutput(db.Model):
    __tablename__ = 'qaar_generated_outputs'

    id = db.Column(db.Integer, primary_key=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='CASCADE'), nullable=False, index=True)
    generated_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    output_type = db.Column(db.String(40), nullable=False)
    title = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    body_text = db.Column(db.Text, nullable=True)
    file_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    source_snapshot = db.Column(db.JSON, nullable=True, server_default='{}')
    generated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        db.CheckConstraint(
            "output_type IN ('report_summary', 'project_management', 'quality_of_works', 'health_and_safety', 'findings_recommendations', 'aide_memoire', 'notice_of_defects', 'full_package')",
            name='ck_qaar_generated_output_type',
        ),
        db.CheckConstraint(
            "status IN ('draft', 'generated', 'superseded', 'approved')",
            name='ck_qaar_generated_output_status',
        ),
    )

    inspection = db.relationship('QaarInspection', backref=db.backref('generated_outputs', lazy='dynamic', cascade='all, delete-orphan'))
    generator = db.relationship('User', backref='qaar_generated_outputs')


class SubaybayanVerification(db.Model):
    __tablename__ = 'subaybayan_verifications'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    cycle_month = db.Column(db.String(7), nullable=False, index=True)
    lgu_encoded_status = db.Column(db.String(40), nullable=False, server_default='not_checked')
    lgu_encoded_at = db.Column(db.DateTime, nullable=True)
    cmlgoo_verified_at = db.Column(db.DateTime, nullable=True)
    po_validated_at = db.Column(db.DateTime, nullable=True)
    ro_action_status = db.Column(db.String(40), nullable=False, server_default='pending')
    ro_action_at = db.Column(db.DateTime, nullable=True)
    discrepancy_notes = db.Column(db.Text, nullable=True)
    observations = db.Column(db.Text, nullable=True)
    evidence_links = db.Column(db.JSON, nullable=True, server_default='[]')
    status = db.Column(db.String(30), nullable=False, server_default='open')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('project_id', 'cycle_month', name='uq_subaybayan_verification_project_cycle'),
        db.CheckConstraint(
            "lgu_encoded_status IN ('not_checked', 'not_encoded', 'encoded', 'incomplete', 'returned_for_rectification')",
            name='ck_subay_lgu_encoded_status',
        ),
        db.CheckConstraint(
            "ro_action_status IN ('pending', 'approved', 'returned', 'not_required')",
            name='ck_subay_ro_action_status',
        ),
        db.CheckConstraint(
            "status IN ('open', 'verified', 'validated', 'returned', 'closed')",
            name='ck_subay_verification_status',
        ),
    )

    verifier = db.relationship('User', backref='subaybayan_verifications')


class ManagementActionReport(db.Model):
    __tablename__ = 'management_action_reports'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=True, index=True)
    inspection_id = db.Column(db.Integer, db.ForeignKey('qaar_inspections.id', ondelete='SET NULL'), nullable=True, index=True)
    verification_id = db.Column(db.Integer, db.ForeignKey('subaybayan_verifications.id', ondelete='SET NULL'), nullable=True, index=True)
    prepared_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    cycle_month = db.Column(db.String(7), nullable=False, index=True)
    risk_level = db.Column(db.String(20), nullable=False, server_default='minor')
    trigger_source = db.Column(db.String(40), nullable=False, server_default='manual')
    trigger_summary = db.Column(db.Text, nullable=True)
    action_required = db.Column(db.Text, nullable=True)
    responsible_office = db.Column(db.String(200), nullable=True)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    resolution_notes = db.Column(db.Text, nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    has_privilege_override = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "risk_level IN ('none', 'minor', 'major', 'severe')",
            name='ck_management_action_risk_level',
        ),
        db.CheckConstraint(
            "trigger_source IN ('manual', 'qaar', 'subaybayan', 'notice', 'monthly_monitoring')",
            name='ck_management_action_trigger_source',
        ),
        db.CheckConstraint(
            "status IN ('draft', 'for_review', 'submitted', 'acted', 'closed')",
            name='ck_management_action_status',
        ),
    )

    inspection = db.relationship('QaarInspection', backref=db.backref('management_actions', lazy='dynamic'))
    verification = db.relationship('SubaybayanVerification', backref=db.backref('management_actions', lazy='dynamic'))
    preparer = db.relationship('User', backref='management_action_reports')
