"""Monthly Progress Report service.

Implements phase2a-plan.md #1/#3/#4/#5/#6: a project-type-agnostic monthly
progress record with Target to Date, Actual to Date, server-computed
Variance / Negative Slippage, and a derived Risk Level. The record's
submit/review/approve/return lifecycle is delegated entirely to the
existing Phase 1 `requirement_workflow_service` via its backing
`ProjectRequirement` (tagged `document_category='monthly_progress_report'`).

Variance and risk are ALWAYS computed server-side and are never accepted
directly from client input, per the Phase 2A architecture rules.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import MonthlyProgressReport, Program, Project, ProjectRequirement, Requirement
from app.services import access_service, audit_service, monitoring_service, submission_service


class MonthlyProgressError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


REQUIREMENT_NAME = 'Monthly Progress Report'
DOCUMENT_CATEGORY = 'monthly_progress_report'


def _validate_project_scoped_references(project_id, qaar_inspection_id=None, evidence_submission_id=None):
    from app.models import QaarInspection, Submission
    validated_qaar_id = None
    if qaar_inspection_id is not None and str(qaar_inspection_id).strip() != '':
        try:
            qid = int(qaar_inspection_id)
        except (ValueError, TypeError):
            raise MonthlyProgressError('Invalid qaar_inspection_id.', 422)
        qaar = db.session.get(QaarInspection, qid)
        if not qaar:
            raise MonthlyProgressError(f'QAAR inspection {qid} does not exist.', 422)
        if qaar.project_id != project_id:
            raise MonthlyProgressError('Referenced QAAR inspection does not belong to this project.', 422)
        validated_qaar_id = qid

    validated_sub_id = None
    if evidence_submission_id is not None and str(evidence_submission_id).strip() != '':
        try:
            sid = int(evidence_submission_id)
        except (ValueError, TypeError):
            raise MonthlyProgressError('Invalid evidence_submission_id.', 422)
        sub = db.session.get(Submission, sid)
        if not sub:
            raise MonthlyProgressError(f'Evidence submission {sid} does not exist.', 422)
        sub_req = db.session.get(ProjectRequirement, sub.project_requirement_id)
        if not sub_req or sub_req.project_id != project_id:
            raise MonthlyProgressError('Referenced evidence submission does not belong to this project.', 422)
        validated_sub_id = sid

    return validated_qaar_id, validated_sub_id


def create_report(data, user_id, upload=None):
    project = _get_project_with_access(data.get('project_id'), user_id)
    try:
        access_service.assert_project_movement_allowed(project)
    except access_service.AccessError as exc:
        raise MonthlyProgressError(exc.message, exc.status_code) from exc
    reporting_period = _validate_reporting_period(data.get('reporting_period'))

    existing = MonthlyProgressReport.query.filter_by(
        project_id=project.id,
        reporting_period=reporting_period,
    ).first()
    if existing:
        raise MonthlyProgressError(
            f'A Monthly Progress Report already exists for {reporting_period}. Edit the existing report instead.',
            409,
        )

    qaar_id, evidence_sub_id = _validate_project_scoped_references(
        project.id,
        qaar_inspection_id=data.get('qaar_inspection_id'),
        evidence_submission_id=data.get('evidence_submission_id'),
    )

    requirement = _get_or_create_backing_requirement(project, reporting_period)

    report = MonthlyProgressReport(
        project_id=project.id,
        project_requirement_id=requirement.id,
        reporting_period=reporting_period,
        assessment_date=_parse_optional_date(data.get('assessment_date')),
        self_reported_actual_pct=_optional_decimal(data.get('self_reported_actual_pct'), 'self_reported_actual_pct'),
        target_to_date_pct=_optional_decimal(data.get('target_to_date_pct'), 'target_to_date_pct'),
        budget_utilization_pct=_optional_decimal(data.get('budget_utilization_pct'), 'budget_utilization_pct'),
        financial_progress_amount=_optional_decimal(data.get('financial_progress_amount'), 'financial_progress_amount'),
        qaar_inspection_id=qaar_id,
        evidence_submission_id=evidence_sub_id,
        created_by=int(user_id),
    )
    _apply_computed_fields(report)
    db.session.add(report)

    has_upload = upload is not None and bool(getattr(upload, 'filename', '').strip())
    try:
        if has_upload:
            db.session.flush()
            role = access_service.get_user_role(user_id)
            source = 'field_upload' if role == 'field_officer' else 'dms_ingestion'
            sub = submission_service.create_submission(
                requirement_id=requirement.id,
                source=source,
                description=f'Monthly Progress Report evidence for {reporting_period}',
                upload=upload,
                user_id=int(user_id),
            )
            report.evidence_submission_id = sub['id']
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='create',
            entity_type='monthly_progress_report',
            entity_id=report.id,
            old_value=None,
            new_value=_serialize_report(report),
            commit=False,
        )
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        err_msg = str(exc).lower()
        if 'uq_monthly_progress_project_period' in err_msg or ('project_id' in err_msg and 'reporting_period' in err_msg):
            raise MonthlyProgressError(
                f'A Monthly Progress Report already exists for {reporting_period}. Edit the existing report instead.',
                409,
            ) from exc
        raise MonthlyProgressError(str(exc), 422) from exc
    except Exception as exc:
        db.session.rollback()
        if isinstance(exc, (MonthlyProgressError, access_service.AccessError)):
            raise
        if isinstance(exc, submission_service.SubmissionError):
            raise MonthlyProgressError(exc.message, exc.status_code) from exc
        raise MonthlyProgressError(str(exc), 422) from exc

    if report.risk_level in ('major', 'severe'):
        try:
            monitoring_service.evaluate_monthly_monitoring_risk_trigger(report, user_id=user_id)
        except Exception:
            # Same rationale as update_report: never let the MAR auto-trigger
            # block saving the Monthly Progress Report itself, but log failures
            # so they are diagnosable instead of silently disappearing.
            current_app.logger.exception(
                'Monthly Progress Report %s: MAR auto-trigger evaluation failed on create.',
                report.id,
            )

    return report


def update_report(report_id, data, user_id):
    report = _get_report_with_access(report_id, user_id)
    try:
        access_service.assert_project_movement_allowed(report.project_id)
    except access_service.AccessError as exc:
        raise MonthlyProgressError(exc.message, exc.status_code) from exc
    before = _serialize_report(report)

    if report.project_requirement.workflow_status not in (None, 'draft', 'returned_for_revision'):
        raise MonthlyProgressError(
            'This report cannot be edited once it has been submitted. Use the workflow return action first.',
            409,
        )

    update_qaar = 'qaar_inspection_id' in data
    update_evidence = 'evidence_submission_id' in data
    new_qaar_id = None
    new_sub_id = None
    if update_qaar or update_evidence:
        new_qaar_id, new_sub_id = _validate_project_scoped_references(
            report.project_id,
            qaar_inspection_id=data.get('qaar_inspection_id') if update_qaar else None,
            evidence_submission_id=data.get('evidence_submission_id') if update_evidence else None,
        )

    if 'assessment_date' in data:
        report.assessment_date = _parse_optional_date(data.get('assessment_date'))
    if 'self_reported_actual_pct' in data:
        report.self_reported_actual_pct = _optional_decimal(data.get('self_reported_actual_pct'), 'self_reported_actual_pct')
    if 'target_to_date_pct' in data:
        report.target_to_date_pct = _optional_decimal(data.get('target_to_date_pct'), 'target_to_date_pct')
    if 'budget_utilization_pct' in data:
        report.budget_utilization_pct = _optional_decimal(data.get('budget_utilization_pct'), 'budget_utilization_pct')
    if 'financial_progress_amount' in data:
        report.financial_progress_amount = _optional_decimal(data.get('financial_progress_amount'), 'financial_progress_amount')
    if update_qaar:
        report.qaar_inspection_id = new_qaar_id
    if update_evidence:
        report.evidence_submission_id = new_sub_id

    try:
        _apply_computed_fields(report)
        db.session.flush()

        audit_service.log_action(
            user_id=int(user_id),
            action='update',
            entity_type='monthly_progress_report',
            entity_id=report.id,
            old_value=before,
            new_value=_serialize_report(report),
            commit=False,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if report.risk_level in ('major', 'severe'):
        try:
            monitoring_service.evaluate_monthly_monitoring_risk_trigger(report, user_id=user_id)
        except Exception:
            # The MAR auto-trigger must never block saving the Monthly Progress
            # Report itself, but a failure here should not be invisible either -
            # log it so it can be diagnosed instead of silently disappearing.
            current_app.logger.exception(
                'Monthly Progress Report %s: MAR auto-trigger evaluation failed.',
                report.id,
            )

    return report


def get_report(report_id, user_id=None):
    return _get_report_with_access(report_id, user_id)


def list_reports(project_id=None, reporting_period=None, workflow_status=None, user_id=None):
    query = MonthlyProgressReport.query.join(
        ProjectRequirement, MonthlyProgressReport.project_requirement_id == ProjectRequirement.id
    )
    if user_id is not None:
        query = access_service.restrict_project_requirement_query(query, user_id)
    if project_id is not None:
        query = query.filter(MonthlyProgressReport.project_id == project_id)
    if reporting_period:
        query = query.filter(MonthlyProgressReport.reporting_period == reporting_period)
    if workflow_status:
        query = query.filter(ProjectRequirement.workflow_status == workflow_status)
    items = query.order_by(MonthlyProgressReport.reporting_period.desc()).all()
    return [_serialize_report(item) for item in items]


def _apply_computed_fields(report):
    """Recompute variance and risk_level server-side. Never trust client input for these."""
    from app.models import QaarInspection
    
    qaar = None
    if report.qaar_inspection_id:
        qaar = db.session.get(QaarInspection, report.qaar_inspection_id)
        if qaar and qaar.project_id != report.project_id:
            qaar = None
    else:
        qaar = QaarInspection.query.filter_by(
            project_id=report.project_id, 
            monthly_cycle_tag=report.reporting_period
        ).first()

    report.has_data_discrepancy = False
    report.discrepancy_delta = None

    if qaar and qaar.physical_accomplishment_pct is not None:
        report.actual_to_date_pct = qaar.physical_accomplishment_pct
        report._resolution_source = 'QAAR derived'
        if report.self_reported_actual_pct is not None:
            delta = abs(report.self_reported_actual_pct - qaar.physical_accomplishment_pct)
            if delta > 5.0:
                report.has_data_discrepancy = True
                report.discrepancy_delta = delta
    else:
        report.actual_to_date_pct = report.self_reported_actual_pct
        report._resolution_source = 'Self-reported fallback'

    if report.target_to_date_pct is not None and report.actual_to_date_pct is not None:
        report.variance_pct = report.target_to_date_pct - report.actual_to_date_pct
    else:
        report.variance_pct = None
    report.risk_level = monitoring_service.calculate_slippage_risk_level(
        float(report.variance_pct) if report.variance_pct is not None else None
    )


def _get_or_create_backing_requirement(project, reporting_period):
    program = db.session.get(Program, project.program_id)
    catalog_requirement = None
    if program:
        catalog_requirement = (
            Requirement.query
            .join(Requirement.phase)
            .filter(
                Requirement.phase.has(program_id=program.id),
                Requirement.document_category == DOCUMENT_CATEGORY,
            )
            .first()
        )

    requirement = ProjectRequirement(
        project_id=project.id,
        requirement_id=catalog_requirement.id if catalog_requirement else None,
        requirement_name=f'{REQUIREMENT_NAME} ({reporting_period})',
        requirement_type='document',
        document_category=DOCUMENT_CATEGORY,
        is_mandatory=True,
        phase_name='Implementation',
        status='pending',
        workflow_status='draft',
        sort_order=0,
    )
    db.session.add(requirement)
    db.session.flush()
    return requirement


def _get_project_with_access(project_id, user_id):
    if not project_id:
        raise MonthlyProgressError('project_id is required.', 422)
    try:
        project_id = int(project_id)
    except (TypeError, ValueError) as exc:
        raise MonthlyProgressError('project_id must be an integer.', 422) from exc
    try:
        return access_service.ensure_project_access(project_id, user_id)
    except access_service.AccessError as exc:
        raise MonthlyProgressError(exc.message, exc.status_code) from exc


def _get_report_with_access(report_id, user_id):
    report = db.session.get(MonthlyProgressReport, report_id)
    if not report:
        raise MonthlyProgressError('Monthly Progress Report not found.', 404)
    if user_id is not None:
        try:
            access_service.ensure_project_access(report.project_id, user_id)
        except access_service.AccessError as exc:
            raise MonthlyProgressError(exc.message, exc.status_code) from exc
    return report


def _validate_reporting_period(value):
    if not value or not isinstance(value, str):
        raise MonthlyProgressError('reporting_period is required and must use YYYY-MM format.', 422)
    try:
        datetime.strptime(value, '%Y-%m')
    except ValueError as exc:
        raise MonthlyProgressError('reporting_period must use YYYY-MM format.', 422) from exc
    return value


def _parse_optional_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise MonthlyProgressError('Date fields must use YYYY-MM-DD format.', 422) from exc
    raise MonthlyProgressError('Date fields must use YYYY-MM-DD format.', 422)


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
        raise MonthlyProgressError(f'{field} must be numeric.', 422) from exc


def _serialize_report(report):
    requirement = report.project_requirement
    return {
        'id': report.id,
        'project_id': report.project_id,
        'project_requirement_id': report.project_requirement_id,
        'workflow_status': requirement.workflow_status if requirement else None,
        'workflow_return_reason': requirement.workflow_return_reason if requirement else None,
        'qaar_inspection_id': report.qaar_inspection_id,
        'evidence_submission_id': report.evidence_submission_id,
        'reporting_period': report.reporting_period,
        'assessment_date': report.assessment_date.isoformat() if report.assessment_date else None,
        'self_reported_actual_pct': float(report.self_reported_actual_pct) if report.self_reported_actual_pct is not None else None,
        'has_data_discrepancy': report.has_data_discrepancy,
        'discrepancy_delta': float(report.discrepancy_delta) if report.discrepancy_delta is not None else None,
        'resolution_source': getattr(report, '_resolution_source', None),
        'target_to_date_pct': float(report.target_to_date_pct) if report.target_to_date_pct is not None else None,
        'actual_to_date_pct': float(report.actual_to_date_pct) if report.actual_to_date_pct is not None else None,
        'variance_pct': float(report.variance_pct) if report.variance_pct is not None else None,
        'budget_utilization_pct': float(report.budget_utilization_pct) if report.budget_utilization_pct is not None else None,
        'financial_progress_amount': float(report.financial_progress_amount) if report.financial_progress_amount is not None else None,
        'risk_level': report.risk_level,
        'created_by': report.created_by,
        'created_at': report.created_at.isoformat() if report.created_at else None,
        'updated_at': report.updated_at.isoformat() if report.updated_at else None,
    }
