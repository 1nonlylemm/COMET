from datetime import datetime, timezone
from app.extensions import db


class HolidayCalendar(db.Model):
    __tablename__ = 'holiday_calendar'

    id = db.Column(db.Integer, primary_key=True)
    holiday_date = db.Column(db.Date, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    holiday_type = db.Column(db.String(30), nullable=False)  # regular, special_non_working, special_working, suspension, local_holiday
    is_non_working = db.Column(db.Boolean, nullable=False, default=True)
    scope = db.Column(db.String(20), nullable=False, default='national')  # national, provincial, lgu
    lgu_id = db.Column(db.Integer, db.ForeignKey('lgu_profiles.id', ondelete='CASCADE'), nullable=True, index=True)
    source_reference = db.Column(db.String(100), nullable=True)  # e.g., 'RA 9492', 'Proclamation No. 727', 'RA 10940'
    is_provisional = db.Column(db.Boolean, nullable=False, default=False, server_default='false')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    lgu = db.relationship('LguProfile', backref=db.backref('holiday_exceptions', lazy='dynamic', cascade='all, delete-orphan'))

    __table_args__ = (
        db.UniqueConstraint('holiday_date', 'scope', 'lgu_id', name='uq_holiday_date_scope_lgu'),
        db.Index('idx_holiday_calendar_lookup', 'holiday_date', 'scope', 'is_non_working'),
    )

    def __repr__(self):
        return f'<HolidayCalendar date={self.holiday_date} name={self.name} non_working={self.is_non_working} scope={self.scope} provisional={self.is_provisional}>'
