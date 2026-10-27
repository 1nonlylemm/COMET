"""Legacy beneficiary models.

These models (`BeneficiaryCategory`, `BeneficiaryRecord`) are legacy and are
retained only for backward compatibility and existing demo seed data
(see `seed.py` / `seed_demo.py`). They are not used by any current COMET
workflow, service, or API route -- there is no service layer or endpoint
that reads or writes them.

Current beneficiary tracking functionality (Signed Distribution List,
Acknowledgement Receipt, Beneficiary Tracking Record, Turnover Photos,
Delivery Invoice) uses `BeneficiaryEvidenceRecord` in
`app/models/monitoring_extras.py`, which is wired into the shared
Phase 1 document workflow, notifications, and audit logging.

New development should use `BeneficiaryEvidenceRecord` and should not
extend these legacy models.
"""
from app.extensions import db
from datetime import datetime, timezone
from sqlalchemy.sql import expression


class BeneficiaryCategory(db.Model):
    __tablename__ = 'beneficiary_categories'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), nullable=False, unique=True)
    name = db.Column(db.String(200), nullable=False)
    mt_level = db.Column(db.String(10), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default=expression.true())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.CheckConstraint(
            mt_level.in_(['MT1', 'MT2', 'MT3', 'MT4']),
            name='ck_beneficiary_mt_level'
        ),
    )

    records = db.relationship('BeneficiaryRecord', backref='category', lazy='dynamic')

    def __repr__(self):
        return f'<BeneficiaryCategory {self.code} - {self.name}>'


class BeneficiaryRecord(db.Model):
    __tablename__ = 'beneficiary_records'

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('beneficiary_categories.id', ondelete='CASCADE'), nullable=False, index=True)
    beneficiary_name = db.Column(db.String(300), nullable=True)
    assistance_type = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=True)
    date_distributed = db.Column(db.Date, nullable=True)
    receipt_number = db.Column(db.String(100), nullable=True)
    is_verified = db.Column(db.Boolean, nullable=False, default=False, server_default=expression.false())
    verified_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    verifier = db.relationship('User', backref='verified_beneficiaries')

    def __repr__(self):
        return f'<BeneficiaryRecord prj={self.project_id} cat={self.category_id}>'
