from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class Program(db.Model):
    __tablename__ = 'programs'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, unique=True)
    code = db.Column(db.String(50), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=True)
    program_type = db.Column(db.String(50), nullable=False)
    funding_agency = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    project_custom_field_schema = db.Column(db.JSON, nullable=True, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "program_type IN ('infrastructure', 'non_infrastructure', 'hybrid')",
            name='ck_program_type'
        ),
    )

    phases = db.relationship('ProgramPhase', backref='program', lazy='dynamic', order_by='ProgramPhase.phase_order')
    cycles = db.relationship('ProgramCycle', backref='program', lazy='dynamic', order_by='ProgramCycle.fiscal_year.desc()')
    projects = db.relationship('Project', backref='program', lazy='dynamic')
    guidelines = db.relationship('ProgramGuideline', backref='program', lazy='dynamic')

    def __repr__(self):
        return f'<Program {self.code} - {self.name}>'


class ProgramCycle(db.Model):
    __tablename__ = 'program_cycles'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    cloned_from_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    fiscal_year = db.Column(db.Integer, nullable=False, index=True)
    cycle_code = db.Column(db.String(80), nullable=False)
    source_template_name = db.Column(db.String(200), nullable=True)
    import_profile = db.Column(db.JSON, nullable=True, server_default='{}')
    field_schema = db.Column(db.JSON, nullable=True, server_default='{}')
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('program_id', 'fiscal_year', 'cycle_code', name='uq_program_cycle_year_code'),
    )

    source_cycle = db.relationship('ProgramCycle', remote_side=[id], backref=db.backref('cloned_cycles', lazy='dynamic'))
    projects = db.relationship('Project', backref='program_cycle', lazy='dynamic')
    import_templates = db.relationship('ImportTemplate', backref='program_cycle', lazy='dynamic')
    import_batches = db.relationship('ImportBatch', backref='program_cycle', lazy='dynamic')

    def __repr__(self):
        return f'<ProgramCycle {self.cycle_code} FY{self.fiscal_year}>'


class ProgramPhase(db.Model):
    __tablename__ = 'program_phases'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    phase_order = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('program_id', 'phase_order', name='uq_program_phase_order'),
    )

    requirements = db.relationship('Requirement', backref='phase', lazy='dynamic', order_by='Requirement.sort_order')

    def __repr__(self):
        return f'<ProgramPhase {self.program_id}:{self.name}>'


class Requirement(db.Model):
    __tablename__ = 'requirements'

    id = db.Column(db.Integer, primary_key=True)
    phase_id = db.Column(db.Integer, db.ForeignKey('program_phases.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    created_from_mapping_decision_id = db.Column(db.Integer, db.ForeignKey('import_mapping_decisions.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    requirement_type = db.Column(db.String(50), nullable=False, server_default='document')
    document_category = db.Column(db.String(60), nullable=True)
    annex_reference = db.Column(db.String(50), nullable=True)
    sort_order = db.Column(db.Integer, nullable=False, server_default='0')
    has_sla = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    sla_days = db.Column(db.Integer, nullable=True)
    is_mandatory = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    custom_field_schema = db.Column(db.JSON, nullable=True, server_default='{}')
    applicable_project_kinds = db.Column(db.JSON, nullable=False, default=lambda: ['infrastructure'], server_default='["infrastructure"]')
    source_label = db.Column(db.String(500), nullable=True)
    source_sheet_name = db.Column(db.String(255), nullable=True)
    source_column = db.Column(db.String(10), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def is_applicable_to(self, project_kind: str) -> bool:
        if self.applicable_project_kinds is None:
            return True
        kinds = self.applicable_project_kinds
        if isinstance(kinds, str):
            kinds = [k.strip().lower() for k in kinds.split(',')]
        elif isinstance(kinds, (list, tuple, set)):
            kinds = [str(k).strip().lower() for k in kinds]
        if '*' in kinds or 'all' in kinds:
            return True
        return str(project_kind).strip().lower() in kinds

    __table_args__ = (
        db.CheckConstraint(
            "requirement_type IN ('document', 'certificate', 'resolution', 'financial', 'engineering', 'inspection', 'other')",
            name='ck_requirement_type'
        ),
        db.CheckConstraint(
            "document_category IS NULL OR document_category IN ("
            "'monthly_progress_report', 'form_3', 'form_3_mov', 'project_exception_report', "
            "'apm_template', 'non_infra_monitoring_evidence', 'signed_distribution_list', "
            "'acknowledgement_receipt', 'beneficiary_tracking_record', 'turnover_photos', "
            "'delivery_invoice', 'final_swa', 'final_inspection_report', "
            "'certificate_of_final_acceptance', 'final_sord', 'proof_of_return_of_funds'"
            ")",
            name='ck_requirement_document_category'
        ),
    )

    project_requirements = db.relationship('ProjectRequirement', backref='requirement', lazy='dynamic')
    program_cycle = db.relationship('ProgramCycle', backref=db.backref('requirements', lazy='dynamic'))
    mapping_decision = db.relationship('ImportMappingDecision', backref=db.backref('created_requirements', lazy='dynamic'))

    def __repr__(self):
        return f'<Requirement {self.name}>'
