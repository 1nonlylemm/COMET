import json
from functools import lru_cache
from pathlib import Path


QAAR_REFERENCE_VERSION = 'v2.10a'
QAAR_REFERENCE_FILENAME = 'qaar_tool_v2_10a.json'

LEGACY_RESPONSE_VALUES = {
    'yes',
    'no',
    'not_applicable',
    'not_observed',
    'partial',
}

PROJECT_MANAGEMENT_KEY_ALIASES = {
    'approved_boq': 'approved_bill_of_quantities',
    'received_ntp': 'received_notice_to_proceed',
    'approved_cshp': 'approved_construction_safety_and_health_program',
    'construction_methodology': 'construction_methodology_as_submitted_in_the_bid',
    'quality_control_plan': 'approved_quality_control_plan',
    'updated_construction_schedule': 'updated_construction_schedule_bar_chart_and_s_curve',
    'correspondence': 'correspondence_minutes_of_meeting_communication_letter_etc',
    'as_staked_plan': 'approved_as_staked_plan',
    'variation_order': 'approved_variation_order_if_any',
    'time_extension': 'approved_time_extension_if_any',
    'work_suspension': 'approved_work_suspension_if_any',
    'work_request': 'approved_work_request_if_any',
    'pouring_permit': 'approved_pouring_permit',
    'concreting_reports': 'reports_on_concreting_works_design_mix_job_mix_trial_mix',
    'site_instructions': 'site_instruction_s',
    'test_results': 'result_of_test',
    'regular_subaybayan_updating': 'regular_updating_in_subaybayan',
    'lgu_website_posting': 'website_posting_of_lgu_project_implementation',
    'final_inspection_report': 'final_inspection_report',
    'as_built_plans': 'approved_as_built_plans',
    'barricades_warning_signs': 'barricades_and_warning_signs',
    'ppe': 'personal_protective_equipment_ppe',
    'traffic_management': 'traffic_management_traffic_signs_flagmen_lighting_fixtures_reflectorized_signages_cones_etc',
    'project_billboard': 'project_billboards_coa',
    'surveyor': 'surveyor_instrument_man',
}

HEALTH_SAFETY_KEY_ALIASES = {
    'safety_officer_certification': 'presence_of_safety_officer_mandatory_with_ceritification_of_accreditation_from_dole',
    'medical_certificates': 'medical_ceritificates_of_personnel',
    'construction_pass_id': 'construction_pass_id_for_the_personnel',
    'board_and_lodging': 'board_and_lodging_for_stay_in_personnel_for_those_with_total_assets_of_above_php15m',
    'isolation_area': 'isolation_area_of_one_room_for_every_200_employees_for_those_with_total_assets_of_above_php15m',
    'sanitary_facilities': 'sanitary',
    'handwashing_alcohol': 'handwashing_station_and_or_dispensers_with_alcohol_based_solution_in_all_entrances_exits_and_areas_with_high_foot_traffic',
    'work_plan_schedule': 'work_plan_work_schedule',
    'entry_exit_logbook': 'for_entry_and_exit_of_workers',
    'health_logbook': 'for_pre_and_post_work_health_conditions_of_workers',
    'ppe': 'adequate_supply_of_ppes_disinfectants_and_handsoaps',
    'ppe_disinfectants': 'adequate_supply_of_ppes_disinfectants_and_handsoaps',
    'safety_policies': 'presence_of_safety_policies_posted_in_the_construction_site',
    'penalties_sanctions': 'penalties_and_sanction_for_violating_cshp',
    'waste_disposal': 'manner_of_disposing_waste_arising_from_the_construction',
}


@lru_cache(maxsize=1)
def get_reference():
    reference_path = Path(__file__).resolve().parents[1] / 'data' / QAAR_REFERENCE_FILENAME
    return json.loads(reference_path.read_text(encoding='utf-8'))


def _with_blank_option(options):
    return [{'value': '', 'label': 'Blank'}] + list(options or [])


def get_catalog():
    reference = get_reference()
    return {
        'reference': {
            'version': reference['version'],
            'source_workbook': reference['source_workbook'],
        },
        'setup': reference['setup'],
        'report_summary_fields': reference['report_summary_fields'],
        'report_summary_work_item_fields': reference['report_summary_work_item_fields'],
        'project_management_checks': reference['project_management_checks'],
        'health_safety_checks': reference['health_safety_checks'],
        'quality_of_works_headers': reference['quality_of_works_headers'],
        'check_responses': _with_blank_option(reference['check_response_options']),
        'item_catalog_entries': reference['item_catalog_entries'],
        'finding_catalog_entries': reference['finding_catalog_entries'],
        'ratings': reference['ratings'],
        'risk_levels': [
            {'value': 'minor', 'label': 'Minor trigger'},
            {'value': 'major', 'label': 'Major trigger'},
            {'value': 'severe', 'label': 'Severe risk identified'},
        ],
    }


def accepted_check_response_values():
    reference = get_reference()
    values = {item['value'] for item in reference['check_response_options']}
    values.update(LEGACY_RESPONSE_VALUES)
    return tuple(sorted(values))


def _index_by_key(rows):
    return {item['check_key']: item for item in rows}


def get_project_management_check(check_key):
    reference = get_reference()
    canonical_key = canonical_project_management_key(check_key)
    return _index_by_key(reference['project_management_checks']).get(canonical_key)


def get_health_safety_check(check_key):
    reference = get_reference()
    canonical_key = canonical_health_safety_key(check_key)
    return _index_by_key(reference['health_safety_checks']).get(canonical_key)


def canonical_project_management_key(check_key):
    return PROJECT_MANAGEMENT_KEY_ALIASES.get(check_key, check_key)


def canonical_health_safety_key(check_key):
    return HEALTH_SAFETY_KEY_ALIASES.get(check_key, check_key)


def points_for_response(reference_item, response):
    if not reference_item or response in (None, ''):
        return None
    option = option_for_response(reference_item, response)
    if option:
        return option.get('points')
    return None


def option_for_response(reference_item, response):
    if not reference_item or response in (None, ''):
        return None
    normalized = str(response).strip()
    for option in reference_item.get('response_options') or []:
        if str(option.get('value') or '').strip() == normalized:
            return option
    return None


def recommendation_for_response(reference_item, response):
    option = option_for_response(reference_item, response)
    if not option:
        return ''
    return option.get('recommendation') or option.get('finding') or ''


def ratio_metrics(reference_item, form_data):
    """Calculate QAAR Project Management ratio rows 45 and 46 from their numeric inputs."""
    if not reference_item or reference_item.get('input_type') != 'ratio':
        return {}
    form_data = form_data or {}
    input_fields = reference_item.get('input_fields') or []
    if len(input_fields) < 2:
        return {}

    denominator_key = input_fields[0]['key']
    numerator_key = input_fields[1]['key']
    denominator = _optional_float(form_data.get(denominator_key))
    numerator = _optional_float(form_data.get(numerator_key))
    max_points = _optional_float(reference_item.get('max_points')) or 0

    if denominator is None:
        return {
            'completion_rate': '',
            'response': '',
            'score': None,
            'score_bucket': None,
            'issue': '',
            'recommendation': '',
        }

    if denominator == 0:
        completion_rate = None
        score = max_points
    else:
        numerator = numerator or 0
        completion_rate = min(max(numerator / denominator, 0), 1)
        score = round(completion_rate * max_points, 2)

    score_bucket = int(score) if score is not None else None
    response = 'N/A' if denominator == 0 else f'{_format_number((completion_rate or 0) * 100)}%'
    issue = ''
    recommendation = ''
    if score is not None and score < max_points:
        issue_template = reference_item.get('issue_template') or ''
        try:
            issue = issue_template.format(**{
                key: _format_number(value)
                for key, value in form_data.items()
            })
        except KeyError:
            issue = issue_template
        recommendation = reference_item.get('recommendation') or ''

    return {
        'completion_rate': response,
        'response': response,
        'score': score,
        'score_bucket': score_bucket,
        'issue': issue,
        'recommendation': recommendation,
    }


def _optional_float(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_number(value):
    parsed = _optional_float(value)
    if parsed is None:
        return ''
    if parsed.is_integer():
        return str(int(parsed))
    return str(round(parsed, 2))


def rating_for_degree(degree):
    if degree in (None, ''):
        return None
    normalized = str(degree).strip().lower()
    for option in get_reference()['ratings']['degree_of_defect_options']:
        if option.get('value', '').strip().lower() == normalized:
            return option.get('rating_per_degree')
    return None


def quality_issue_weight(quality_issue):
    if quality_issue in (None, ''):
        return None
    normalized = ' '.join(str(quality_issue).strip().lower().split())
    for option in get_reference()['ratings']['quality_issue_weights']:
        values = {
            ' '.join(str(option.get('value') or '').strip().lower().split()),
            ' '.join(str(option.get('label') or '').strip().lower().split()),
        }
        if normalized in values:
            return option.get('weight')
    if normalized.startswith('high'):
        return 5
    if normalized.startswith('moderate'):
        return 3
    if normalized.startswith('low'):
        return 1
    return None


def search_item_catalog(category=None, query=None, limit=75):
    reference = get_reference()
    query = (query or '').strip().lower()
    category = (category or '').strip().upper()
    results = []
    for item in reference['item_catalog_entries']:
        if category and item.get('category') != category:
            continue
        haystack = f"{item.get('item_code') or ''} {item.get('description') or ''}".lower()
        if query and query not in haystack:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def search_finding_catalog(item_code=None, query=None, limit=75):
    reference = get_reference()
    query = (query or '').strip().lower()
    item_code = (item_code or '').strip()
    results = []
    for item in reference['finding_catalog_entries']:
        if item_code and item.get('item_code') != item_code:
            continue
        haystack = ' '.join([
            item.get('code_no') or '',
            item.get('finding') or '',
            item.get('recommendation') or '',
            item.get('quality_issue') or '',
        ]).lower()
        if query and query not in haystack:
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results
