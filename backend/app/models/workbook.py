from datetime import datetime, timezone

from sqlalchemy.sql import expression

from app.extensions import db


class WorkbookWorkspace(db.Model):
    __tablename__ = 'workbook_workspaces'

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('programs.id', ondelete='CASCADE'), nullable=False, index=True)
    program_cycle_id = db.Column(db.Integer, db.ForeignKey('program_cycles.id', ondelete='CASCADE'), nullable=False, index=True)
    source_import_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    active_import_template_id = db.Column(db.Integer, db.ForeignKey('import_templates.id', ondelete='SET NULL'), nullable=True, index=True)
    name = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(30), nullable=False, server_default='active')
    schema_signature = db.Column(db.String(128), nullable=True, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name='ck_workbook_workspace_status',
        ),
        db.UniqueConstraint('program_cycle_id', 'name', name='uq_workbook_workspace_cycle_name'),
    )

    program = db.relationship('Program', backref=db.backref('workbook_workspaces', lazy='dynamic'))
    program_cycle = db.relationship('ProgramCycle', backref=db.backref('workbook_workspaces', lazy='dynamic'))
    source_import_batch = db.relationship('ImportBatch', foreign_keys=[source_import_batch_id])
    active_import_template = db.relationship('ImportTemplate', foreign_keys=[active_import_template_id])
    sheets = db.relationship(
        'WorkbookSheet',
        backref='workspace',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='WorkbookSheet.sheet_order',
    )

    def __repr__(self):
        return f'<WorkbookWorkspace {self.program_cycle_id}:{self.name}>'


class WorkbookSheet(db.Model):
    __tablename__ = 'workbook_sheets'

    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey('workbook_workspaces.id', ondelete='CASCADE'), nullable=False, index=True)
    source_sheet_name = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(255), nullable=False)
    sheet_type = db.Column(db.String(80), nullable=True, index=True)
    sheet_order = db.Column(db.Integer, nullable=False, server_default='0')
    max_row = db.Column(db.Integer, nullable=True)
    max_column = db.Column(db.Integer, nullable=True)
    merged_ranges = db.Column(db.JSON, nullable=True, server_default='[]')
    is_visible = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('workspace_id', 'source_sheet_name', name='uq_workbook_sheet_workspace_source'),
    )

    columns = db.relationship(
        'WorkbookColumn',
        backref='sheet',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='WorkbookColumn.column_index',
    )
    rows = db.relationship(
        'WorkbookRow',
        backref='sheet',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='WorkbookRow.source_row_number',
    )

    def __repr__(self):
        return f'<WorkbookSheet {self.source_sheet_name}>'


class WorkbookColumn(db.Model):
    __tablename__ = 'workbook_columns'

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('workbook_sheets.id', ondelete='CASCADE'), nullable=False, index=True)
    source_column = db.Column(db.String(10), nullable=False)
    column_index = db.Column(db.Integer, nullable=False)
    header_path = db.Column(db.JSON, nullable=True, server_default='[]')
    source_header = db.Column(db.String(500), nullable=True)
    display_label = db.Column(db.String(500), nullable=True)
    canonical_label = db.Column(db.String(500), nullable=True)
    normalized_header = db.Column(db.String(500), nullable=True, index=True)
    classification = db.Column(db.String(40), nullable=True, index=True)
    mapping_decision_id = db.Column(db.Integer, db.ForeignKey('import_mapping_decisions.id', ondelete='SET NULL'), nullable=True, index=True)
    data_type = db.Column(db.String(40), nullable=False, server_default='text')
    number_format = db.Column(db.String(120), nullable=True)
    validation_rules = db.Column(db.JSON, nullable=True, server_default='{}')
    validation_options = db.Column(db.JSON, nullable=True, server_default='[]')
    binding_target = db.Column(db.String(255), nullable=False, server_default='import_only')
    binding_config = db.Column(db.JSON, nullable=True, server_default='{}')
    is_editable = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    is_required = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    is_formula = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    formula_policy = db.Column(db.String(40), nullable=False, server_default='manual')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('sheet_id', 'source_column', name='uq_workbook_column_sheet_source'),
    )

    cells = db.relationship('WorkbookCell', backref='column', lazy='dynamic', cascade='all, delete-orphan')
    mapping_decision = db.relationship('ImportMappingDecision', backref=db.backref('workbook_columns', lazy='dynamic'))

    def __repr__(self):
        return f'<WorkbookColumn {self.sheet_id}:{self.source_column}>'


class WorkbookRow(db.Model):
    __tablename__ = 'workbook_rows'

    id = db.Column(db.Integer, primary_key=True)
    sheet_id = db.Column(db.Integer, db.ForeignKey('workbook_sheets.id', ondelete='CASCADE'), nullable=False, index=True)
    source_row_number = db.Column(db.Integer, nullable=False)
    source_row_key = db.Column(db.String(255), nullable=True, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True)
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='SET NULL'), nullable=True, index=True)
    row_state = db.Column(db.String(30), nullable=False, server_default='active')
    last_import_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "row_state IN ('active', 'skipped', 'conflict', 'archived')",
            name='ck_workbook_row_state',
        ),
        db.UniqueConstraint('sheet_id', 'source_row_number', name='uq_workbook_row_sheet_source_row'),
    )

    project = db.relationship('Project', backref=db.backref('workbook_rows', lazy='dynamic'))
    lgu = db.relationship('LguProfile', backref=db.backref('workbook_rows', lazy='dynamic'))
    cells = db.relationship('WorkbookCell', backref='row', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<WorkbookRow {self.sheet_id}:{self.source_row_number}>'


class WorkbookCell(db.Model):
    __tablename__ = 'workbook_cells'

    id = db.Column(db.Integer, primary_key=True)
    row_id = db.Column(db.Integer, db.ForeignKey('workbook_rows.id', ondelete='CASCADE'), nullable=False, index=True)
    column_id = db.Column(db.Integer, db.ForeignKey('workbook_columns.id', ondelete='CASCADE'), nullable=False, index=True)
    cell_ref = db.Column(db.String(20), nullable=False, index=True)
    raw_value = db.Column(db.JSON, nullable=True)
    typed_value = db.Column(db.JSON, nullable=True)
    display_value = db.Column(db.String(1000), nullable=True)
    formula = db.Column(db.Text, nullable=True)
    cached_formula_value = db.Column(db.JSON, nullable=True)
    source_value = db.Column(db.JSON, nullable=True)
    current_value = db.Column(db.JSON, nullable=True)
    value_type = db.Column(db.String(40), nullable=False, server_default='text')
    validation_state = db.Column(db.String(30), nullable=False, server_default='valid')
    validation_messages = db.Column(db.JSON, nullable=True, server_default='[]')
    is_dirty = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    last_edited_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    last_edited_at = db.Column(db.DateTime, nullable=True)
    last_import_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "validation_state IN ('valid', 'warning', 'error')",
            name='ck_workbook_cell_validation_state',
        ),
        db.UniqueConstraint('row_id', 'column_id', name='uq_workbook_cell_row_column'),
    )

    editor = db.relationship('User', foreign_keys=[last_edited_by])
    changes = db.relationship(
        'WorkbookCellChange',
        backref='cell',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='WorkbookCellChange.changed_at',
    )

    def __repr__(self):
        return f'<WorkbookCell {self.cell_ref}>'


class WorkbookCellChange(db.Model):
    __tablename__ = 'workbook_cell_changes'

    id = db.Column(db.Integer, primary_key=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('workbook_cells.id', ondelete='CASCADE'), nullable=False, index=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey('workbook_workspaces.id', ondelete='CASCADE'), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='SET NULL'), nullable=True, index=True)
    binding_target = db.Column(db.String(255), nullable=True)
    old_value = db.Column(db.JSON, nullable=True)
    new_value = db.Column(db.JSON, nullable=True)
    change_source = db.Column(db.String(50), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True)
    changed_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    reason = db.Column(db.Text, nullable=True)
    audit_log_id = db.Column(db.Integer, db.ForeignKey('audit_logs.id', ondelete='SET NULL'), nullable=True, index=True)

    workspace = db.relationship('WorkbookWorkspace', backref=db.backref('cell_changes', lazy='dynamic'))
    project = db.relationship('Project', backref=db.backref('workbook_cell_changes', lazy='dynamic'))
    actor = db.relationship('User', foreign_keys=[changed_by])

    def __repr__(self):
        return f'<WorkbookCellChange {self.cell_id}:{self.change_source}>'


class WorkbookConflict(db.Model):
    __tablename__ = 'workbook_conflicts'

    id = db.Column(db.Integer, primary_key=True)
    workspace_id = db.Column(db.Integer, db.ForeignKey('workbook_workspaces.id', ondelete='CASCADE'), nullable=False, index=True)
    cell_id = db.Column(db.Integer, db.ForeignKey('workbook_cells.id', ondelete='CASCADE'), nullable=False, index=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey('import_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    source_value = db.Column(db.JSON, nullable=True)
    current_value = db.Column(db.JSON, nullable=True)
    conflict_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(30), nullable=False, server_default='open')
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('open', 'keep_comet', 'accept_import', 'resolved', 'ignored')",
            name='ck_workbook_conflict_status',
        ),
    )

    workspace = db.relationship('WorkbookWorkspace', backref=db.backref('conflicts', lazy='dynamic'))
    cell = db.relationship('WorkbookCell', backref=db.backref('conflicts', lazy='dynamic'))
    import_batch = db.relationship('ImportBatch', backref=db.backref('workbook_conflicts', lazy='dynamic'))
    resolver = db.relationship('User', foreign_keys=[resolved_by])

    def __repr__(self):
        return f'<WorkbookConflict {self.cell_id}:{self.conflict_type}>'
