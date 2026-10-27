from datetime import date
from app.extensions import db
from app.models.calendar import HolidayCalendar

VERIFIED_HOLIDAYS = [
    # ── 2025 Holidays (Proclamation No. 727, s. 2024 & Subsequent Proclamations) ───────────
    # Regular Holidays (RA 9492 / Proc. 727 / Proc. 839 / Proc. 911)
    {"date": date(2025, 1, 1), "name": "New Year's Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 4, 1), "name": "Eid'l Fitr", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 839 / RA 9177", "is_provisional": False},
    {"date": date(2025, 4, 9), "name": "Araw ng Kagitingan", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 4, 17), "name": "Maundy Thursday", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 4, 18), "name": "Good Friday", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 5, 1), "name": "Labor Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 6, 6), "name": "Eid'l Adha", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 911 / RA 9849", "is_provisional": False},
    {"date": date(2025, 6, 12), "name": "Independence Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 8, 25), "name": "National Heroes Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 11, 30), "name": "Bonifacio Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 12, 25), "name": "Christmas Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 12, 30), "name": "Rizal Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    # Special Non-Working Days (Proc. 727, Proc. 878, RA 9256, RA 10966)
    {"date": date(2025, 1, 29), "name": "Chinese New Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727", "is_provisional": False},
    {"date": date(2025, 4, 19), "name": "Black Saturday", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727", "is_provisional": False},
    {"date": date(2025, 5, 12), "name": "National and Local Elections", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 878", "is_provisional": False},
    {"date": date(2025, 8, 21), "name": "Ninoy Aquino Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9256", "is_provisional": False},
    {"date": date(2025, 10, 31), "name": "All Saints' Day Eve", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727", "is_provisional": False},
    {"date": date(2025, 11, 1), "name": "All Saints' Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    {"date": date(2025, 12, 8), "name": "Feast of the Immaculate Conception", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 10966", "is_provisional": False},
    {"date": date(2025, 12, 24), "name": "Christmas Eve", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727", "is_provisional": False},
    {"date": date(2025, 12, 31), "name": "Last Day of the Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 727 / RA 9492", "is_provisional": False},
    # Special Working Day (Commemoration)
    {"date": date(2025, 2, 25), "name": "EDSA People Power Revolution Anniversary", "type": "special_working", "non_working": False, "scope": "national", "ref": "Proclamation No. 727", "is_provisional": False},
    # Laguna Provincial Holidays (Statutory RA 11144, RA 10940)
    {"date": date(2025, 6, 19), "name": "Araw ng Kapanganakan ni Dr. Jose P. Rizal", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 11144", "is_provisional": False},
    {"date": date(2025, 7, 28), "name": "Araw ng Laguna", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 10940", "is_provisional": False},

    # ── 2026 Holidays (Proclamation No. 1006, s. 2025 & Subsequent Proclamations) ──────────
    # Regular Holidays (RA 9492 / Proc. 1006 / Proc. 1189 / Proc. 1264)
    {"date": date(2026, 1, 1), "name": "New Year's Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 3, 20), "name": "Eid'l Fitr", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1189 / RA 9177", "is_provisional": False},
    {"date": date(2026, 4, 2), "name": "Maundy Thursday", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 4, 3), "name": "Good Friday", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 4, 9), "name": "Araw ng Kagitingan", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 5, 1), "name": "Labor Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 5, 27), "name": "Eid'l Adha", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1264 / RA 9849", "is_provisional": False},
    {"date": date(2026, 6, 12), "name": "Independence Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 8, 31), "name": "National Heroes Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 11, 30), "name": "Bonifacio Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 12, 25), "name": "Christmas Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 12, 30), "name": "Rizal Day", "type": "regular", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    # Special Non-Working Days (Proc. 1006, RA 9256, RA 10966)
    {"date": date(2026, 2, 17), "name": "Chinese New Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006", "is_provisional": False},
    {"date": date(2026, 4, 4), "name": "Black Saturday", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006", "is_provisional": False},
    {"date": date(2026, 8, 21), "name": "Ninoy Aquino Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9256", "is_provisional": False},
    {"date": date(2026, 11, 1), "name": "All Saints' Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    {"date": date(2026, 11, 2), "name": "All Souls' Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006", "is_provisional": False},
    {"date": date(2026, 12, 8), "name": "Feast of the Immaculate Conception", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 10966", "is_provisional": False},
    {"date": date(2026, 12, 24), "name": "Christmas Eve", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006", "is_provisional": False},
    {"date": date(2026, 12, 31), "name": "Last Day of the Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Proclamation No. 1006 / RA 9492", "is_provisional": False},
    # Special Working Day (Commemoration)
    {"date": date(2026, 2, 25), "name": "EDSA People Power Revolution Anniversary", "type": "special_working", "non_working": False, "scope": "national", "ref": "Proclamation No. 1006", "is_provisional": False},
    # Laguna Provincial Holidays (Statutory RA 11144, RA 10940)
    {"date": date(2026, 6, 19), "name": "Araw ng Kapanganakan ni Dr. Jose P. Rizal", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 11144", "is_provisional": False},
    {"date": date(2026, 7, 28), "name": "Araw ng Laguna", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 10940", "is_provisional": False},
    # Laguna LGU-Specific Special Non-Working Days (Official Presidential Proclamations)
    {"date": date(2026, 1, 15), "name": "San Pablo Coconut Festival", "type": "local_holiday", "non_working": True, "scope": "lgu", "lgu_id": 24, "ref": "Proclamation No. 1133", "is_provisional": False},
    {"date": date(2026, 2, 3), "name": "Biñan Liberation Day", "type": "local_holiday", "non_working": True, "scope": "lgu", "lgu_id": 3, "ref": "Proclamation No. 1144", "is_provisional": False},
    {"date": date(2026, 5, 7), "name": "San Pablo Charter Anniversary", "type": "local_holiday", "non_working": True, "scope": "lgu", "lgu_id": 24, "ref": "Proclamation No. 1134", "is_provisional": False},
    {"date": date(2026, 7, 10), "name": "Santa Rosa Cityhood Anniversary", "type": "local_holiday", "non_working": True, "scope": "lgu", "lgu_id": 27, "ref": "Proclamation No. 1329", "is_provisional": False},
    {"date": date(2026, 8, 4), "name": "Cabuyao Cityhood Anniversary", "type": "local_holiday", "non_working": True, "scope": "lgu", "lgu_id": 4, "ref": "Proclamation No. 1348", "is_provisional": False},

    # ── 2027 Baseline & Provisional Calendar (Official Proclamation Pending) ──────────────
    # Standing Statutory Fixed Dates (RA 9492, RA 9256, RA 10966, RA 11144, RA 10940)
    {"date": date(2027, 1, 1), "name": "New Year's Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 4, 9), "name": "Araw ng Kagitingan", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 5, 1), "name": "Labor Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 6, 12), "name": "Independence Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 6, 19), "name": "Araw ng Kapanganakan ni Dr. Jose P. Rizal", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 11144", "is_provisional": False},
    {"date": date(2027, 7, 28), "name": "Araw ng Laguna", "type": "local_holiday", "non_working": True, "scope": "provincial", "ref": "RA 10940", "is_provisional": False},
    {"date": date(2027, 8, 21), "name": "Ninoy Aquino Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "RA 9256", "is_provisional": False},
    {"date": date(2027, 8, 30), "name": "National Heroes Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 11, 1), "name": "All Saints' Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 11, 30), "name": "Bonifacio Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 12, 8), "name": "Feast of the Immaculate Conception", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "RA 10966", "is_provisional": False},
    {"date": date(2027, 12, 25), "name": "Christmas Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 12, 30), "name": "Rizal Day", "type": "regular", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    {"date": date(2027, 12, 31), "name": "Last Day of the Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "RA 9492", "is_provisional": False},
    # Provisional Annual Proclamation-Dependent Dates (Pending Official 2027 Proclamation)
    {"date": date(2027, 2, 6), "name": "Chinese New Year", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 2, 25), "name": "EDSA People Power Revolution Anniversary", "type": "special_working", "non_working": False, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 3, 25), "name": "Maundy Thursday", "type": "regular", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 3, 26), "name": "Good Friday", "type": "regular", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 3, 27), "name": "Black Saturday", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 11, 2), "name": "All Souls' Day", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
    {"date": date(2027, 12, 24), "name": "Christmas Eve", "type": "special_non_working", "non_working": True, "scope": "national", "ref": "Provisional / Pending 2027 Proclamation", "is_provisional": True},
]


def seed_verified_holidays(session=None):
    """Seed verified statutory Philippine holidays, Laguna Day, and verified local proclamations into holiday_calendar."""
    from app.services.working_day_service import clear_holiday_cache

    s = session or db.session

    # Remove unsupported records identified during audit (e.g. 2025-11-02 All Souls' Day unsupported by Proc. 727)
    s.query(HolidayCalendar).filter(
        HolidayCalendar.holiday_date == date(2025, 11, 2),
        HolidayCalendar.scope == 'national',
        HolidayCalendar.name.ilike('%All Souls%')
    ).delete(synchronize_session=False)

    seeded_count = 0
    for item in VERIFIED_HOLIDAYS:
        existing = s.query(HolidayCalendar).filter_by(
            holiday_date=item["date"],
            scope=item["scope"],
            lgu_id=item.get("lgu_id"),
        ).first()
        if existing:
            existing.name = item["name"]
            existing.holiday_type = item["type"]
            existing.is_non_working = item["non_working"]
            existing.source_reference = item["ref"]
            existing.is_provisional = item.get("is_provisional", False)
        else:
            rec = HolidayCalendar(
                holiday_date=item["date"],
                name=item["name"],
                holiday_type=item["type"],
                is_non_working=item["non_working"],
                scope=item["scope"],
                lgu_id=item.get("lgu_id"),
                source_reference=item["ref"],
                is_provisional=item.get("is_provisional", False),
            )
            s.add(rec)
            seeded_count += 1
    s.commit()
    clear_holiday_cache()
    return seeded_count
