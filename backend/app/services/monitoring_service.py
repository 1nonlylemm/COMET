from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import false

from app.extensions import db
from app.models import (
    LguProfile,
    ManagementActionReport,
    Project,
    QaarGeneratedOutput,
    QaarHealthSafetyCheck,
    QaarInspection,
    QaarProjectManagementCheck,
    QaarReportSummary,
    QaarWorkFinding,
    QaarWorkItem,
    StoredObject,
    SubaybayanVerification,
    User,
    Program,
)
from app.services import access_service, audit_service, object_storage_service, qaar_calculation_service, qaar_output_service, settings_service
from app.services.fiscal_year_scope import apply_inspection_project_fiscal_year, apply_project_fiscal_year
from app.services.completion_documents_service import resolve_effective_project_type
from app.services.project_service import validate_project_kind_for_program_type, ProjectError
from app.services import qaar_reference



VALID_INSPECTION_STATUSES = ('draft', 'submitted', 'reviewed', 'approved', 'flagged')
VALID_INSPECTION_TRANSITIONS = {
    'draft': {'draft', 'submitted', 'flagged'},
    'submitted': {'submitted', 'draft', 'reviewed', 'approved', 'flagged'},
    'reviewed': {'reviewed', 'draft', 'submitted', 'approved', 'flagged'},
    'flagged': {'flagged', 'draft', 'submitted', 'reviewed'},
    'approved': {'approved'},
}
OPERATIONAL_INSPECTION_FIELDS = {
    'qaar_package',
    'work_items',
    'work_findings',
    'physical_accomplishment_pct',
    'inspection_date',
    'monitoring_type',
    'observation_summary',
    'findings',
    'recommendations',
    'agreement_summary',
    'issues_identified',
    'is_site_visit',
    'aide_memoire_text',
    'annex_d_reference',
    'monthly_cycle_tag',
    'monthly_cycle_note',
}
VALID_MONITORING_TYPES = ('qaar',)
VALID_TRANSMITTAL_STATUSES = ('not_required', 'pending', 'transmitted', 'acknowledged')
VALID_PROJECT_KINDS = (
    'infrastructure',
    'goods',
    'vehicle',
    'financial_assistance',
)
VALID_MONITORING_APPLICABILITY = ('qaar', 'non_infra_template', 'none', 'mixed')
VALID_QAAR_CATEGORIES = ('WSS', 'DRR', 'LRS')
VALID_CHECK_RESPONSES = qaar_reference.accepted_check_response_values()
VALID_SUBAYBAYAN_LGU_STATUSES = ('not_checked', 'not_encoded', 'encoded', 'incomplete', 'returned_for_rectification')
VALID_SUBAYBAYAN_RO_STATUSES = ('pending', 'approved', 'returned', 'not_required')
VALID_SUBAYBAYAN_STATUSES = ('open', 'verified', 'validated', 'returned', 'closed')
VALID_RISK_LEVELS = ('none', 'minor', 'major', 'severe')
VALID_MANAGEMENT_ACTION_STATUSES = ('draft', 'for_review', 'submitted', 'acted', 'closed')
VALID_MANAGEMENT_ACTION_SOURCES = ('manual', 'qaar', 'subaybayan', 'notice', 'monthly_monitoring')
RISK_ORDER = {'none': 0, 'minor': 1, 'major': 2, 'severe': 3}


class MonitoringError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def list_inspections(
    project_id=None,
    status=None,
    monitoring_type=None,
    transmittal_status=None,
    monthly_cycle_tag=None,
    search=None,
    page=1,
    per_page=20,
    fiscal_year=None,
    user_id=None,
):
    query = QaarInspection.query.join(Project, QaarInspection.project_id == Project.id)
    query = _apply_project_scope(query, user_id)
    query = apply_inspection_project_fiscal_year(query, fiscal_year)

    if project_id is not None:
        query = query.filter(QaarInspection.project_id == project_id)
    if status:
        query = query.filter(QaarInspection.status == status)
    if monitoring_type:
        query = query.filter(QaarInspection.monitoring_type == monitoring_type)
    if transmittal_status:
        query = query.filter(QaarInspection.transmittal_status == transmittal_status)
    if monthly_cycle_tag:
        query = query.filter(QaarInspection.monthly_cycle_tag == monthly_cycle_tag)
    if search:
        query = query.join(LguProfile, Project.lgu_id == LguProfile.id).filter(
            db.or_(
                Project.project_name.ilike(f'%{search}%'),
                LguProfile.name.ilike(f'%{search}%'),
                QaarInspection.observation_summary.ilike(f'%{search}%'),
                QaarInspection.findings.ilike(f'%{search}%'),
                QaarInspection.recommendations.ilike(f'%{search}%'),
                QaarInspection.agreement_summary.ilike(f'%{search}%'),
                QaarInspection.issues_identified.ilike(f'%{search}%'),
                QaarInspection.annex_d_reference.ilike(f'%{search}%'),
                QaarInspection.transmittal_reference.ilike(f'%{search}%'),
            )
        )

    pagination = query.order_by(
        QaarInspection.inspection_date.desc(),
        QaarInspection.created_at.desc(),
    ).paginate(page=page, per_page=per_page, error_out=False)
    return {
        'items': [_serialize_inspection(item) for item in pagination.items],
        'page': pagination.page,
        'per_page': pagination.per_page,
        'total': pagination.total,
        'pages': pagination.pages,
    }


def get_monitoring_workbench(user_id=None, fiscal_year=None):
    query = (
        Project.query
        .join(LguProfile, Project.lgu_id == LguProfile.id)
        .filter(Project.current_phase != 'pre_implementation')
    )
    query = _apply_project_list_scope(query, user_id)
    query = apply_project_fiscal_year(query, fiscal_year)

    projects = query.order_by(Project.fiscal_year.desc(), Project.project_name.asc()).all()
    project_ids = [project.id for project in projects]
    inspections_by_project = {project_id: [] for project_id in project_ids}

    if project_ids:
        inspections = (
            QaarInspection.query
            .filter(QaarInspection.project_id.in_(project_ids))
            .order_by(QaarInspection.inspection_date.desc(), QaarInspection.created_at.desc())
            .all()
        )
        for inspection in inspections:
            inspections_by_project.setdefault(inspection.project_id, []).append(inspection)

    worklist = [
        _serialize_workbench_project(project, inspections_by_project.get(project.id, []))
        for project in projects
    ]
    return {
        'summary': {
            'monitorable_projects': len(projects),
            'with_monitoring_records': sum(1 for item in worklist if item['inspection_count'] > 0),
            'needing_initial_record': sum(1 for item in worklist if item['inspection_count'] == 0),
            'flagged_findings': sum(item['flagged_count'] for item in worklist),
            'pending_transmittal': sum(1 for item in worklist if item['pending_transmittal_count'] > 0),
        },
        'projects': worklist,
    }


def get_qaar_catalog():
    return qaar_reference.get_catalog()


def list_qaar_item_catalog(category=None, search=None, limit=75):
    return qaar_reference.search_item_catalog(category=category, query=search, limit=limit)


def list_qaar_finding_catalog(item_code=None, search=None, limit=75):
    return qaar_reference.search_finding_catalog(item_code=item_code, query=search, limit=limit)


def get_inspection(inspection_id, user_id=None):
    inspection = db.session.get(QaarInspection, inspection_id)
    if not inspection:
        raise MonitoringError('Inspection not found', 404)

    try:
        if user_id is not None:
            access_service.ensure_project_access(inspection.project_id, user_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc

    return inspection


def create_inspection(data, user_id):
    project = _get_project_with_access(data['project_id'], user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc
    _ensure_project_is_monitorable(project)
    _ensure_monitoring_type_allowed(project, data.get('monitoring_type', 'qaar'))

    inspection = QaarInspection(
        project_id=project.id,
        inspected_by=int(user_id),
        inspection_date=_parse_date(data['inspection_date']),
        monitoring_type=data.get('monitoring_type', 'qaar'),
        physical_accomplishment_pct=_optional_decimal(data.get('physical_accomplishment_pct'), 'physical_accomplishment_pct'),
        observation_summary=data.get('observation_summary'),
        findings=data.get('findings'),
        recommendations=data.get('recommendations'),
        agreement_summary=data.get('agreement_summary'),
        issues_identified=data.get('issues_identified'),
        is_site_visit=_json_bool(data.get('is_site_visit', True), 'is_site_visit'),
        aide_memoire_text=data.get('aide_memoire_text'),
        annex_d_reference=data.get('annex_d_reference'),
        transmittal_status=data.get('transmittal_status', 'not_required'),
        transmittal_reference=data.get('transmittal_reference'),
        transmitted_at=_parse_optional_datetime(data.get('transmitted_at')),
        monthly_cycle_tag=data.get('monthly_cycle_tag') or None,
        monthly_cycle_note=data.get('monthly_cycle_note'),
        status=data.get('status', 'draft'),
    )
    _validate_status(inspection.status)
    if inspection.status == 'approved':
        raise MonitoringError('Inspections cannot be created directly in approved status.', 422)
    _validate_monitoring_type(inspection.monitoring_type)
    _validate_transmittal_status(inspection.transmittal_status)
    _validate_physical_pct(inspection.physical_accomplishment_pct)

    try:
        db.session.add(inspection)
        db.session.flush()
        _sync_qaar_package(inspection, data.get('qaar_package'), user_id=user_id)
        _sync_embedded_subaybayan_verification(project, inspection, data.get('subaybayan_verification'), user_id=user_id, commit=False)
        _sync_embedded_management_action(project, inspection, data.get('management_action'), user_id=user_id, commit=False)
        _upsert_management_action_from_qaar_findings(inspection, user_id=user_id)
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='qaar_inspection',
            entity_id=inspection.id,
            old_value=None,
            new_value=_serialize_inspection(inspection),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return inspection


def update_inspection(inspection_id, data, user_id):
    inspection = get_inspection(inspection_id, user_id=user_id)
    try:
        access_service.assert_project_movement_allowed(inspection.project_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc
    before = _serialize_inspection(inspection)
    project = inspection.project
    _ensure_project_is_monitorable(project)

    if inspection.status == 'approved':
        if 'status' in data and data['status'] != 'approved':
            raise MonitoringError('Approved inspections cannot revert to an earlier mutable status.', 422)
        attempted_operational = [k for k in data if k in OPERATIONAL_INSPECTION_FIELDS and data[k] is not None]
        if attempted_operational:
            raise MonitoringError(
                f"Approved inspections are immutable: operational inspection content ({', '.join(attempted_operational)}) cannot be modified.",
                422,
            )

    if 'inspection_date' in data:
        inspection.inspection_date = _parse_date(data['inspection_date'])
    if 'monitoring_type' in data:
        _ensure_monitoring_type_allowed(project, data['monitoring_type'])
        _validate_monitoring_type(data['monitoring_type'])
        inspection.monitoring_type = data['monitoring_type']
    if 'physical_accomplishment_pct' in data:
        _validate_physical_pct(data['physical_accomplishment_pct'])
        inspection.physical_accomplishment_pct = _optional_decimal(data['physical_accomplishment_pct'], 'physical_accomplishment_pct')
    if 'observation_summary' in data:
        inspection.observation_summary = data['observation_summary']
    if 'findings' in data:
        inspection.findings = data['findings']
    if 'recommendations' in data:
        inspection.recommendations = data['recommendations']
    if 'agreement_summary' in data:
        inspection.agreement_summary = data['agreement_summary']
    if 'issues_identified' in data:
        inspection.issues_identified = data['issues_identified']
    if 'is_site_visit' in data:
        inspection.is_site_visit = _json_bool(data['is_site_visit'], 'is_site_visit')
    if 'aide_memoire_text' in data:
        inspection.aide_memoire_text = data['aide_memoire_text']
    if 'annex_d_reference' in data:
        inspection.annex_d_reference = data['annex_d_reference']
    if 'transmittal_status' in data:
        _validate_transmittal_status(data['transmittal_status'])
        inspection.transmittal_status = data['transmittal_status']
    if 'transmittal_reference' in data:
        inspection.transmittal_reference = data['transmittal_reference']
    if 'transmitted_at' in data:
        inspection.transmitted_at = _parse_optional_datetime(data['transmitted_at'])
    if 'monthly_cycle_tag' in data:
        inspection.monthly_cycle_tag = data['monthly_cycle_tag'] or None
    if 'monthly_cycle_note' in data:
        inspection.monthly_cycle_note = data['monthly_cycle_note']
    if 'status' in data:
        target_status = data['status']
        _validate_status(target_status)
        allowed_transitions = VALID_INSPECTION_TRANSITIONS.get(inspection.status, set())
        if target_status not in allowed_transitions:
            raise MonitoringError(
                f"Cannot transition inspection from '{inspection.status}' to '{target_status}'.",
                422,
            )
        inspection.status = target_status

    try:
        if 'qaar_package' in data:
            _sync_qaar_package(inspection, data.get('qaar_package'), user_id=user_id)
        if 'subaybayan_verification' in data:
            _sync_embedded_subaybayan_verification(project, inspection, data.get('subaybayan_verification'), user_id=user_id, commit=False)
        if 'management_action' in data:
            _sync_embedded_management_action(project, inspection, data.get('management_action'), user_id=user_id, commit=False)
        _upsert_management_action_from_qaar_findings(inspection, user_id=user_id)
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='qaar_inspection',
            entity_id=inspection.id,
            old_value=before,
            new_value=_serialize_inspection(inspection),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return inspection


def update_project_monitoring_profile(project_id, data, user_id=None):
    project = _get_project_with_access(project_id, user_id=user_id)
    before = _serialize_project_monitoring_profile(project)
    old_project_kind = project.project_kind

    if 'project_kind' in data:
        program = project.program or db.session.get(Program, project.program_id)
        program_type = program.program_type if program else None
        try:
            project.project_kind = validate_project_kind_for_program_type(
                program_type,
                data.get('project_kind'),
            )
        except ProjectError as exc:
            raise MonitoringError(exc.message, exc.status_code) from exc
    if 'monitoring_applicability' in data:
        _validate_optional_value(data.get('monitoring_applicability'), VALID_MONITORING_APPLICABILITY, 'monitoring_applicability')
        project.monitoring_applicability = _clean_text(data.get('monitoring_applicability'))
    if 'qaar_category' in data:
        _validate_optional_value(data.get('qaar_category'), VALID_QAAR_CATEGORIES, 'qaar_category')
        project.qaar_category = _clean_text(data.get('qaar_category'))
    if 'subaybayan_project_code' in data:
        project.subaybayan_project_code = _clean_text(data.get('subaybayan_project_code'))
    if 'subaybayan_url' in data:
        project.subaybayan_url = _clean_text(data.get('subaybayan_url'))
    if 'nadai_received_at' in data:
        project.nadai_received_at = _parse_optional_date(data.get('nadai_received_at'))
    if 'subaybayan_enrolled_at' in data:
        project.subaybayan_enrolled_at = _parse_optional_date(data.get('subaybayan_enrolled_at'))
    if 'subaybayan_enrollment_status' in data:
        _validate_optional_value(
            data.get('subaybayan_enrollment_status'),
            ('not_started', 'pending', 'enrolled', 'delayed', 'not_required'),
            'subaybayan_enrollment_status',
        )
        project.subaybayan_enrollment_status = _clean_text(data.get('subaybayan_enrollment_status'))

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id) if user_id else None,
            action='update',
            entity_type='project_monitoring_profile',
            entity_id=project.id,
            old_value=before,
            new_value=_serialize_project_monitoring_profile(project),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if 'project_kind' in data and project.project_kind != old_project_kind:
        from app.services import project_service
        project_service.reconcile_project_requirements(project.id, user_id=user_id)

    return _serialize_project_monitoring_profile(project)


def list_subaybayan_verifications(project_id=None, cycle_month=None, user_id=None):
    query = SubaybayanVerification.query.join(Project, SubaybayanVerification.project_id == Project.id)
    query = _apply_project_scope(query, user_id)
    if project_id is not None:
        query = query.filter(SubaybayanVerification.project_id == project_id)
    if cycle_month:
        _validate_cycle_month(cycle_month)
        query = query.filter(SubaybayanVerification.cycle_month == cycle_month)
    return [
        _serialize_subaybayan_verification(item)
        for item in query.order_by(SubaybayanVerification.cycle_month.desc(), SubaybayanVerification.created_at.desc()).all()
    ]


def upsert_subaybayan_verification(data, user_id=None, commit=True):
    project = _get_project_with_access(data.get('project_id'), user_id=user_id)
    cycle_month = data.get('cycle_month')
    _validate_cycle_month(cycle_month)
    verification = SubaybayanVerification.query.filter_by(
        project_id=project.id,
        cycle_month=cycle_month,
    ).first()
    before = _serialize_subaybayan_verification(verification) if verification else None
    if not verification:
        verification = SubaybayanVerification(
            project_id=project.id,
            cycle_month=cycle_month,
            verified_by=int(user_id) if user_id else None,
        )
        db.session.add(verification)
    _apply_subaybayan_verification_fields(verification, data, user_id=user_id)
    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id) if user_id else None,
            action='upsert',
            entity_type='subaybayan_verification',
            entity_id=verification.id,
            old_value=before,
            new_value=_serialize_subaybayan_verification(verification),
            commit=False,
        )
        if commit:
            db.session.commit()
    except Exception:
        if commit:
            db.session.rollback()
        raise
    return verification


def list_management_actions(project_id=None, cycle_month=None, user_id=None):
    query = ManagementActionReport.query.outerjoin(Project, ManagementActionReport.project_id == Project.id)
    query = _apply_project_scope(query, user_id)
    if project_id is not None:
        query = query.filter(ManagementActionReport.project_id == project_id)
    if cycle_month:
        _validate_cycle_month(cycle_month)
        query = query.filter(ManagementActionReport.cycle_month == cycle_month)
    return [
        _serialize_management_action(item)
        for item in query.order_by(ManagementActionReport.cycle_month.desc(), ManagementActionReport.created_at.desc()).all()
    ]


def upsert_management_action(data, user_id=None, commit=True):
    project_id = data.get('project_id')
    project = _get_project_with_access(project_id, user_id=user_id) if project_id else None
    action_id = data.get('id')
    action = db.session.get(ManagementActionReport, action_id) if action_id else None
    before = _serialize_management_action(action) if action else None
    if action:
        if action.project_id:
            _get_project_with_access(action.project_id, user_id=user_id)
    else:
        cycle_month = data.get('cycle_month')
        _validate_cycle_month(cycle_month)
        action = ManagementActionReport(
            project_id=project.id if project else None,
            cycle_month=cycle_month,
            prepared_by=int(user_id) if user_id else None,
        )
        db.session.add(action)
    _apply_management_action_fields(action, data, user_id=user_id)
    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id) if user_id else None,
            action='upsert',
            entity_type='management_action_report',
            entity_id=action.id,
            old_value=before,
            new_value=_serialize_management_action(action),
            commit=False,
        )
        if commit:
            db.session.commit()
    except Exception:
        if commit:
            db.session.rollback()
        raise
    return action


def calculate_slippage_risk_level(variance_pct):
    """Classify negative slippage into the shared risk_level vocabulary.

    variance_pct follows the convention `target_to_date_pct - actual_to_date_pct`
    (positive means behind schedule). Thresholds are configurable via
    `settings_service.get_risk_thresholds()` rather than hard-coded, per
    phase2a-plan.md #6.
    """
    if variance_pct is None:
        return None
    thresholds = settings_service.get_risk_thresholds()
    numeric_variance = float(variance_pct)
    if numeric_variance >= thresholds['high_pct']:
        return 'severe'
    if numeric_variance >= thresholds['moderate_pct']:
        return 'major'
    if numeric_variance > 0:
        return 'minor'
    return 'none'


def evaluate_monthly_monitoring_risk_trigger(monthly_progress_report, user_id=None):
    """Auto-create/update a MAR when a Monthly Progress Report is Major/Severe risk
    and no approved Form 3 exemption currently covers its reporting period.

    If an existing MAR is found but the risk has dropped or a Form 3 is now
    approved, auto-transitions the MAR to 'for_review'.
    """
    from app.models import Form3Request, ProjectRequirement, ManagementActionReport
    from flask import current_app
    from app.services import audit_service
    from app.extensions import db

    reporting_period = monthly_progress_report.reporting_period
    project_id = monthly_progress_report.project_id
    assessment_date = monthly_progress_report.assessment_date
    current_risk = monthly_progress_report.risk_level

    from sqlalchemy import or_, and_

    approved_form3_query = (
        Form3Request.query
        .join(ProjectRequirement, Form3Request.project_requirement_id == ProjectRequirement.id)
        .filter(
            Form3Request.project_id == project_id,
            ProjectRequirement.workflow_status == 'approved',
        )
    )

    if assessment_date:
        approved_form3_query = approved_form3_query.filter(
            or_(
                and_(
                    or_(Form3Request.requested_exemption_start.isnot(None), Form3Request.requested_exemption_end.isnot(None)),
                    or_(Form3Request.requested_exemption_start.is_(None), Form3Request.requested_exemption_start <= assessment_date),
                    or_(Form3Request.requested_exemption_end.is_(None), Form3Request.requested_exemption_end >= assessment_date),
                ),
                and_(
                    Form3Request.requested_exemption_start.is_(None),
                    Form3Request.requested_exemption_end.is_(None),
                    Form3Request.reporting_period == reporting_period,
                )
            )
        )
    else:
        approved_form3_query = approved_form3_query.filter(
            Form3Request.reporting_period == reporting_period
        )

    approved_form3 = approved_form3_query.first()
    trigger_holds = current_risk in ('major', 'severe') and not approved_form3

    existing = ManagementActionReport.query.filter_by(
        project_id=project_id,
        cycle_month=reporting_period,
        trigger_source='monthly_monitoring',
    ).order_by(ManagementActionReport.id.desc()).first()

    if trigger_holds:
        if existing and existing.status in ('closed', 'acted'):
            return existing

        trigger_summary = (
            f'Monthly Progress Report for {reporting_period} shows {current_risk} risk '
            f'(variance {monthly_progress_report.variance_pct}% behind target) with no approved Form 3 exemption on file.'
        )
        before = _serialize_management_action(existing) if existing else None

        if not existing:
            existing = ManagementActionReport(
                project_id=project_id,
                cycle_month=reporting_period,
                trigger_source='monthly_monitoring',
                prepared_by=int(user_id) if user_id else None,
            )
            db.session.add(existing)
            db.session.flush()

        existing.risk_level = current_risk
        existing.trigger_summary = trigger_summary
        if not existing.action_required:
            existing.action_required = (
                'Coordinate with the LGU to determine corrective action or require submission of a Form 3 '
                'justification if the delay is warranted.'
            )
        if existing.status in ('for_review',):
            existing.status = 'draft'

        try:
            db.session.flush()
            if before:
                audit_service.log_action(
                    user_id=int(user_id) if user_id else None,
                    action='update',
                    entity_type='management_action_report',
                    entity_id=existing.id,
                    old_value=before,
                    new_value=_serialize_management_action(existing),
                    commit=False,
                )
            else:
                audit_service.log_action(
                    user_id=int(user_id) if user_id else None,
                    action='mar_auto_generated',
                    entity_type='management_action_report',
                    entity_id=existing.id,
                    old_value=None,
                    new_value=_serialize_management_action(existing),
                    commit=False,
                )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        try:
            from app.services import notification_service
            notification_service.notify_management_action_event(
                management_action_id=existing.id,
                event='generated' if not before else 'updated',
                actor_user_id=user_id,
            )
        except Exception as exc:  # pragma: no cover
            current_app.logger.warning('MAR generation notification failed: %s', exc)

        return existing
    else:
        # Trigger dropped - reconcile existing open MAR if it exists
        if existing and existing.status in ('draft', 'submitted'):
            before = _serialize_management_action(existing)
            existing.status = 'for_review'
            
            reason = "Auto-resolved: Form 3 exemption approved for this reporting period." if approved_form3 else f"Auto-resolved: Risk level recalculated to {current_risk}."
            existing.resolution_notes = reason
            
            try:
                db.session.flush()
                audit_service.log_action(
                    user_id=int(user_id) if user_id else None,
                    action='update',
                    entity_type='management_action_report',
                    entity_id=existing.id,
                    old_value=before,
                    new_value=_serialize_management_action(existing),
                    commit=False,
                )
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise

            try:
                from app.services import notification_service
                notification_service.notify_management_action_event(
                    management_action_id=existing.id,
                    event='flagged_for_review',
                    actor_user_id=user_id,
                )
            except Exception as exc:  # pragma: no cover
                current_app.logger.warning('MAR flagged notification failed: %s', exc)

        return None


def submit_management_action(management_action_id, user_id, note=None):
    return _transition_management_action(management_action_id, user_id, action='submit', roles=('staff', 'admin'), note=note)


def acknowledge_management_action(management_action_id, user_id, note=None):
    return _transition_management_action(management_action_id, user_id, action='acknowledge', roles=('admin',), note=note)


def close_management_action(management_action_id, user_id, note=None):
    return _transition_management_action(management_action_id, user_id, action='close', roles=('admin', 'staff'), note=note)


VALID_MANAGEMENT_ACTION_TRANSITIONS = {
    'submit': {'from': ('draft',), 'to': 'submitted', 'action_label': 'submit'},
    'return': {'from': ('submitted',), 'to': 'draft', 'action_label': 'return'},
    'acknowledge': {'from': ('submitted',), 'to': 'acted', 'action_label': 'acknowledge'},
    'close': {'from': ('acted', 'for_review'), 'to': 'closed', 'action_label': 'close'},
}

def _transition_management_action(management_action_id, user_id, *, action, roles, note=None):
    role = access_service.get_user_role(user_id)
    if role not in roles:
        raise MonitoringError(
            f"Role '{role}' is not authorized for this action. Requires one of: {', '.join(roles)}",
            403,
        )
    action_def = VALID_MANAGEMENT_ACTION_TRANSITIONS[action]
    management_action = db.session.get(ManagementActionReport, management_action_id)
    if not management_action:
        raise MonitoringError('Management Action Report not found', 404)
    if management_action.project_id is not None:
        _get_project_with_access(management_action.project_id, user_id=user_id)
        try:
            access_service.assert_project_movement_allowed(management_action.project_id)
        except access_service.AccessError as exc:
            raise MonitoringError(exc.message, exc.status_code) from exc

    if management_action.status not in action_def['from']:
        raise MonitoringError(
            f'Cannot {action} a Management Action Report from status "{management_action.status}".',
            409,
        )

    before = _serialize_management_action(management_action)
    management_action.status = action_def['to']
    if action == 'close' and note:
        management_action.resolution_notes = note
    if action == 'close':
        from app.models.user import User
        user = db.session.get(User, user_id)
        if user and user.role == 'staff' and not getattr(user, 'can_close_management_actions', False):
            management_action.has_privilege_override = True
            from app.services import notification_service
            notification_service.notify_mar_privilege_override(management_action, user_id)
        management_action.resolved_at = datetime.now(timezone.utc)

    try:
        db.session.flush()
        audit_service.log_action(
            user_id=int(user_id),
            action=f'mar_{action}',
            entity_type='management_action_report',
            entity_id=management_action.id,
            old_value=before,
            new_value=_serialize_management_action(management_action),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    try:
        from app.services import notification_service
        event_map = {'submit': 'submitted', 'acknowledge': 'acted', 'close': 'closed'}
        notification_service.notify_management_action_event(
            management_action_id=management_action.id,
            event=event_map[action],
            actor_user_id=user_id,
        )
    except Exception as exc:  # pragma: no cover - defensive, transition must survive notification failures.
        current_app.logger.warning('MAR transition notification failed: %s', exc)
    return management_action


def list_management_actions_for_cycle(cycle_month, user_id=None):
    """Consolidated monthly MAR view (PO -> RO consolidation, per the Manual)."""
    _validate_cycle_month(cycle_month)
    return list_management_actions(cycle_month=cycle_month, user_id=user_id)


def generate_qaar_outputs(inspection_id, output_types=None, user_id=None):
    inspection = get_inspection(inspection_id, user_id=user_id)
    snapshot = _serialize_qaar_package(inspection)
    requested = output_types or ['full_package', 'aide_memoire', 'notice_of_defects']
    outputs = []
    with object_storage_service.storage_transaction() as storage_tx:
        for output_type in requested:
            if output_type not in qaar_output_service.VALID_OUTPUT_TYPES:
                raise MonitoringError(f'Invalid output_type: {output_type}', 422)
            rendered_output = qaar_output_service.build_qaar_output(inspection, output_type, snapshot)
            stored_pdf = object_storage_service.store_bytes(
                rendered_output['pdf_bytes'],
                source_module='qaar_outputs',
                original_filename=rendered_output['filename'],
                content_type='application/pdf',
                uploaded_by=user_id,
                metadata={
                    'inspection_id': inspection.id,
                    'output_type': output_type,
                    'reference_version': snapshot.get('scoring_summary', {}).get('reference_version'),
                },
                tracker=storage_tx,
            )
            output_snapshot = {
                **snapshot,
                'generated_output': rendered_output['structured_output'],
            }
            output = QaarGeneratedOutput(
                inspection_id=inspection.id,
                generated_by=int(user_id) if user_id else None,
                output_type=output_type,
                title=rendered_output['title'],
                status='generated',
                body_text=rendered_output['body_text'],
                file_object_id=stored_pdf.id,
                source_snapshot=_json_ready(output_snapshot),
            )
            db.session.add(output)
            outputs.append(output)
        db.session.commit()
        storage_tx.commit()
    return [_serialize_generated_output(item) for item in outputs]


def get_generated_output(output_id, user_id=None):
    output = db.session.get(QaarGeneratedOutput, output_id)
    if not output:
        raise MonitoringError('Generated QAAR output not found', 404)
    inspection = output.inspection
    if not inspection:
        raise MonitoringError('Generated QAAR output is not linked to an inspection', 404)
    try:
        if user_id is not None:
            access_service.ensure_project_access(inspection.project_id, user_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc
    return output


def get_generated_output_download(output_id, user_id=None):
    output = get_generated_output(output_id, user_id=user_id)
    if not output.file_object_id:
        raise MonitoringError('Generated PDF file is not available for this output.', 404)
    stored_object = db.session.get(StoredObject, output.file_object_id)
    if not stored_object:
        raise MonitoringError('Generated PDF file object was not found.', 404)
    return output, stored_object


def _sync_qaar_package(inspection, package, user_id=None):
    if package is None:
        return
    if inspection.monitoring_type == 'qaar':
        _ensure_monitoring_type_allowed(inspection.project, 'qaar')
    if not isinstance(package, dict):
        raise MonitoringError('qaar_package must be an object', 422)

    summary_data = package.get('report_summary')
    if summary_data is not None:
        _upsert_qaar_report_summary(inspection, summary_data)

    if 'project_management_checks' in package:
        _replace_project_management_checks(inspection, package.get('project_management_checks') or [])
    if 'health_safety_checks' in package:
        _replace_health_safety_checks(inspection, package.get('health_safety_checks') or [])
    if 'work_items' in package:
        _replace_work_items(inspection, package.get('work_items') or [])
    if 'work_findings' in package:
        _replace_work_findings(inspection, package.get('work_findings') or [])


def _upsert_qaar_report_summary(inspection, data):
    if not isinstance(data, dict):
        raise MonitoringError('qaar_package.report_summary must be an object', 422)
    summary = inspection.report_summary or QaarReportSummary(inspection_id=inspection.id)
    if summary.id is None:
        db.session.add(summary)
    autofill = _build_qaar_autofill_snapshot(inspection)
    effective_data = dict(data)
    fallback_values = {
        'office_address': autofill.get('office_address'),
        'region': autofill.get('region'),
        'province': autofill.get('province'),
        'city_municipality': autofill.get('city_municipality'),
        'barangay': autofill.get('barangay'),
        'program_name': autofill.get('program_name'),
        'funded_year': autofill.get('funded_year'),
        'implementing_unit': autofill.get('implementing_unit'),
        'monitoring_office': autofill.get('monitoring_office'),
        'project_id_text': autofill.get('project_id_text'),
        'project_title': autofill.get('project_title'),
        'national_subsidy': autofill.get('national_subsidy'),
        'project_location': autofill.get('project_location'),
        'project_description': autofill.get('project_description'),
        'date_of_inspection_assessment': inspection.inspection_date,
        'actual_accomplishment_pct': (
            float(inspection.physical_accomplishment_pct)
            if inspection.physical_accomplishment_pct is not None
            else None
        ),
        'actual_project_status': autofill.get('actual_project_status'),
        'date_started': autofill.get('date_started'),
        'target_completion_date': autofill.get('target_completion_date'),
        'prepared_by_name': autofill.get('prepared_by_name'),
        'prepared_by_position': autofill.get('prepared_by_position'),
    }
    for key, value in fallback_values.items():
        if effective_data.get(key) in (None, '') and value not in (None, ''):
            effective_data[key] = value
    calculated_data = qaar_calculation_service.calculate_report_summary(effective_data)
    autofill_snapshot = {
        **autofill,
        'calculation': qaar_calculation_service.calculation_snapshot(),
    }
    fields = {
        'office_address': _clean_text(calculated_data.get('office_address')),
        'program_name': _clean_text(calculated_data.get('program_name')),
        'funded_year': _optional_int(calculated_data.get('funded_year')),
        'implementing_unit': _clean_text(calculated_data.get('implementing_unit')),
        'monitoring_office': _clean_text(calculated_data.get('monitoring_office')),
        'project_id_text': _clean_text(calculated_data.get('project_id_text')),
        'project_title': _clean_text(calculated_data.get('project_title')),
        'national_subsidy': _optional_decimal(calculated_data.get('national_subsidy'), 'qaar_package.report_summary.national_subsidy'),
        'project_location': _clean_text(calculated_data.get('project_location')),
        'project_description': _clean_text(calculated_data.get('project_description')),
        'planned_accomplishment_pct': _optional_decimal(calculated_data.get('planned_accomplishment_pct'), 'qaar_package.report_summary.planned_accomplishment_pct'),
        'actual_accomplishment_pct': _optional_decimal(calculated_data.get('actual_accomplishment_pct'), 'qaar_package.report_summary.actual_accomplishment_pct'),
        'actual_project_status': _clean_text(calculated_data.get('actual_project_status')),
        'actual_completion_date': _parse_optional_date(calculated_data.get('actual_completion_date')),
        'date_started': _parse_optional_date(calculated_data.get('date_started')),
        'target_completion_date': _parse_optional_date(calculated_data.get('target_completion_date')),
        'lgu_counterpart': _optional_decimal(calculated_data.get('lgu_counterpart'), 'qaar_package.report_summary.lgu_counterpart'),
        'liquidation': _optional_decimal(calculated_data.get('liquidation'), 'qaar_package.report_summary.liquidation'),
        'contractor_name': _clean_text(calculated_data.get('contractor_name')),
        'contractor_address': _clean_text(calculated_data.get('contractor_address')),
        'owner_name': _clean_text(calculated_data.get('owner_name')),
        'owner_contact_number': _clean_text(calculated_data.get('owner_contact_number')),
        'pcab_license': _clean_text(calculated_data.get('pcab_license')),
        'contract_amount': _optional_decimal(calculated_data.get('contract_amount'), 'qaar_package.report_summary.contract_amount'),
        'prepared_by_name': _clean_text(calculated_data.get('prepared_by_name')),
        'prepared_by_position': _clean_text(calculated_data.get('prepared_by_position')),
        'form_data': _json_ready(calculated_data),
        'autofill_snapshot': _json_ready(autofill_snapshot),
    }
    for key, value in fields.items():
        setattr(summary, key, value)


def _replace_project_management_checks(inspection, checks):
    if not isinstance(checks, list):
        raise MonitoringError('project_management_checks must be a list', 422)
    QaarProjectManagementCheck.query.filter_by(inspection_id=inspection.id).delete(synchronize_session=False)
    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict):
            raise MonitoringError('Each project management check must be an object', 422)
        key = _clean_text(item.get('check_key'))
        if not key:
            continue
        reference_item = qaar_reference.get_project_management_check(key)
        canonical_key = reference_item['check_key'] if reference_item else key
        section = reference_item['section'] if reference_item else _clean_text(item.get('section'))
        label = reference_item['label'] if reference_item else _clean_text(item.get('label')) or key
        sort_order = reference_item['sort_order'] if reference_item else index
        form_data = _clean_project_management_form_data(item.get('form_data'), reference_item)
        if reference_item and reference_item.get('input_type') == 'ratio':
            response = None
            metrics = qaar_reference.ratio_metrics(reference_item, form_data)
            remarks = _clean_text(item.get('remarks')) or metrics.get('recommendation')
        else:
            response = _clean_text(item.get('response'))
            _validate_optional_value(response, VALID_CHECK_RESPONSES, 'project_management_checks.response')
            remarks = _clean_text(item.get('remarks')) or qaar_reference.recommendation_for_response(reference_item, response)
        db.session.add(QaarProjectManagementCheck(
            inspection_id=inspection.id,
            check_key=canonical_key,
            section=section,
            label=label,
            response=response,
            remarks=remarks,
            form_data=_json_ready(form_data),
            source=_clean_text(item.get('source')),
            sort_order=item.get('sort_order') or sort_order,
        ))


def _clean_project_management_form_data(value, reference_item=None):
    if not isinstance(value, dict):
        return {}
    if not reference_item or reference_item.get('input_type') != 'ratio':
        return _json_ready(value)

    cleaned = {}
    valid_keys = {field['key']: field for field in reference_item.get('input_fields') or []}
    for key, field in valid_keys.items():
        raw_value = value.get(key)
        if raw_value in (None, ''):
            continue
        numeric_value = _optional_float(raw_value)
        if numeric_value is None:
            raise MonitoringError(f'{field["label"]} must be numeric', 422)
        cleaned[key] = numeric_value
    return cleaned


def _replace_health_safety_checks(inspection, checks):
    if not isinstance(checks, list):
        raise MonitoringError('health_safety_checks must be a list', 422)
    QaarHealthSafetyCheck.query.filter_by(inspection_id=inspection.id).delete(synchronize_session=False)
    for index, item in enumerate(checks, start=1):
        if not isinstance(item, dict):
            raise MonitoringError('Each health and safety check must be an object', 422)
        key = _clean_text(item.get('check_key'))
        if not key:
            continue
        reference_item = qaar_reference.get_health_safety_check(key)
        canonical_key = reference_item['check_key'] if reference_item else key
        label = reference_item['label'] if reference_item else _clean_text(item.get('label')) or key
        sort_order = reference_item['sort_order'] if reference_item else index
        response = _clean_text(item.get('response'))
        _validate_optional_value(response, VALID_CHECK_RESPONSES, 'health_safety_checks.response')
        db.session.add(QaarHealthSafetyCheck(
            inspection_id=inspection.id,
            check_key=canonical_key,
            label=label,
            response=response,
            remarks=_clean_text(item.get('remarks')),
            sort_order=item.get('sort_order') or sort_order,
        ))


def _replace_work_items(inspection, items):
    if inspection.status == 'approved':
        raise MonitoringError('Cannot modify or delete work items on an approved inspection.', 422)
    if not isinstance(items, list):
        raise MonitoringError('work_items must be a list', 422)
    QaarWorkFinding.query.filter_by(inspection_id=inspection.id).delete(synchronize_session=False)
    QaarWorkItem.query.filter_by(inspection_id=inspection.id).delete(synchronize_session=False)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise MonitoringError('Each work item must be an object', 422)
        db.session.add(QaarWorkItem(
            inspection_id=inspection.id,
            item_code=_clean_text(item.get('item_code')),
            description=_clean_text(item.get('description')),
            quantity=_optional_decimal(item.get('quantity'), 'work_items.quantity'),
            inspected_quantity=_optional_decimal(item.get('inspected_quantity'), 'work_items.inspected_quantity'),
            unit=_clean_text(item.get('unit')),
            unit_cost=_optional_decimal(item.get('unit_cost'), 'work_items.unit_cost'),
            location=_clean_text(item.get('location')),
            source_catalog_row=_optional_int(item.get('source_catalog_row')),
            sort_order=item.get('sort_order') or index,
        ))
    db.session.flush()


def _replace_work_findings(inspection, findings):
    if inspection.status == 'approved':
        raise MonitoringError('Cannot modify or delete work findings on an approved inspection.', 422)
    if not isinstance(findings, list):
        raise MonitoringError('work_findings must be a list', 422)
    QaarWorkFinding.query.filter_by(inspection_id=inspection.id).delete(synchronize_session=False)
    work_items = QaarWorkItem.query.filter_by(inspection_id=inspection.id).order_by(QaarWorkItem.sort_order.asc(), QaarWorkItem.id.asc()).all()
    for index, item in enumerate(findings, start=1):
        if not isinstance(item, dict):
            raise MonitoringError('Each work finding must be an object', 422)
        work_item = _resolve_work_item_for_finding(item, work_items)
        risk_level = _clean_text(item.get('risk_level'))
        _validate_optional_value(risk_level, ('minor', 'major', 'severe'), 'work_findings.risk_level')
        db.session.add(QaarWorkFinding(
            inspection_id=inspection.id,
            work_item_id=work_item.id if work_item else None,
            defect_code=_clean_text(item.get('defect_code')),
            defect_description=_clean_text(item.get('defect_description')),
            quality_issue=_clean_text(item.get('quality_issue')),
            recommendation=_clean_text(item.get('recommendation')),
            location=_clean_text(item.get('location')),
            degree_of_defect=_clean_text(item.get('degree_of_defect')),
            rating_weight=_optional_decimal(item.get('rating_weight'), 'work_findings.rating_weight'),
            timeline=_clean_text(item.get('timeline')),
            remarks=_clean_text(item.get('remarks')),
            source_catalog_row=_optional_int(item.get('source_catalog_row')),
            risk_level=risk_level,
            sort_order=item.get('sort_order') or index,
        ))


def _resolve_work_item_for_finding(item, work_items):
    work_item_index = _optional_int(item.get('work_item_index'))
    if work_item_index and 1 <= work_item_index <= len(work_items):
        return work_items[work_item_index - 1]

    work_item_id = _optional_int(item.get('work_item_id'))
    if work_item_id is None:
        return None
    return next((work_item for work_item in work_items if work_item.id == work_item_id), None)


def _sync_embedded_subaybayan_verification(project, inspection, data, user_id=None, commit=True):
    if not data:
        return
    payload = dict(data)
    payload.setdefault('project_id', project.id)
    payload.setdefault('cycle_month', inspection.monthly_cycle_tag)
    if not payload.get('cycle_month'):
        raise MonitoringError('subaybayan_verification.cycle_month is required', 422)
    upsert_subaybayan_verification(payload, user_id=user_id, commit=commit)


def _sync_embedded_management_action(project, inspection, data, user_id=None, commit=True):
    if not data:
        return
    payload = dict(data)
    payload.setdefault('project_id', project.id)
    payload.setdefault('inspection_id', inspection.id)
    payload.setdefault('cycle_month', inspection.monthly_cycle_tag)
    if not payload.get('cycle_month'):
        raise MonitoringError('management_action.cycle_month is required', 422)
    upsert_management_action(payload, user_id=user_id, commit=commit)


def _upsert_management_action_from_qaar_findings(inspection, user_id=None):
    if not inspection.monthly_cycle_tag:
        return
    findings = QaarWorkFinding.query.filter_by(inspection_id=inspection.id).all()
    risky = [item for item in findings if item.risk_level]
    if not risky:
        return
    highest = max(risky, key=lambda item: RISK_ORDER.get(item.risk_level, 0))
    summary_lines = []
    action_lines = []
    for finding in risky:
        text = finding.defect_description or finding.quality_issue or finding.remarks
        if text:
            summary_lines.append(f'[{finding.risk_level}] {text}')
        if finding.recommendation:
            action_lines.append(finding.recommendation)
    action = ManagementActionReport.query.filter_by(
        inspection_id=inspection.id,
        trigger_source='qaar',
        cycle_month=inspection.monthly_cycle_tag,
    ).first()
    if action and action.status in ('closed', 'acted'):
        return
    if not action:
        action = ManagementActionReport(
            project_id=inspection.project_id,
            inspection_id=inspection.id,
            cycle_month=inspection.monthly_cycle_tag,
            trigger_source='qaar',
            prepared_by=int(user_id) if user_id else None,
        )
        db.session.add(action)
    action.risk_level = highest.risk_level
    action.trigger_summary = '\n'.join(summary_lines)
    action.action_required = '\n'.join(dict.fromkeys(action_lines))
    action.status = 'draft'


def _apply_subaybayan_verification_fields(verification, data, user_id=None):
    if 'verified_by' in data and data.get('verified_by'):
        verification.verified_by = data.get('verified_by')
    elif user_id:
        verification.verified_by = int(user_id)
    if 'lgu_encoded_status' in data:
        _validate_optional_value(data.get('lgu_encoded_status'), VALID_SUBAYBAYAN_LGU_STATUSES, 'lgu_encoded_status')
        verification.lgu_encoded_status = data.get('lgu_encoded_status') or 'not_checked'
    if 'lgu_encoded_at' in data:
        verification.lgu_encoded_at = _parse_optional_datetime(data.get('lgu_encoded_at'))
    if 'cmlgoo_verified_at' in data:
        verification.cmlgoo_verified_at = _parse_optional_datetime(data.get('cmlgoo_verified_at'))
    if 'po_validated_at' in data:
        verification.po_validated_at = _parse_optional_datetime(data.get('po_validated_at'))
    if 'ro_action_status' in data:
        _validate_optional_value(data.get('ro_action_status'), VALID_SUBAYBAYAN_RO_STATUSES, 'ro_action_status')
        verification.ro_action_status = data.get('ro_action_status') or 'pending'
    if 'ro_action_at' in data:
        verification.ro_action_at = _parse_optional_datetime(data.get('ro_action_at'))
    if 'discrepancy_notes' in data:
        verification.discrepancy_notes = _clean_text(data.get('discrepancy_notes'))
    if 'observations' in data:
        verification.observations = _clean_text(data.get('observations'))
    if 'evidence_links' in data:
        verification.evidence_links = data.get('evidence_links') or []
    if 'status' in data:
        _validate_optional_value(data.get('status'), VALID_SUBAYBAYAN_STATUSES, 'status')
        verification.status = data.get('status') or 'open'


def _validate_mar_references(target_project_id, inspection_id=None, verification_id=None):
    from app.models import QaarInspection, SubaybayanVerification
    validated_insp_id = None
    if inspection_id is not None and str(inspection_id).strip() != '':
        try:
            iid = int(inspection_id)
        except (ValueError, TypeError):
            raise MonitoringError('Invalid inspection_id.', 422)
        insp = db.session.get(QaarInspection, iid)
        if not insp:
            raise MonitoringError(f'QAAR inspection {iid} does not exist.', 422)
        if target_project_id and insp.project_id != target_project_id:
            raise MonitoringError('Referenced QAAR inspection does not belong to this project.', 422)
        validated_insp_id = iid

    validated_ver_id = None
    if verification_id is not None and str(verification_id).strip() != '':
        try:
            vid = int(verification_id)
        except (ValueError, TypeError):
            raise MonitoringError('Invalid verification_id.', 422)
        ver = db.session.get(SubaybayanVerification, vid)
        if not ver:
            raise MonitoringError(f'SubayBayan verification {vid} does not exist.', 422)
        if target_project_id and ver.project_id != target_project_id:
            raise MonitoringError('Referenced SubayBayan verification does not belong to this project.', 422)
        validated_ver_id = vid

    return validated_insp_id, validated_ver_id


def _apply_management_action_fields(action, data, user_id=None):
    target_project_id = data.get('project_id') if 'project_id' in data else action.project_id
    if 'project_id' in data and data.get('project_id') != action.project_id:
        new_pid = data.get('project_id')
        if 'inspection_id' not in data and action.inspection_id:
            from app.models import QaarInspection
            insp = db.session.get(QaarInspection, action.inspection_id)
            if insp and new_pid and insp.project_id != new_pid:
                raise MonitoringError('Existing QAAR inspection does not belong to the new project.', 422)
        if 'verification_id' not in data and action.verification_id:
            from app.models import SubaybayanVerification
            ver = db.session.get(SubaybayanVerification, action.verification_id)
            if ver and new_pid and ver.project_id != new_pid:
                raise MonitoringError('Existing SubayBayan verification does not belong to the new project.', 422)
        action.project_id = new_pid

    val_insp_id = None
    val_ver_id = None
    update_insp = 'inspection_id' in data
    update_ver = 'verification_id' in data
    if update_insp or update_ver:
        val_insp_id, val_ver_id = _validate_mar_references(
            target_project_id,
            inspection_id=data.get('inspection_id') if update_insp else None,
            verification_id=data.get('verification_id') if update_ver else None,
        )

    if update_insp:
        action.inspection_id = val_insp_id
    if update_ver:
        action.verification_id = val_ver_id
    if 'prepared_by' in data and data.get('prepared_by'):
        action.prepared_by = data.get('prepared_by')
    elif user_id and not action.prepared_by:
        action.prepared_by = int(user_id)
    if 'cycle_month' in data:
        _validate_cycle_month(data.get('cycle_month'))
        action.cycle_month = data.get('cycle_month')
    if 'risk_level' in data:
        _validate_optional_value(data.get('risk_level'), VALID_RISK_LEVELS, 'risk_level')
        action.risk_level = data.get('risk_level') or 'minor'
    if 'trigger_source' in data:
        _validate_optional_value(data.get('trigger_source'), VALID_MANAGEMENT_ACTION_SOURCES, 'trigger_source')
        action.trigger_source = data.get('trigger_source') or 'manual'
    if 'trigger_summary' in data:
        action.trigger_summary = _clean_text(data.get('trigger_summary'))
    if 'action_required' in data:
        action.action_required = _clean_text(data.get('action_required'))
    if 'responsible_office' in data:
        action.responsible_office = _clean_text(data.get('responsible_office'))
    if 'due_date' in data:
        action.due_date = _parse_optional_date(data.get('due_date'))
    if 'status' in data:
        _validate_optional_value(data.get('status'), VALID_MANAGEMENT_ACTION_STATUSES, 'status')
        action.status = data.get('status') or 'draft'
    if 'resolution_notes' in data:
        action.resolution_notes = _clean_text(data.get('resolution_notes'))
    if 'resolved_at' in data:
        action.resolved_at = _parse_optional_datetime(data.get('resolved_at'))


def _serialize_project_monitoring_profile(project):
    effective = _effective_monitoring_applicability(project)
    return {
        'project_id': project.id,
        'project_kind': project.project_kind,
        'monitoring_applicability': project.monitoring_applicability,
        'effective_monitoring_applicability': effective,
        'qaar_category': project.qaar_category,
        'subaybayan_project_code': project.subaybayan_project_code or project.source_project_code,
        'subaybayan_url': project.subaybayan_url,
        'nadai_received_at': project.nadai_received_at.isoformat() if project.nadai_received_at else None,
        'subaybayan_enrolled_at': project.subaybayan_enrolled_at.isoformat() if project.subaybayan_enrolled_at else None,
        'subaybayan_enrollment_status': project.subaybayan_enrollment_status,
        'subaybayan_enrollment_due_at': _subaybayan_due_date(project),
    }


def _effective_monitoring_applicability(project):
    if project.monitoring_applicability:
        return project.monitoring_applicability
    program = getattr(project, 'program', None) or (db.session.get(Program, project.program_id) if getattr(project, 'program_id', None) else None)
    if not project.project_kind and program and program.program_type == 'hybrid':
        return 'mixed'
    effective_kind = resolve_effective_project_type(project)
    if effective_kind in ('vehicle', 'goods', 'financial_assistance', 'non_infrastructure'):
        return 'non_infra_template'
    if effective_kind in ('infrastructure', 'infra'):
        return 'qaar'
    if effective_kind in ('mixed', 'hybrid'):
        return 'mixed'
    return 'qaar'


def _ensure_monitoring_type_allowed(project, monitoring_type):
    if monitoring_type != 'qaar':
        raise MonitoringError(
            'Implementation monitoring records are QAAR-only. Generate Aide Memoire and Notice outputs from a saved QAAR record.',
            422,
        )
    effective = _effective_monitoring_applicability(project)
    if effective not in {'qaar', 'mixed'}:
        raise MonitoringError(
            'QAAR monitoring is only applicable to infrastructure projects. Use the non-infrastructure monitoring path for this project.',
            422,
        )


def _subaybayan_due_date(project):
    if not project.nadai_received_at:
        return None
    return (project.nadai_received_at + timedelta(days=15)).isoformat()


def _build_qaar_autofill_snapshot(inspection):
    project = inspection.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    inspector = db.session.get(User, inspection.inspected_by) if inspection.inspected_by else None
    custom_fields = project.custom_fields or {}
    imported_context = custom_fields.get('imported_context') or {}
    location = (
        custom_fields.get('location')
        or _imported_context_value(imported_context, 'location')
        or (lgu.municipality if lgu else None)
    )
    return {
        'office_address': custom_fields.get('office_address'),
        'region': custom_fields.get('region') or 'CALABARZON',
        'province': custom_fields.get('province') or _qaar_province_value(lgu),
        'city_municipality': custom_fields.get('city_municipality') or _qaar_municipality_value(lgu),
        'barangay': custom_fields.get('barangay') or _imported_context_value(imported_context, 'barangay'),
        'program_name': program.name if program else None,
        'funded_year': project.fiscal_year if project else None,
        'implementing_unit': custom_fields.get('implementing_unit') or _qaar_implementing_unit_value(project, lgu),
        'monitoring_office': custom_fields.get('monitoring_office') or 'PROVINCIAL OFFICE',
        'project_id_text': project.subaybayan_project_code or project.source_project_code or str(project.id),
        'project_title': project.project_name,
        'national_subsidy': float(project.budget_amount) if project.budget_amount is not None else None,
        'project_location': location,
        'project_description': custom_fields.get('project_description') or custom_fields.get('description') or project.notes,
        'actual_project_status': project.overall_status,
        'date_started': project.actual_start_date,
        'target_completion_date': project.target_end_date,
        'prepared_by_name': inspector.full_name if inspector else None,
        'prepared_by_position': getattr(inspector, 'role', None) if inspector else None,
    }


def _qaar_province_value(lgu):
    return str(lgu.province).upper() if lgu and lgu.province else 'LAGUNA'


def _qaar_municipality_value(lgu):
    if not lgu:
        return None
    name = lgu.name or ''
    locality = lgu.municipality or name
    if locality.lower() == 'santa cruz':
        return 'SANTA CRUZ (Capital)'
    if name.lower().startswith('city of ') and not locality.upper().startswith('CITY OF '):
        return f'CITY OF {locality.replace(" City", "").upper()}'
    return locality.upper()


def _qaar_implementing_unit_value(project, lgu):
    custom_fields = (project.custom_fields or {}) if project else {}
    district = str(custom_fields.get('district') or '').upper()
    project_unit = str(custom_fields.get('implementing_unit') or '').upper()
    if project_unit in {'PROVINCIAL LGU', 'MUNICIPAL LGU', 'CITY LGU', 'BARANGAY LGU'}:
        return project_unit
    if district == 'PROVINCIAL':
        return 'PROVINCIAL LGU'
    if lgu and (lgu.name or '').lower().startswith('city of '):
        return 'CITY LGU'
    return 'MUNICIPAL LGU'


def _imported_context_value(imported_context, key):
    item = imported_context.get(key) if isinstance(imported_context, dict) else None
    if isinstance(item, dict):
        return item.get('value')
    return item


def _apply_project_list_scope(query, user_id):
    if user_id is None:
        return query

    try:
        return access_service.restrict_project_query(query, user_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc


def _apply_project_scope(query, user_id):
    if user_id is None:
        return query

    try:
        return access_service.restrict_project_query(query, user_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc


def _get_project_with_access(project_id, user_id=None):
    try:
        if user_id is not None:
            return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise MonitoringError(exc.message, exc.status_code) from exc

    project = db.session.get(Project, project_id)
    if not project:
        raise MonitoringError('Project not found', 404)
    return project


def _ensure_project_is_monitorable(project):
    if project.current_phase == 'pre_implementation':
        raise MonitoringError(
            'Implementation monitoring is only available after a project has entered the implementation phase.',
            422,
        )


def _validate_status(status):
    if status not in VALID_INSPECTION_STATUSES:
        raise MonitoringError(
            f'Invalid inspection status. Must be one of: {", ".join(VALID_INSPECTION_STATUSES)}',
            422,
        )


def _validate_monitoring_type(monitoring_type):
    if monitoring_type not in VALID_MONITORING_TYPES:
        raise MonitoringError(
            'monitoring_type must be qaar',
            422,
        )


def _validate_transmittal_status(transmittal_status):
    if transmittal_status not in VALID_TRANSMITTAL_STATUSES:
        raise MonitoringError(
            f'transmittal_status must be one of: {", ".join(VALID_TRANSMITTAL_STATUSES)}',
            422,
        )


def _validate_physical_pct(value):
    if value in (None, ''):
        return
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise MonitoringError('physical_accomplishment_pct must be numeric', 422) from exc
    if numeric_value < 0 or numeric_value > 100:
        raise MonitoringError('physical_accomplishment_pct must be between 0 and 100', 422)


def _parse_date(value):
    if isinstance(value, date):
        return value
    if not value:
        raise MonitoringError('inspection_date is required', 422)
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise MonitoringError('inspection_date must use YYYY-MM-DD format', 422) from exc
    raise MonitoringError('inspection_date must use YYYY-MM-DD format', 422)


def _parse_optional_datetime(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()).replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        normalized = value.replace('Z', '+00:00')
        try:
            return datetime.fromisoformat(normalized)
        except ValueError as exc:
            try:
                return datetime.combine(date.fromisoformat(value), datetime.min.time()).replace(tzinfo=timezone.utc)
            except ValueError:
                raise MonitoringError('transmitted_at must use ISO date or datetime format', 422) from exc
    raise MonitoringError('transmitted_at must use ISO date or datetime format', 422)


def _serialize_workbench_project(project, inspections):
    lgu = project.lgu
    program = project.program
    latest = inspections[0] if inspections else None
    flagged_count = sum(1 for item in inspections if item.status == 'flagged')
    pending_transmittal_count = sum(1 for item in inspections if item.transmittal_status == 'pending')
    if not inspections:
        monitoring_state = 'needs_initial_record'
    elif flagged_count:
        monitoring_state = 'flagged_follow_up'
    elif pending_transmittal_count:
        monitoring_state = 'pending_transmittal'
    elif latest.status in ('submitted', 'reviewed'):
        monitoring_state = 'under_review'
    else:
        monitoring_state = 'current'

    return {
        'project_id': project.id,
        'project_name': project.project_name,
        'lgu_id': project.lgu_id,
        'lgu_name': lgu.name if lgu else None,
        'lgu_municipality': lgu.municipality if lgu else None,
        'lgu_province': lgu.province if lgu else None,
        'program_id': project.program_id,
        'program_name': program.name if program else None,
        'program_type': program.program_type if program else None,
        'fiscal_year': project.fiscal_year,
        'source_project_code': project.source_project_code,
        'subaybayan_project_code': project.subaybayan_project_code,
        'budget_amount': float(project.budget_amount) if project.budget_amount is not None else None,
        'current_phase': project.current_phase,
        'overall_status': project.overall_status,
        'actual_start_date': project.actual_start_date.isoformat() if project.actual_start_date else None,
        'target_end_date': project.target_end_date.isoformat() if project.target_end_date else None,
        'actual_end_date': project.actual_end_date.isoformat() if project.actual_end_date else None,
        'physical_completion_pct': float(project.physical_completion_pct) if project.physical_completion_pct is not None else 0,
        'custom_fields': _json_ready(project.custom_fields or {}),
        'monitoring_profile': _serialize_project_monitoring_profile(project),
        'latest_subaybayan_verification': _serialize_latest_subaybayan_verification(project.id),
        'open_management_action_count': ManagementActionReport.query.filter(
            ManagementActionReport.project_id == project.id,
            ManagementActionReport.status.in_(('draft', 'for_review', 'submitted', 'acted')),
        ).count(),
        'inspection_count': len(inspections),
        'flagged_count': flagged_count,
        'pending_transmittal_count': pending_transmittal_count,
        'latest_inspection_id': latest.id if latest else None,
        'latest_inspection_date': latest.inspection_date.isoformat() if latest and latest.inspection_date else None,
        'latest_status': latest.status if latest else None,
        'latest_monitoring_type': latest.monitoring_type if latest else None,
        'latest_monthly_cycle_tag': latest.monthly_cycle_tag if latest else None,
        'monitoring_state': monitoring_state,
    }


def _serialize_inspection(inspection):
    project = inspection.project
    lgu = project.lgu if project else None
    program = project.program if project else None
    inspector = db.session.get(User, inspection.inspected_by) if inspection.inspected_by else None
    return {
        'id': inspection.id,
        'project_id': inspection.project_id,
        'project_name': project.project_name if project else None,
        'project_phase': project.current_phase if project else None,
        'program_id': project.program_id if project else None,
        'program_name': program.name if program else None,
        'lgu_id': project.lgu_id if project else None,
        'lgu_name': lgu.name if lgu else None,
        'inspection_date': inspection.inspection_date.isoformat() if inspection.inspection_date else None,
        'monitoring_type': inspection.monitoring_type,
        'physical_accomplishment_pct': float(inspection.physical_accomplishment_pct) if inspection.physical_accomplishment_pct is not None else None,
        'observation_summary': inspection.observation_summary,
        'findings': inspection.findings,
        'recommendations': inspection.recommendations,
        'agreement_summary': inspection.agreement_summary,
        'issues_identified': inspection.issues_identified,
        'is_site_visit': bool(inspection.is_site_visit),
        'aide_memoire_text': inspection.aide_memoire_text,
        'annex_d_reference': inspection.annex_d_reference,
        'transmittal_status': inspection.transmittal_status,
        'transmittal_reference': inspection.transmittal_reference,
        'transmitted_at': inspection.transmitted_at.isoformat() if inspection.transmitted_at else None,
        'monthly_cycle_tag': inspection.monthly_cycle_tag,
        'monthly_cycle_note': inspection.monthly_cycle_note,
        'monitoring_profile': _serialize_project_monitoring_profile(project) if project else None,
        'qaar_package': _serialize_qaar_package(inspection),
        'subaybayan_verification': _serialize_latest_subaybayan_verification(project.id, inspection.monthly_cycle_tag) if project and inspection.monthly_cycle_tag else None,
        'management_actions': [
            _serialize_management_action(item)
            for item in inspection.management_actions.order_by(ManagementActionReport.created_at.desc()).all()
        ],
        'generated_outputs': [
            _serialize_generated_output(item)
            for item in inspection.generated_outputs.order_by(QaarGeneratedOutput.generated_at.desc()).all()
        ],
        'status': inspection.status,
        'inspected_by': inspection.inspected_by,
        'inspected_by_name': inspector.full_name if inspector else None,
        'created_at': inspection.created_at.isoformat() if inspection.created_at else None,
        'updated_at': inspection.updated_at.isoformat() if inspection.updated_at else None,
    }


def _serialize_qaar_package(inspection):
    summary = inspection.report_summary
    project_management_checks = _serialize_qaar_project_management_checks(inspection)
    work_items = [
        _serialize_work_item(item)
        for item in inspection.work_items.order_by(QaarWorkItem.sort_order.asc(), QaarWorkItem.id.asc()).all()
    ]
    work_findings = [
        _serialize_work_finding(item)
        for item in inspection.work_findings.order_by(QaarWorkFinding.sort_order.asc(), QaarWorkFinding.id.asc()).all()
    ]
    health_safety_checks = _serialize_qaar_health_safety_checks(inspection)
    package = {
        'report_summary': _serialize_qaar_report_summary(summary) if summary else {
            'autofill_snapshot': _json_ready({
                **_build_qaar_autofill_snapshot(inspection),
                'calculation': qaar_calculation_service.calculation_snapshot(),
            }),
        },
        'project_management_checks': project_management_checks,
        'work_items': work_items,
        'work_findings': work_findings,
        'health_safety_checks': health_safety_checks,
    }
    package['report_summary'] = qaar_calculation_service.calculate_report_summary(package['report_summary'])
    package['scoring_summary'] = qaar_calculation_service.compute_scoring_summary(package)
    return package


def _serialize_qaar_report_summary(summary):
    form_data = summary.form_data or {}
    payload = {
        'id': summary.id,
        'office_address': summary.office_address,
        'program_name': summary.program_name,
        'funded_year': summary.funded_year,
        'implementing_unit': summary.implementing_unit,
        'monitoring_office': summary.monitoring_office,
        'project_id_text': summary.project_id_text,
        'project_title': summary.project_title,
        'national_subsidy': float(summary.national_subsidy) if summary.national_subsidy is not None else None,
        'project_location': summary.project_location,
        'project_description': summary.project_description,
        'planned_accomplishment_pct': float(summary.planned_accomplishment_pct) if summary.planned_accomplishment_pct is not None else None,
        'actual_accomplishment_pct': float(summary.actual_accomplishment_pct) if summary.actual_accomplishment_pct is not None else None,
        'actual_project_status': summary.actual_project_status,
        'actual_completion_date': summary.actual_completion_date.isoformat() if summary.actual_completion_date else None,
        'date_started': summary.date_started.isoformat() if summary.date_started else None,
        'target_completion_date': summary.target_completion_date.isoformat() if summary.target_completion_date else None,
        'lgu_counterpart': float(summary.lgu_counterpart) if summary.lgu_counterpart is not None else None,
        'liquidation': float(summary.liquidation) if summary.liquidation is not None else None,
        'contractor_name': summary.contractor_name,
        'contractor_address': summary.contractor_address,
        'owner_name': summary.owner_name,
        'owner_contact_number': summary.owner_contact_number,
        'pcab_license': summary.pcab_license,
        'contract_amount': float(summary.contract_amount) if summary.contract_amount is not None else None,
        'prepared_by_name': summary.prepared_by_name,
        'prepared_by_position': summary.prepared_by_position,
        'form_data': form_data,
        'autofill_snapshot': _json_ready(summary.autofill_snapshot or {}),
    }
    extras = {
        key: value
        for key, value in form_data.items()
        if key not in payload
    }
    return {**extras, **payload}


def _serialize_qaar_project_management_checks(inspection):
    catalog = qaar_reference.get_catalog()
    saved_items = inspection.project_management_checks.order_by(
        QaarProjectManagementCheck.sort_order.asc(),
        QaarProjectManagementCheck.id.asc(),
    ).all()
    saved_by_key = {
        qaar_reference.canonical_project_management_key(item.check_key): item
        for item in saved_items
    }
    rows = []
    for reference_item in catalog['project_management_checks']:
        saved_item = saved_by_key.pop(reference_item['check_key'], None)
        rows.append(_serialize_project_management_check(saved_item, reference_item))
    rows.extend(_serialize_project_management_check(item) for item in saved_by_key.values())
    return rows


def _serialize_project_management_check(item=None, reference_item=None):
    if reference_item is None and item is not None:
        reference_item = qaar_reference.get_project_management_check(item.check_key)
    check_key = reference_item.get('check_key') if reference_item else item.check_key
    label = reference_item.get('label') if reference_item else item.label
    section = reference_item.get('section') if reference_item else item.section
    sort_order = reference_item.get('sort_order') if reference_item else item.sort_order
    form_data = _json_ready(item.form_data or {}) if item and hasattr(item, 'form_data') else {}
    input_type = reference_item.get('input_type') if reference_item else 'select'
    if input_type == 'ratio':
        metrics = qaar_reference.ratio_metrics(reference_item, form_data)
        response = metrics.get('response') or ''
        points = metrics.get('score')
        remarks = item.remarks if item and item.remarks else metrics.get('recommendation') or ''
        computed = metrics
    else:
        response = item.response if item else ''
        points = qaar_reference.points_for_response(reference_item, response)
        remarks = item.remarks if item and item.remarks else qaar_reference.recommendation_for_response(reference_item, response)
        computed = {}
    return {
        'id': item.id if item else None,
        'check_key': check_key,
        'section': section,
        'label': label,
        'official_item_no': reference_item.get('official_item_no') if reference_item else None,
        'max_points': reference_item.get('max_points') if reference_item else None,
        'points': points,
        'input_type': input_type,
        'input_fields': reference_item.get('input_fields') if reference_item else [],
        'computed_fields': reference_item.get('computed_fields') if reference_item else [],
        'computed': computed,
        'response_options': reference_item.get('response_options') if reference_item else [],
        'source_row': reference_item.get('source_row') if reference_item else None,
        'response': response,
        'remarks': remarks,
        'form_data': form_data,
        'source': item.source if item else None,
        'sort_order': sort_order,
    }


def _serialize_work_item(item):
    return {
        'id': item.id,
        'item_code': item.item_code,
        'description': item.description,
        'quantity': float(item.quantity) if item.quantity is not None else None,
        'inspected_quantity': float(item.inspected_quantity) if item.inspected_quantity is not None else None,
        'unit': item.unit,
        'unit_cost': float(item.unit_cost) if item.unit_cost is not None else None,
        'location': item.location,
        'source_catalog_row': item.source_catalog_row,
        'sort_order': item.sort_order,
    }


def _serialize_work_finding(item):
    return {
        'id': item.id,
        'work_item_id': item.work_item_id,
        'defect_code': item.defect_code,
        'defect_description': item.defect_description,
        'quality_issue': item.quality_issue,
        'recommendation': item.recommendation,
        'location': item.location,
        'degree_of_defect': item.degree_of_defect,
        'rating_weight': float(item.rating_weight) if item.rating_weight is not None else None,
        'timeline': item.timeline,
        'remarks': item.remarks,
        'source_catalog_row': item.source_catalog_row,
        'risk_level': item.risk_level,
        'sort_order': item.sort_order,
    }


def _serialize_qaar_health_safety_checks(inspection):
    catalog = qaar_reference.get_catalog()
    saved_items = inspection.health_safety_checks.order_by(
        QaarHealthSafetyCheck.sort_order.asc(),
        QaarHealthSafetyCheck.id.asc(),
    ).all()
    saved_by_key = {
        qaar_reference.canonical_health_safety_key(item.check_key): item
        for item in saved_items
    }
    rows = []
    for reference_item in catalog['health_safety_checks']:
        saved_item = saved_by_key.pop(reference_item['check_key'], None)
        rows.append(_serialize_health_safety_check(saved_item, reference_item))
    rows.extend(_serialize_health_safety_check(item) for item in saved_by_key.values())
    return rows


def _serialize_health_safety_check(item=None, reference_item=None):
    if reference_item is None and item is not None:
        reference_item = qaar_reference.get_health_safety_check(item.check_key)
    check_key = reference_item.get('check_key') if reference_item else item.check_key
    label = reference_item.get('label') if reference_item else item.label
    sort_order = reference_item.get('sort_order') if reference_item else item.sort_order
    response = item.response if item else ''
    return {
        'id': item.id if item else None,
        'check_key': check_key,
        'label': label,
        'official_item_no': reference_item.get('official_item_no') if reference_item else None,
        'max_points': reference_item.get('max_points') if reference_item else None,
        'points': qaar_reference.points_for_response(reference_item, response),
        'response_options': reference_item.get('response_options') if reference_item else [],
        'source_row': reference_item.get('source_row') if reference_item else None,
        'response': response,
        'remarks': item.remarks if item else '',
        'sort_order': sort_order,
    }


def _compute_qaar_scoring_summary(package):
    return qaar_calculation_service.compute_scoring_summary(package)


def _score_check_rows(rows):
    answered = [
        row for row in rows
        if row.get('response') not in (None, '')
    ]
    points = sum(_number_or_zero(row.get('points')) for row in answered)
    max_points = sum(_number_or_zero(row.get('max_points')) for row in answered)
    official_max_points = sum(_number_or_zero(row.get('max_points')) for row in rows)
    return {
        'answered_rows': len(answered),
        'official_rows': len(rows),
        'points': _round_number(points),
        'max_points': _round_number(max_points),
        'official_max_points': _round_number(official_max_points),
        'score_pct': _round_number((points / max_points) * 100) if max_points else None,
    }


def _score_work_items(items):
    scored_items = []
    total_computed_cost = 0
    for item in items:
        inspected_quantity = _optional_float(item.get('inspected_quantity'))
        quantity = _optional_float(item.get('quantity'))
        unit_cost = _optional_float(item.get('unit_cost'))
        basis_quantity = inspected_quantity if inspected_quantity is not None else quantity
        computed_cost = basis_quantity * unit_cost if basis_quantity is not None and unit_cost is not None else None
        if computed_cost is not None:
            total_computed_cost += computed_cost
        scored_items.append({
            'id': item.get('id'),
            'item_code': item.get('item_code'),
            'description': item.get('description'),
            'basis_quantity': _round_number(basis_quantity),
            'unit_cost': _round_number(unit_cost),
            'computed_cost': _round_number(computed_cost),
            'computed_weight': None,
        })
    for item in scored_items:
        computed_cost = _optional_float(item.get('computed_cost'))
        if total_computed_cost and computed_cost is not None:
            item['computed_weight'] = _round_number(computed_cost / total_computed_cost, 6)
    return {
        'total_computed_cost': _round_number(total_computed_cost) if total_computed_cost else None,
        'items': scored_items,
    }


def _score_work_findings(findings, scored_work_items):
    item_weights = {
        item.get('id'): item.get('computed_weight')
        for item in scored_work_items
        if item.get('id') is not None
    }
    scored_findings = []
    total_known_rating = 0
    for finding in findings:
        rating_per_degree = _optional_float(finding.get('rating_weight'))
        if rating_per_degree is None:
            rating_per_degree = qaar_reference.rating_for_degree(finding.get('degree_of_defect'))
        quality_issue_weight = qaar_reference.quality_issue_weight(finding.get('quality_issue'))
        work_item_weight = item_weights.get(finding.get('work_item_id'))
        computed_total_rating = (
            _optional_float(work_item_weight) * _optional_float(rating_per_degree)
            if work_item_weight is not None and rating_per_degree is not None
            else None
        )
        if computed_total_rating is not None:
            total_known_rating += computed_total_rating
        scored_findings.append({
            'id': finding.get('id'),
            'work_item_id': finding.get('work_item_id'),
            'defect_code': finding.get('defect_code'),
            'degree_of_defect': finding.get('degree_of_defect'),
            'rating_per_degree': _round_number(rating_per_degree),
            'quality_issue': finding.get('quality_issue'),
            'quality_issue_weight': quality_issue_weight,
            'work_item_weight': _round_number(work_item_weight, 6),
            'computed_total_rating': _round_number(computed_total_rating, 6),
        })
    return {
        'findings': scored_findings,
        'total_known_rating': _round_number(total_known_rating, 6) if scored_findings else None,
    }


def _serialize_latest_subaybayan_verification(project_id, cycle_month=None):
    if not project_id:
        return None
    query = SubaybayanVerification.query.filter_by(project_id=project_id)
    if cycle_month:
        query = query.filter_by(cycle_month=cycle_month)
    verification = query.order_by(SubaybayanVerification.cycle_month.desc(), SubaybayanVerification.created_at.desc()).first()
    return _serialize_subaybayan_verification(verification) if verification else None


def _serialize_subaybayan_verification(item):
    if not item:
        return None
    verifier = db.session.get(User, item.verified_by) if item.verified_by else None
    project = item.project
    return {
        'id': item.id,
        'project_id': item.project_id,
        'project_name': project.project_name if project else None,
        'cycle_month': item.cycle_month,
        'verified_by': item.verified_by,
        'verified_by_name': verifier.full_name if verifier else None,
        'lgu_encoded_status': item.lgu_encoded_status,
        'lgu_encoded_at': item.lgu_encoded_at.isoformat() if item.lgu_encoded_at else None,
        'cmlgoo_verified_at': item.cmlgoo_verified_at.isoformat() if item.cmlgoo_verified_at else None,
        'po_validated_at': item.po_validated_at.isoformat() if item.po_validated_at else None,
        'ro_action_status': item.ro_action_status,
        'ro_action_at': item.ro_action_at.isoformat() if item.ro_action_at else None,
        'discrepancy_notes': item.discrepancy_notes,
        'observations': item.observations,
        'evidence_links': item.evidence_links or [],
        'status': item.status,
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_management_action(item):
    if not item:
        return None
    project = item.project
    return {
        'id': item.id,
        'project_id': item.project_id,
        'project_name': project.project_name if project else None,
        'inspection_id': item.inspection_id,
        'verification_id': item.verification_id,
        'prepared_by': item.prepared_by,
        'cycle_month': item.cycle_month,
        'risk_level': item.risk_level,
        'trigger_source': item.trigger_source,
        'trigger_summary': item.trigger_summary,
        'action_required': item.action_required,
        'responsible_office': item.responsible_office,
        'due_date': item.due_date.isoformat() if item.due_date else None,
        'status': item.status,
        'resolution_notes': item.resolution_notes,
        'resolved_at': item.resolved_at.isoformat() if item.resolved_at else None,
        'has_privilege_override': getattr(item, 'has_privilege_override', False),
        'created_at': item.created_at.isoformat() if item.created_at else None,
        'updated_at': item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_generated_output(item):
    stored_object = db.session.get(StoredObject, item.file_object_id) if item.file_object_id else None
    return {
        'id': item.id,
        'inspection_id': item.inspection_id,
        'generated_by': item.generated_by,
        'output_type': item.output_type,
        'title': item.title,
        'status': item.status,
        'body_text': item.body_text,
        'file_object_id': item.file_object_id,
        'file': _serialize_generated_output_file(item, stored_object),
        'source_snapshot': _json_ready(item.source_snapshot or {}),
        'generated_at': item.generated_at.isoformat() if item.generated_at else None,
    }


def _serialize_generated_output_file(item, stored_object):
    if not stored_object:
        return None
    return {
        'id': stored_object.id,
        'filename': stored_object.original_filename,
        'content_type': stored_object.content_type,
        'size_bytes': stored_object.size_bytes,
        'download_url': f'/api/monitoring/outputs/{item.id}/download',
    }


def _qaar_output_title(inspection, output_type):
    labels = {
        'report_summary': 'QAAR Report Summary',
        'project_management': 'QAAR Project Management',
        'quality_of_works': 'QAAR Quality of Works',
        'health_and_safety': 'QAAR Health and Safety',
        'findings_recommendations': 'QAAR Findings and Recommendations',
        'aide_memoire': 'Aide Memoire',
        'notice_of_defects': 'Notice of Defects / Deficiencies',
        'full_package': 'QAAR Package',
    }
    project_name = inspection.project.project_name if inspection.project else f'Inspection #{inspection.id}'
    return f'{labels.get(output_type, output_type)} - {project_name}'


def _render_qaar_output_text(inspection, output_type, snapshot):
    summary = snapshot.get('report_summary') or {}
    findings = snapshot.get('work_findings') or []
    project_management = snapshot.get('project_management_checks') or []
    health_safety = snapshot.get('health_safety_checks') or []
    work_items = snapshot.get('work_items') or []
    scoring = snapshot.get('scoring_summary') or {}
    catalog = qaar_reference.get_catalog()
    project = inspection.project
    lines = [
        _qaar_output_title(inspection, output_type),
        f"QAAR tool reference: {catalog['reference']['version']} ({catalog['reference']['source_workbook']})",
        f'Project: {project.project_name if project else ""}',
        f'LGU: {project.lgu.name if project and project.lgu else ""}',
        f'Inspection date: {inspection.inspection_date.isoformat() if inspection.inspection_date else ""}',
    ]
    if output_type in {'report_summary', 'full_package'}:
        lines.extend([
            f'Program: {summary.get("program_name") or ""}',
            f'Project ID: {summary.get("project_id_text") or ""}',
            f'Actual accomplishment: {summary.get("actual_accomplishment_pct") or ""}',
        ])
        if work_items:
            lines.append('ITEM/SCOPE OF WORKS: INSPECTED ITEMS ONLY WITH FINDINGS')
            scored_items = {
                item.get('id'): item
                for item in (scoring.get('work_items') or {}).get('items', [])
            }
            for item in work_items:
                scored_item = scored_items.get(item.get('id')) or {}
                lines.append(
                    f"- {item.get('item_code') or ''} | {item.get('description') or ''}"
                    f" | Quantity: {item.get('quantity') or ''}"
                    f" | Inspected: {item.get('inspected_quantity') or ''}"
                    f" | Unit: {item.get('unit') or ''}"
                    f" | Unit Cost: {item.get('unit_cost') or ''}"
                    f" | Computed Cost: {scored_item.get('computed_cost') or ''}"
                    f" | Weight: {scored_item.get('computed_weight') or ''}"
                )
    if output_type in {'project_management', 'full_package'}:
        pm_score = scoring.get('project_management') or {}
        lines.append(
            f"PROJECT MANAGEMENT score: {pm_score.get('points') or 0}/{pm_score.get('max_points') or 0}"
            f" answered rows; {pm_score.get('answered_rows') or 0}/{pm_score.get('official_rows') or len(project_management)} official rows answered"
        )
        lines.append('PROJECT MANAGEMENT')
        for check in project_management:
            lines.append(
                f"- {check.get('official_item_no') or ''}. {check.get('label') or ''}"
                f" | Remarks: {check.get('response') or ''}"
                f" | Notes: {check.get('remarks') or ''}"
            )
    if output_type in {'health_and_safety', 'full_package'}:
        hs_score = scoring.get('health_and_safety') or {}
        lines.append(
            f"HEALTH AND SAFETY score: {hs_score.get('points') or 0}/{hs_score.get('max_points') or 0}"
            f" answered rows; {hs_score.get('answered_rows') or 0}/{hs_score.get('official_rows') or len(health_safety)} official rows answered"
        )
        lines.append('CONSTRUCTION SAFETY IMPLEMENTATION ASSESSMENT')
        for check in health_safety:
            lines.append(
                f"- {check.get('official_item_no') or ''}. {check.get('label') or ''}"
                f" | Remarks: {check.get('response') or ''}"
                f" | Notes: {check.get('remarks') or ''}"
            )
    if output_type in {'quality_of_works', 'findings_recommendations', 'aide_memoire', 'notice_of_defects', 'full_package'}:
        headers = ', '.join(item['label'] for item in catalog['quality_of_works_headers'])
        lines.append(f'QUALITY OF WORKS columns: {headers}')
        lines.append('FINDINGS AND RECOMMENDATIONS:')
        scored_findings = {
            item.get('id'): item
            for item in (scoring.get('quality_of_works') or {}).get('findings', [])
        }
        for finding in findings:
            scored_finding = scored_findings.get(finding.get('id')) or {}
            lines.append(
                f'- Code No.: {finding.get("defect_code") or ""}'
                f' | Type of Defects/Damage: {finding.get("defect_description") or ""}'
                f' | Location/ Landmark: {finding.get("location") or ""}'
                f' | Quality Issue: {finding.get("quality_issue") or ""}'
                f' | Recommendation: {finding.get("recommendation") or ""}'
                f' | Degree of Defect: {finding.get("degree_of_defect") or ""}'
                f' | Rating per Degree: {scored_finding.get("rating_per_degree") or ""}'
                f' | Quality Issue Weight: {scored_finding.get("quality_issue_weight") or ""}'
                f' | Total Rating: {scored_finding.get("computed_total_rating") or ""}'
                f' | Timeline: {finding.get("timeline") or ""}'
                f' | Remarks: {finding.get("remarks") or ""}'
                f' | Risk: {finding.get("risk_level") or ""}'
            )
    if output_type == 'notice_of_defects':
        lines.append('Issuance owner: LGU to contractor, based on QAAR/Aide Memoire findings unless office policy states otherwise.')
    if scoring.get('method_note'):
        lines.append(f"QAAR scoring note: {scoring['method_note']}")
    return '\n'.join(lines)


def _optional_float(value):
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_decimal(value, field):
    if value in (None, ''):
        return None
    try:
        if isinstance(value, str):
            value = value.strip().replace(',', '')
        numeric_value = Decimal(str(value))
        if not numeric_value.is_finite():
            raise InvalidOperation
        return numeric_value
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MonitoringError(f'{field} must be numeric', 422) from exc


def _json_bool(value, field):
    if isinstance(value, bool):
        return value
    raise MonitoringError(f'{field} must be true or false', 422)


def _number_or_zero(value):
    numeric_value = _optional_float(value)
    return numeric_value if numeric_value is not None else 0


def _round_number(value, places=2):
    numeric_value = _optional_float(value)
    if numeric_value is None:
        return None
    rounded = round(numeric_value, places)
    if rounded == int(rounded):
        return int(rounded)
    return rounded


def _json_ready(value):
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _clean_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise MonitoringError('Expected an integer value', 422) from exc


def _parse_optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise MonitoringError('Date fields must use YYYY-MM-DD format', 422) from exc
    raise MonitoringError('Date fields must use YYYY-MM-DD format', 422)


def _validate_cycle_month(value):
    if not value or not isinstance(value, str):
        raise MonitoringError('cycle_month is required and must use YYYY-MM format', 422)
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise MonitoringError('cycle_month must use YYYY-MM format', 422) from exc


def _validate_optional_value(value, allowed, field):
    if value in (None, ''):
        return
    if value not in allowed:
        raise MonitoringError(f'{field} must be one of: {", ".join(allowed)}', 422)


def reconcile_mar_for_approved_form3(form3, user_id=None):
    from app.models.monitoring_extras import MonthlyProgressReport
    from app.models.field_inspection import ManagementActionReport
    from app.services import audit_service
    from app.extensions import db
    from flask import current_app

    reporting_period = form3.reporting_period
    project_id = form3.project_id

    existing_mars = ManagementActionReport.query.filter_by(
        project_id=project_id,
        cycle_month=reporting_period,
        trigger_source='monthly_monitoring'
    ).filter(
        ManagementActionReport.status.in_(['draft', 'submitted'])
    ).all()

    for existing in existing_mars:
        before = _serialize_management_action(existing)
        existing.status = 'for_review'
        existing.resolution_notes = "Auto-resolved: Form 3 exemption approved for this reporting period."
        try:
            db.session.flush()
            audit_service.log_action(
                user_id=int(user_id) if user_id else None,
                action='update',
                entity_type='management_action_report',
                entity_id=existing.id,
                old_value=before,
                new_value=_serialize_management_action(existing),
                commit=False,
            )
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        try:
            from app.services import notification_service
            notification_service.notify_management_action_event(
                management_action_id=existing.id,
                event='flagged_for_review',
                actor_user_id=user_id,
            )
        except Exception as exc:  # pragma: no cover
            current_app.logger.warning('MAR flagged notification failed: %s', exc)
