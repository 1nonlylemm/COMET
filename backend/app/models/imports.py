from datetime import datetime, timezone

from sqlalchemy.sql import expression

from app.extensions import db


class ImportTemplate(db.Model):
    __tablename__ = 'import_templates'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='CASCADE'), nullable=True, index=True)
    cloned_from_template_id = db.Column(db.Integer, db.ForeignKey('import_templates.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(200), nullable=False)
    file_type = db.Column(db.String(20), nullable=False)
    version_number = db.Column(db.Integer, nullable=False, server_default='1')
    status = db.Column(db.String(30), nullable=False, server_default='draft')
    schema_signature = db.Column(db.String(128), nullable=True, index=True)
    sheet_mappings = db.Column(db.JSON, nullable=False, server_default='{}')
    column_mappings = db.Column(db.JSON, nullable=False, server_default='{}')
    transform_rules = db.Column(db.JSON, nullable=True, server_default='{}')
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    locked_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "file_type IN ('csv', 'xlsx', 'xls')",
            name='ck_import_template_file_type',
        ),
        db.CheckConstraint(
            "status IN ('draft', 'active', 'superseded', 'archived')",
            name='ck_import_template_status',
        ),
    )

    program = db.relationship('Program', backref=db.backref('import_templates', lazy='dynamic'))
    source_template = db.relationship('ImportTemplate', remote_side=[id], backref=db.backref('cloned_templates', lazy='dynamic'))
    creator = db.relationship('User', backref=db.backref('import_templates', lazy='dynamic'))
    import_batches = db.relationship('ImportBatch', backref='import_template', lazy='dynamic')

    def __repr__(self):
        return f'<ImportTemplate {self.name} v{self.version_number}>'


class ImportBatch(db.Model):
    __tablename__ = 'import_batches'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    import_template_id = db.Column(db.Integer, db.ForeignKey('import_templates.id', ondelete='SET NULL'), nullable=True, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    original_file_name = db.Column(db.String(255), nullable=False)
    stored_file_path = db.Column(db.String(500), nullable=False)
    stored_object_id = db.Column(db.Integer, db.ForeignKey('stored_objects.id', ondelete='SET NULL'), nullable=True, index=True)
    file_hash = db.Column(db.String(128), nullable=False, index=True)
    file_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(30), nullable=False, server_default='profiled')
    workbook_profile = db.Column(db.JSON, nullable=True, server_default='{}')
    mapping_preview = db.Column(db.JSON, nullable=True, server_default='{}')
    preview_summary = db.Column(db.JSON, nullable=True, server_default='{}')
    committed_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "file_type IN ('csv', 'xlsx', 'xls')",
            name='ck_import_batch_file_type',
        ),
        db.CheckConstraint(
            "status IN ('uploaded', 'profiled', 'mapped', 'previewed', 'committed', 'failed', 'cancelled')",
            name='ck_import_batch_status',
        ),
    )

    program = db.relationship('Program', backref=db.backref('import_batches', lazy='dynamic'))
    uploader = db.relationship('User', backref=db.backref('import_batches', lazy='dynamic'))
    stored_object = db.relationship('StoredObject')
    rows = db.relationship('ImportRow', backref='import_batch', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ImportBatch {self.id} {self.original_file_name}>'


class ImportRow(db.Model):
    __tablename__ = 'import_rows'

    id = db.Column(db.Integer, primary_key=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    sheet_name = db.Column(db.String(255), nullable=False)
    row_number = db.Column(db.Integer, nullable=False)
    row_key = db.Column(db.String(255), nullable=True, index=True)
    raw_data = db.Column(db.JSON, nullable=False, server_default='{}')
    mapped_data = db.Column(db.JSON, nullable=True, server_default='{}')
    validation_errors = db.Column(db.JSON, nullable=True, server_default='[]')
    action = db.Column(db.String(30), nullable=True)
    committed_entity_type = db.Column(db.String(50), nullable=True)
    committed_entity_id = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('import_batch_id', 'sheet_name', 'row_number', name='uq_import_row_batch_sheet_row'),
        db.CheckConstraint(
            "action IS NULL OR action IN ('create_project', 'update_project', 'skip', 'error')",
            name='ck_import_row_action',
        ),
    )

    def __repr__(self):
        return f'<ImportRow batch={self.import_batch_id} {self.sheet_name}!{self.row_number}>'


class ImportMappingDecision(db.Model):
    __tablename__ = 'import_mapping_decisions'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='SET NULL'), nullable=True, index=True)
    import_template_id = db.Column(db.Integer, db.ForeignKey('import_templates.id', ondelete='SET NULL'), nullable=True, index=True)
    created_from_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    source_sheet_name = db.Column(db.String(255), nullable=False)
    source_column = db.Column(db.String(10), nullable=False)
    source_header = db.Column(db.String(500), nullable=True)
    normalized_source_header = db.Column(db.String(500), nullable=True, index=True)
    column_fingerprint = db.Column(db.String(160), nullable=False, index=True)
    classification = db.Column(db.String(40), nullable=False, server_default='context')
    canonical_label = db.Column(db.String(500), nullable=True)
    target_field = db.Column(db.String(255), nullable=True)
    suggested_role = db.Column(db.String(80), nullable=True)
    binding_target = db.Column(db.String(255), nullable=True)
    binding_config = db.Column(db.JSON, nullable=True, server_default='{}')
    requirement_metadata = db.Column(db.JSON, nullable=True, server_default='{}')
    value_mapping_rules = db.Column(db.JSON, nullable=True, server_default='{}')
    trust_level = db.Column(db.String(30), nullable=False, server_default='confirmed')
    status = db.Column(db.String(30), nullable=False, server_default='active')
    version_number = db.Column(db.Integer, nullable=False, server_default='1')
    confirmed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "classification IN ('project_field', 'lgu_field', 'cycle_field', 'requirement', 'context', 'ignored', 'calculated')",
            name='ck_import_mapping_decision_classification',
        ),
        db.CheckConstraint(
            "trust_level IN ('suggested', 'confirmed')",
            name='ck_import_mapping_decision_trust_level',
        ),
        db.CheckConstraint(
            "status IN ('active', 'superseded', 'archived')",
            name='ck_import_mapping_decision_status',
        ),
    )

    program = db.relationship('Program', backref=db.backref('import_mapping_decisions', lazy='dynamic'))
    program_cycle = db.relationship('ProgramCycle', backref=db.backref('import_mapping_decisions', lazy='dynamic'))
    import_template = db.relationship('ImportTemplate', backref=db.backref('mapping_decisions', lazy='dynamic'))
    import_batch = db.relationship('ImportBatch', backref=db.backref('mapping_decisions', lazy='dynamic'))
    confirmer = db.relationship('User', backref=db.backref('confirmed_import_mapping_decisions', lazy='dynamic'))

    def __repr__(self):
        return f'<ImportMappingDecision {self.program_id}:{self.source_sheet_name}!{self.source_column}>'
