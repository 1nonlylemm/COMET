from datetime import date, datetime

from app.services import qaar_reference


COMPUTED_REPORT_SUMMARY_KEYS = (
    'percent_slippage',
    'project_duration',
    'time_elapsed',
    'total_project_cost',
    'balance_of_contract',
)

REPORT_SUMMARY_FORMULA_REGISTRY = [
    {
        'key': 'percent_slippage',
        'label': '% SLIPPAGE :',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'F32',
        'dependencies': [
            'actual_project_status',
            'planned_accomplishment_pct',
            'actual_accomplishment_pct',
            'date_of_inspection_assessment',
            'date_started',
            'target_completion_date',
        ],
        'status': 'server_calculated',
    },
    {
        'key': 'project_duration',
        'label': 'PROJECT DURATION :',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'F36',
        'dependencies': ['date_started', 'target_completion_date'],
        'status': 'server_calculated',
    },
    {
        'key': 'time_elapsed',
        'label': 'TIME ELAPSED :',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'F37',
        'dependencies': [
            'actual_project_status',
            'date_started',
            'target_completion_date',
            'date_of_inspection_assessment',
            'actual_completion_date',
        ],
        'status': 'server_calculated',
    },
    {
        'key': 'total_project_cost',
        'label': 'TOTAL :',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'F40',
        'dependencies': ['national_subsidy', 'lgu_counterpart'],
        'status': 'server_calculated',
    },
    {
        'key': 'balance_of_contract',
        'label': 'BALANCE OF THE CONTRACT :',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'L40',
        'dependencies': ['contract_amount', 'liquidation'],
        'status': 'server_calculated',
    },
]

QUALITY_OF_WORKS_FORMULA_REGISTRY = [
    {
        'key': 'work_item_cost',
        'label': 'COST',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'L49:L58',
        'dependencies': ['quantity', 'inspected_quantity', 'unit_cost'],
        'status': 'server_calculated',
    },
    {
        'key': 'work_item_weight',
        'label': 'WEIGHT',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'M49:M58',
        'dependencies': ['work_item_cost', 'total_computed_cost'],
        'status': 'server_calculated',
    },
    {
        'key': 'rating_per_degree',
        'label': 'Rating per Degree of Defect',
        'source_sheet': 'RATINGS',
        'cell': 'lookup',
        'dependencies': ['degree_of_defect'],
        'status': 'server_calculated',
    },
    {
        'key': 'quality_issue_weight',
        'label': 'Quality Issue Weight',
        'source_sheet': 'RATINGS',
        'cell': 'lookup',
        'dependencies': ['quality_issue'],
        'status': 'server_calculated',
    },
    {
        'key': 'computed_total_rating',
        'label': 'Total Rating',
        'source_sheet': 'QUALITY OF WORKS',
        'cell': 'computed',
        'dependencies': ['work_item_weight', 'rating_per_degree'],
        'status': 'server_calculated',
    },
]

PROJECT_MANAGEMENT_FORMULA_REGISTRY = [
    {
        'key': 'corrective_actions_ratio',
        'label': 'Corrective Actions (# of Corrected Defects/ Total # of Defects)',
        'source_sheet': 'PROJECT MANAGEMENT',
        'cell': 'K58/N58/L58',
        'dependencies': ['total_defects', 'corrected_defects'],
        'status': 'server_calculated',
    },
    {
        'key': 'testing_requirements_ratio',
        'label': 'Min. Testing Requirements based on Latest SWA',
        'source_sheet': 'PROJECT MANAGEMENT',
        'cell': 'K60/N60/L60',
        'dependencies': ['min_tests_required', 'actual_tests_conducted'],
        'status': 'server_calculated',
    },
]

ASSESSMENT_RATING_FORMULA_REGISTRY = [
    {
        'key': 'project_management_weighted_rating',
        'label': 'Project Management (30%)',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K95',
        'dependencies': ['project_management_checks'],
        'status': 'server_calculated',
    },
    {
        'key': 'quality_of_works_weighted_rating',
        'label': 'Workmanship/Quality of Works (70%)',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K99',
        'dependencies': ['work_items', 'work_findings'],
        'status': 'server_calculated',
    },
    {
        'key': 'quality_rating',
        'label': 'Rating on Quality (Output I + Output II)',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K102',
        'dependencies': ['project_management_weighted_rating', 'quality_of_works_weighted_rating'],
        'status': 'server_calculated',
    },
    {
        'key': 'timeliness_rating',
        'label': 'Timeliness',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K106',
        'dependencies': ['planned_accomplishment_pct', 'actual_accomplishment_pct', 'time_elapsed', 'percent_slippage'],
        'status': 'server_calculated',
    },
    {
        'key': 'to_date_assessment_rating',
        'label': 'To Date Assessment Rating',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K116',
        'dependencies': ['quality_rating', 'timeliness_rating'],
        'status': 'server_calculated',
    },
    {
        'key': 'health_and_safety_rating',
        'label': 'Assessment Rating for Safety and Health',
        'source_sheet': 'REPORT SUMMARY',
        'cell': 'K124',
        'dependencies': ['health_safety_checks'],
        'status': 'server_calculated',
    },
]

SLIPPAGE_STATUSES = {'ON-GOING', 'SUSPENDED', 'CANCELLED'}

STATUS_ALIASES = {
    'ONGOING': 'ON-GOING',
    'ON GOING': 'ON-GOING',
    'ON-GOING': 'ON-GOING',
    'SUSPENDED': 'SUSPENDED',
    'COMPLETED': 'COMPLETED',
    'CANCELED': 'CANCELLED',
    'CANCELLED': 'CANCELLED',
}


def calculation_snapshot():
    return {
        'calculation_source': 'server',
        'reference_version': qaar_reference.QAAR_REFERENCE_VERSION,
        'computed_report_summary_fields': list(COMPUTED_REPORT_SUMMARY_KEYS),
        'formula_registry': get_formula_registry(),
        'formula_basis': 'QAAR v2.10a REPORT SUMMARY computed cells F32, F36, F37, F40, and L40.',
    }


def get_formula_registry():
    return {
        'report_summary': REPORT_SUMMARY_FORMULA_REGISTRY,
        'project_management': PROJECT_MANAGEMENT_FORMULA_REGISTRY,
        'quality_of_works': QUALITY_OF_WORKS_FORMULA_REGISTRY,
        'assessment_rating': ASSESSMENT_RATING_FORMULA_REGISTRY,
    }


def calculate_package(package):
    calculated = dict(package or {})
    calculated['report_summary'] = calculate_report_summary(calculated.get('report_summary') or {})
    calculated['scoring_summary'] = compute_scoring_summary(calculated)
    return calculated


def calculate_report_summary(summary):
    data = dict(summary or {})
    status = normalize_report_status(data.get('actual_project_status'))
    if status:
        data['actual_project_status'] = status

    duration = inclusive_days(data.get('date_started'), data.get('target_completion_date'))
    elapsed_basis = data.get('actual_completion_date') if status == 'COMPLETED' else data.get('date_of_inspection_assessment')
    elapsed_days = inclusive_days(data.get('date_started'), elapsed_basis)
    time_elapsed_pct = None
    if duration and elapsed_days is not None:
        time_elapsed_pct = min(elapsed_days / duration, 1) * 100

    planned = optional_float(data.get('planned_accomplishment_pct'))
    actual = optional_float(data.get('actual_accomplishment_pct'))
    slippage = None
    if status in SLIPPAGE_STATUSES and actual is not None:
        if planned is not None:
            slippage = actual - planned
        elif time_elapsed_pct is not None:
            slippage = actual - time_elapsed_pct

    national_subsidy = optional_float(data.get('national_subsidy'))
    lgu_counterpart = optional_float(data.get('lgu_counterpart')) or 0
    contract_amount = optional_float(data.get('contract_amount'))
    liquidation = optional_float(data.get('liquidation'))

    data.update({
        'percent_slippage': format_computed_number(slippage),
        'project_duration': format_computed_number(duration, places=0),
        'time_elapsed': f'{format_computed_number(time_elapsed_pct)}%' if time_elapsed_pct is not None else '',
        'total_project_cost': format_computed_number(national_subsidy + lgu_counterpart) if national_subsidy is not None else '',
        'balance_of_contract': (
            format_computed_number(contract_amount - liquidation)
            if contract_amount is not None and liquidation is not None
            else ''
        ),
    })
    return data


def compute_scoring_summary(package):
    project_management = score_check_rows(package.get('project_management_checks') or [])
    health_safety = score_check_rows(package.get('health_safety_checks') or [])
    work_items = score_work_items(package.get('work_items') or [])
    findings = score_work_findings(package.get('work_findings') or [], work_items['items'])
    scoring = {
        'reference_version': qaar_reference.QAAR_REFERENCE_VERSION,
        'method_note': (
            'Server-side COMET calculations use captured entries and the official QAAR v2.10a '
            'lookup tables. Project Management ratio rows, Health/Safety, and Quality of Works '
            'supported formulas are recalculated server-side; full Excel hidden-column formula parity '
            'remains tracked separately.'
        ),
        'project_management': project_management,
        'health_and_safety': health_safety,
        'work_items': work_items,
        'quality_of_works': findings,
    }
    scoring['assessment_rating'] = compute_assessment_rating(package, scoring)
    return scoring


def score_check_rows(rows):
    answered = [
        row for row in rows
        if _check_row_answered(row)
    ]
    points = sum(number_or_zero(row.get('points')) for row in answered)
    max_points = sum(number_or_zero(row.get('max_points')) for row in answered)
    official_max_points = sum(number_or_zero(row.get('max_points')) for row in rows)
    return {
        'answered_rows': len(answered),
        'official_rows': len(rows),
        'points': round_number(points),
        'max_points': round_number(max_points),
        'official_max_points': round_number(official_max_points),
        'score_pct': round_number((points / max_points) * 100) if max_points else None,
    }


def _check_row_answered(row):
    if row.get('response') not in (None, ''):
        return True
    form_data = row.get('form_data') or {}
    return any(value not in (None, '') for value in form_data.values())


def score_work_items(items):
    scored_items = []
    total_computed_cost = 0
    for item in items:
        inspected_quantity = optional_float(item.get('inspected_quantity'))
        quantity = optional_float(item.get('quantity'))
        unit_cost = optional_float(item.get('unit_cost'))
        basis_quantity = inspected_quantity if inspected_quantity is not None else quantity
        computed_cost = basis_quantity * unit_cost if basis_quantity is not None and unit_cost is not None else None
        if computed_cost is not None:
            total_computed_cost += computed_cost
        scored_items.append({
            'id': item.get('id'),
            'item_code': item.get('item_code'),
            'description': item.get('description'),
            'basis_quantity': round_number(basis_quantity),
            'unit_cost': round_number(unit_cost),
            'computed_cost': round_number(computed_cost),
            'computed_weight': None,
        })
    for item in scored_items:
        computed_cost = optional_float(item.get('computed_cost'))
        if total_computed_cost and computed_cost is not None:
            item['computed_weight'] = round_number(computed_cost / total_computed_cost, 6)
    return {
        'total_computed_cost': round_number(total_computed_cost) if total_computed_cost else None,
        'items': scored_items,
    }


def score_work_findings(findings, scored_work_items):
    item_weights = {
        item.get('id'): item.get('computed_weight')
        for item in scored_work_items
        if item.get('id') is not None
    }
    quality_weight_totals = {}
    prepared_findings = []
    for finding in findings:
        quality_issue_weight = qaar_reference.quality_issue_weight(finding.get('quality_issue'))
        prepared = {
            'finding': finding,
            'quality_issue_weight': quality_issue_weight,
        }
        prepared_findings.append(prepared)
        work_item_id = finding.get('work_item_id')
        if work_item_id is not None and quality_issue_weight is not None:
            quality_weight_totals[work_item_id] = (
                quality_weight_totals.get(work_item_id, 0) + quality_issue_weight
            )

    scored_findings = []
    total_demerit = 0
    for prepared in prepared_findings:
        finding = prepared['finding']
        rating_per_degree = optional_float(finding.get('rating_weight'))
        if rating_per_degree is None:
            rating_per_degree = qaar_reference.rating_for_degree(finding.get('degree_of_defect'))
        quality_issue_weight = prepared['quality_issue_weight']
        work_item_weight = item_weights.get(finding.get('work_item_id'))
        item_quality_weight_total = quality_weight_totals.get(finding.get('work_item_id'))
        derived_rating_per_finding = (
            optional_float(work_item_weight) / optional_float(item_quality_weight_total)
            if work_item_weight is not None and item_quality_weight_total
            else None
        )
        weighted_quality_issue = (
            optional_float(quality_issue_weight) * optional_float(derived_rating_per_finding)
            if quality_issue_weight is not None and derived_rating_per_finding is not None
            else None
        )
        computed_total_rating = (
            optional_float(rating_per_degree) * optional_float(weighted_quality_issue)
            if rating_per_degree is not None and weighted_quality_issue is not None
            else None
        )
        if computed_total_rating is not None:
            total_demerit += computed_total_rating
        scored_findings.append({
            'id': finding.get('id'),
            'work_item_id': finding.get('work_item_id'),
            'defect_code': finding.get('defect_code'),
            'degree_of_defect': finding.get('degree_of_defect'),
            'rating_per_degree': round_number(rating_per_degree),
            'quality_issue': finding.get('quality_issue'),
            'quality_issue_weight': quality_issue_weight,
            'work_item_weight': round_number(work_item_weight, 6),
            'derived_rating_per_finding': round_number(derived_rating_per_finding, 6),
            'weighted_quality_issue': round_number(weighted_quality_issue, 6),
            'computed_total_rating': round_number(computed_total_rating, 6),
        })
    merit_rating = max(1 - total_demerit, 0) if scored_findings else None
    weighted_rating = merit_rating * 0.7 if merit_rating is not None else None
    return {
        'findings': scored_findings,
        'total_known_rating': round_number(total_demerit, 6) if scored_findings else None,
        'total_demerit': round_number(total_demerit, 6) if scored_findings else None,
        'merit_rating': round_number(merit_rating, 6),
        'weighted_rating': round_number(weighted_rating, 6),
    }


def compute_assessment_rating(package, scoring):
    summary = package.get('report_summary') or {}
    project_management = scoring.get('project_management') or {}
    quality_of_works = scoring.get('quality_of_works') or {}
    health_safety = scoring.get('health_and_safety') or {}

    pm_weighted = _weighted_score(
        project_management.get('points'),
        project_management.get('official_max_points'),
        0.3,
        project_management.get('answered_rows'),
    )
    qow_weighted = optional_float(quality_of_works.get('weighted_rating'))
    quality_rating = _sum_if_any(pm_weighted, qow_weighted)
    timeliness = _timeliness_assessment(summary)
    to_date_rating = (
        quality_rating * 0.6 + timeliness['rating'] * 0.4
        if quality_rating is not None and timeliness.get('rating') is not None
        else None
    )
    health_rating = _health_safety_assessment(health_safety)

    return {
        'quality': {
            'project_management': _rating_entry(pm_weighted, _risk_for_component(pm_weighted, 0.3)),
            'quality_of_works': _rating_entry(qow_weighted, _risk_for_component(qow_weighted, 0.7)),
            'combined_quality': _rating_entry(quality_rating, _risk_for_fraction(quality_rating)),
        },
        'timeliness': {
            **timeliness,
            'rating_display': _format_percent_fraction(timeliness.get('rating')),
        },
        'to_date': _rating_entry(to_date_rating, _risk_for_fraction(to_date_rating)),
        'health_and_safety': health_rating,
    }


def _weighted_score(points, max_points, weight, answered_rows=None):
    if not answered_rows:
        return None
    points = optional_float(points)
    max_points = optional_float(max_points)
    if points is None or not max_points:
        return None
    return round_number((points / max_points) * weight, 6)


def _sum_if_any(*values):
    parsed = [optional_float(value) for value in values if optional_float(value) is not None]
    if not parsed:
        return None
    return round_number(sum(parsed), 6)


def _timeliness_assessment(summary):
    status = normalize_report_status(summary.get('actual_project_status'))
    planned = optional_float(summary.get('planned_accomplishment_pct'))
    actual = 100 if status == 'COMPLETED' else optional_float(summary.get('actual_accomplishment_pct'))
    time_elapsed = optional_float(summary.get('time_elapsed'))
    planned_target = planned if planned is not None else time_elapsed
    variance = (
        actual - planned_target
        if actual is not None and planned_target is not None
        else None
    )
    rating_pct = _timeliness_rating_pct(time_elapsed, planned_target, actual, variance)
    rating = rating_pct / 100 if rating_pct is not None else None
    return {
        'planned_target_accomplishment': round_number(planned_target),
        'actual_accomplishment': round_number(actual),
        'variance': round_number(variance),
        'rating': round_number(rating, 6),
        'risk_level': _risk_for_timeliness_pct(rating_pct),
        'assessment_note': _timeliness_note(time_elapsed, variance),
    }


def _timeliness_rating_pct(time_elapsed, planned_target, actual, variance):
    if time_elapsed is None and planned_target is None:
        return None
    if all(optional_float(value) == 0 for value in [planned_target, actual, variance]):
        return None
    if time_elapsed is not None and time_elapsed > 100:
        return 0
    if variance is None:
        return None
    if variance >= 100:
        return 0
    if variance >= 0:
        return 100
    if variance >= -5.99:
        return 80
    if variance >= -10.99:
        return 70
    if variance >= -15.99:
        return 50
    if variance >= -20.99:
        return 30
    return 0


def _timeliness_note(time_elapsed, variance):
    if time_elapsed is not None and time_elapsed > 100:
        return 'Time elapsed exceeded the construction duration'
    if variance is None or variance >= 0:
        return ''
    if variance >= -15:
        return 'Per RA 9184: LGU must issue a warning letter to Contractor'
    return "Subject for Termination of the Contractor's Contract"


def _health_safety_assessment(health_safety):
    if not health_safety.get('answered_rows'):
        return _rating_entry(None, '')
    points = optional_float(health_safety.get('points'))
    max_points = optional_float(health_safety.get('official_max_points')) or 110
    rating = points / max_points if points is not None and max_points else None
    risk = ''
    if rating is not None:
        risk = 'Compliant' if rating >= 1 else 'Non-Compliant'
    return _rating_entry(round_number(rating, 6), risk)


def _rating_entry(rating, risk_level):
    return {
        'rating': round_number(rating, 6),
        'rating_display': _format_percent_fraction(rating),
        'risk_level': risk_level or '',
    }


def _risk_for_component(value, component_weight):
    value = optional_float(value)
    component_weight = optional_float(component_weight)
    if value is None or not component_weight:
        return ''
    return _risk_for_fraction(value / component_weight)


def _risk_for_fraction(value):
    value = optional_float(value)
    if value is None:
        return ''
    percent = value * 100
    if percent == 100:
        return 'NO RISK'
    if percent >= 85:
        return 'LOW'
    if percent >= 70:
        return 'MODERATE'
    return 'HIGH'


def _risk_for_timeliness_pct(value):
    value = optional_float(value)
    if value is None:
        return ''
    if value == 100:
        return 'NO RISK'
    if value == 80:
        return 'LOW'
    if value == 70:
        return 'MODERATE'
    return 'HIGH'


def _format_percent_fraction(value):
    value = optional_float(value)
    if value is None:
        return ''
    return f'{format_computed_number(value * 100)}%'


def normalize_report_status(value):
    if value in (None, ''):
        return ''
    normalized = ' '.join(str(value).strip().replace('_', ' ').replace('-', ' ').upper().split())
    return STATUS_ALIASES.get(normalized, str(value).strip())


def inclusive_days(start_value, end_value):
    start_date = optional_date(start_value)
    end_date = optional_date(end_value)
    if not start_date or not end_date or end_date < start_date:
        return None
    return (end_date - start_date).days + 1


def optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        normalized = value.strip()
        if 'T' in normalized:
            normalized = normalized.split('T', 1)[0]
        try:
            return date.fromisoformat(normalized)
        except ValueError:
            return None
    return None


def optional_float(value):
    if value in (None, ''):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(',', '')
            if value.endswith('%'):
                value = value[:-1]
        return float(value)
    except (TypeError, ValueError):
        return None


def number_or_zero(value):
    numeric_value = optional_float(value)
    return numeric_value if numeric_value is not None else 0


def round_number(value, places=2):
    numeric_value = optional_float(value)
    if numeric_value is None:
        return None
    rounded = round(numeric_value, places)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def format_computed_number(value, places=2):
    rounded = round_number(value, places=places)
    return '' if rounded is None else str(rounded)
