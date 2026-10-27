from datetime import datetime, timezone

from sqlalchemy.sql import expression

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class DocumentCheckerEvaluationDataset(db.Model):
    __tablename__ = 'document_checker_evaluation_datasets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    dataset_type = db.Column(db.String(40), nullable=False, default='synthetic', server_default='synthetic')
    version = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='draft', server_default='draft')
    dataset_metadata = db.Column('metadata', db.JSON, nullable=True, default=dict, server_default='{}')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint('name', 'version', name='uq_document_checker_dataset_name_version'),
        db.CheckConstraint(
            "dataset_type IN ('synthetic', 'demo', 'redacted_real', 'reviewer_adjudicated', 'holdout')",
            name='ck_document_checker_dataset_type',
        ),
        db.CheckConstraint(
            "status IN ('draft', 'active', 'locked', 'archived')",
            name='ck_document_checker_dataset_status',
        ),
    )

    creator = db.relationship('User', backref=db.backref('document_checker_evaluation_datasets', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerEvaluationDataset {self.name} {self.version}>'


class DocumentCheckerEvaluationCase(db.Model):
    __tablename__ = 'document_checker_evaluation_cases'

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_datasets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    document_file_id = db.Column(db.Integer, db.ForeignKey('document_files.id', ondelete='SET NULL'), nullable=True, index=True)
    case_key = db.Column(db.String(160), nullable=False)
    document_family = db.Column(db.String(80), nullable=False, index=True)
    requirement_id = db.Column(db.Integer, db.ForeignKey('requirements.id', ondelete='SET NULL'), nullable=True, index=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='SET NULL'), nullable=True, index=True)
    fiscal_year = db.Column(db.Integer, nullable=True, index=True)
    ground_truth = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    pii_redacted = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    label_source = db.Column(db.String(80), nullable=True)
    label_confidence = db.Column(db.String(20), nullable=True)
    case_metadata = db.Column('metadata', db.JSON, nullable=True, default=dict, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint('dataset_id', 'case_key', name='uq_document_checker_case_dataset_key'),
        db.CheckConstraint(
            "label_confidence IS NULL OR label_confidence IN ('low', 'medium', 'high')",
            name='ck_document_checker_case_label_confidence',
        ),
        db.CheckConstraint(
            'fiscal_year IS NULL OR (fiscal_year BETWEEN 2000 AND 2100)',
            name='ck_document_checker_case_fy_range',
        ),
    )

    dataset = db.relationship(
        'DocumentCheckerEvaluationDataset',
        backref=db.backref('cases', lazy='dynamic', cascade='all, delete-orphan'),
    )
    document_file = db.relationship('DocumentFile', backref=db.backref('checker_evaluation_cases', lazy='dynamic'))
    requirement = db.relationship('Requirement', backref=db.backref('checker_evaluation_cases', lazy='dynamic'))
    program = db.relationship('Program', backref=db.backref('checker_evaluation_cases', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerEvaluationCase {self.case_key}>'


class DocumentCheckerEvaluationRun(db.Model):
    __tablename__ = 'document_checker_evaluation_runs'

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_datasets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    run_name = db.Column(db.String(180), nullable=False)
    status = db.Column(db.String(40), nullable=False, default='queued', server_default='queued', index=True)
    checker_version = db.Column(db.String(80), nullable=True)
    rule_policy_version = db.Column(db.String(80), nullable=True)
    provider_config = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    reference_profile_snapshot = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    started_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    started_at = db.Column(db.DateTime, nullable=True, index=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    summary_metrics = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    run_metadata = db.Column('metadata', db.JSON, nullable=True, default=dict, server_default='{}')
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('queued', 'running', 'completed', 'completed_with_failures', 'failed', 'cancelled')",
            name='ck_document_checker_run_status',
        ),
    )

    dataset = db.relationship(
        'DocumentCheckerEvaluationDataset',
        backref=db.backref('runs', lazy='dynamic', cascade='all, delete-orphan'),
    )
    starter = db.relationship('User', backref=db.backref('document_checker_evaluation_runs', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerEvaluationRun {self.run_name} {self.status}>'


class DocumentCheckerEvaluationResult(db.Model):
    __tablename__ = 'document_checker_evaluation_results'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    case_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_cases.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    checker_result_id = db.Column(
        db.Integer,
        db.ForeignKey('document_compliance_results.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    expected_output = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    predicted_output = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    metric_breakdown = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    passed = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false(), index=True)
    failure_reasons = db.Column(db.JSON, nullable=True, default=list, server_default='[]')
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    __table_args__ = (
        db.UniqueConstraint('run_id', 'case_id', name='uq_document_checker_result_run_case'),
    )

    run = db.relationship(
        'DocumentCheckerEvaluationRun',
        backref=db.backref('results', lazy='dynamic', cascade='all, delete-orphan'),
    )
    case = db.relationship('DocumentCheckerEvaluationCase', backref=db.backref('results', lazy='dynamic', cascade='all, delete-orphan'))
    checker_result = db.relationship('DocumentComplianceResult', backref=db.backref('evaluation_results', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerEvaluationResult run={self.run_id} case={self.case_id} passed={self.passed}>'


class DocumentCheckerMetricSnapshot(db.Model):
    __tablename__ = 'document_checker_metric_snapshots'

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_datasets.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    run_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_runs.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    snapshot_type = db.Column(db.String(60), nullable=False, default='latest_run', server_default='latest_run')
    metrics = db.Column(db.JSON, nullable=True, default=dict, server_default='{}')
    gates = db.Column(db.JSON, nullable=True, default=list, server_default='[]')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)

    __table_args__ = (
        db.CheckConstraint(
            "snapshot_type IN ('latest_run', 'official_gate', 'trend_point', 'manual_baseline')",
            name='ck_document_checker_snapshot_type',
        ),
    )

    dataset = db.relationship(
        'DocumentCheckerEvaluationDataset',
        backref=db.backref('metric_snapshots', lazy='dynamic', cascade='all, delete-orphan'),
    )
    run = db.relationship('DocumentCheckerEvaluationRun', backref=db.backref('metric_snapshots', lazy='dynamic'))
    creator = db.relationship('User', backref=db.backref('document_checker_metric_snapshots', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerMetricSnapshot dataset={self.dataset_id} type={self.snapshot_type}>'


class DocumentCheckerReleasedReport(db.Model):
    __tablename__ = 'document_checker_released_reports'

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(
        db.Integer,
        db.ForeignKey('document_checker_evaluation_runs.id', ondelete='CASCADE'),
        nullable=False,
    )
    status = db.Column(db.String(40), nullable=False, default='released', server_default='released', index=True)
    report_version = db.Column(db.String(80), nullable=False, default='v1', server_default='v1')
    release_notes = db.Column(db.Text, nullable=True)
    release_metadata = db.Column('metadata', db.JSON, nullable=True, default=dict, server_default='{}')
    released_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    released_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow, index=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        db.UniqueConstraint('run_id', name='uq_document_checker_released_report_run'),
        db.CheckConstraint(
            "status IN ('released', 'revoked')",
            name='ck_document_checker_released_report_status',
        ),
    )

    run = db.relationship(
        'DocumentCheckerEvaluationRun',
        backref=db.backref('released_report', uselist=False),
    )
    releaser = db.relationship('User', backref=db.backref('document_checker_released_reports', lazy='dynamic'))

    def __repr__(self):
        return f'<DocumentCheckerReleasedReport run={self.run_id} status={self.status}>'
