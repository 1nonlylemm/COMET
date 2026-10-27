from io import BytesIO

from flask import Blueprint, Response, request, send_file
from flask_jwt_extended import get_jwt_identity

from app.api.escalation.schemas import (
    validate_ai_draft_request,
    validate_dispatch_request,
    validate_generate_notice_request,
    validate_notice_create,
    validate_notice_document_params,
    validate_notice_receipt,
    validate_notice_release,
    validate_notice_update,
)
from app.services import ai_service, email_service, escalation_service, notice_service, settings_service
from app.utils.auth import admin_or_staff_required, admin_required, step_up_required
from app.utils.response import error_response, success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg


escalation_bp = Blueprint('escalation', __name__)


@escalation_bp.route('/dashboard', methods=['GET'])
@admin_or_staff_required
def dashboard():
    try:
        data = escalation_service.get_escalation_dashboard(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except escalation_service.EscalationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/breaches', methods=['GET'])
@admin_or_staff_required
def breach_list():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search')
    state = request.args.get('state')
    next_notice_type = request.args.get('next_notice_type')
    blocking_reason = request.args.get('blocking_reason')
    lgu_id = request.args.get('lgu_id', type=int)
    program_id = request.args.get('program_id', type=int)

    try:
        result = escalation_service.list_breach_candidates(
            page=page,
            per_page=per_page,
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
            search=search,
            state=state,
            next_notice_type=next_notice_type,
            blocking_reason=blocking_reason,
            lgu_id=lgu_id,
            program_id=program_id,
        )
        return success_response(data=result['breaches'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except escalation_service.EscalationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices', methods=['GET'])
@admin_or_staff_required
def list_notices():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    project_id = request.args.get('project_id', type=int)
    trigger_sla_id = request.args.get('trigger_sla_id', type=int)
    notice_type = request.args.get('notice_type')
    status = request.args.get('status')
    lgu_id = request.args.get('lgu_id', type=int)
    program_id = request.args.get('program_id', type=int)
    search = request.args.get('search')

    try:
        result = escalation_service.list_escalation_notices(
            page=page,
            per_page=per_page,
            user_id=get_jwt_identity(),
            project_id=project_id,
            trigger_sla_id=trigger_sla_id,
            notice_type=notice_type,
            status=status,
            lgu_id=lgu_id,
            program_id=program_id,
            fiscal_year=parse_fiscal_year_arg(request.args),
            search=search,
        )
        return success_response(data=result['notices'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except escalation_service.EscalationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/document-templates', methods=['GET'])
@admin_or_staff_required
def list_notice_document_templates():
    try:
        return success_response(data=settings_service.list_notice_document_templates())
    except settings_service.SettingsError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices', methods=['POST'])
@admin_or_staff_required
def create_notice():
    data = request.get_json() or {}
    errors = validate_notice_create(data)
    if errors:
        return validation_error(errors)

    try:
        notice = notice_service.create_notice(
            project_id=data['project_id'],
            notice_type=data['notice_type'],
            generated_by=get_jwt_identity(),
            trigger_sla_id=data.get('trigger_sla_id'),
            trigger_project_requirement_id=data.get('trigger_project_requirement_id'),
            title=data.get('title'),
            final_text=data.get('final_text'),
            status=data.get('status', 'draft'),
            legal_findings=data.get('legal_findings'),
            user_id=get_jwt_identity(),
        )
        detail = escalation_service.get_escalation_notice_detail(notice.id, user_id=get_jwt_identity())
        return success_response(
            data=detail,
            message='Escalation notice created successfully',
            status_code=201,
        )
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>', methods=['GET'])
@admin_or_staff_required
def get_notice(notice_id):
    try:
        data = escalation_service.get_escalation_notice_detail(notice_id, user_id=get_jwt_identity())
        return success_response(data=data)
    except escalation_service.EscalationError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>', methods=['PUT'])
@admin_or_staff_required
def update_notice(notice_id):
    data = request.get_json() or {}
    errors = validate_notice_update(data)
    if errors:
        return validation_error(errors)

    try:
        notice = notice_service.update_notice(notice_id, data, user_id=get_jwt_identity())
        detail = escalation_service.get_escalation_notice_detail(notice.id, user_id=get_jwt_identity())
        return success_response(data=detail, message='Escalation notice updated successfully')
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/ai-draft', methods=['POST'])
@admin_or_staff_required
def ai_draft_notice(notice_id):
    data = request.get_json() or {}
    errors = validate_ai_draft_request(data)
    if errors:
        return validation_error(errors)

    try:
        draft = ai_service.draft_annex_e_finding(
            notice_id=notice_id,
            informal_notes=data['informal_notes'],
            finding_id=data.get('finding_id'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=draft, message='AI draft generated successfully')
    except (ai_service.AiServiceError, escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/document', methods=['GET', 'POST'])
@admin_or_staff_required
def render_notice_document(notice_id):
    request_payload = request.get_json(silent=True) if request.method == 'POST' else {}
    request_payload = request_payload or {}
    params = {'format': request_payload.get('format') or request.args.get('format', 'pdf')}
    errors = validate_notice_document_params(params)
    if errors:
        return validation_error(errors)
    placeholder_overrides = request_payload.get('placeholder_overrides') or {}
    if not isinstance(placeholder_overrides, dict):
        return validation_error({'placeholder_overrides': 'placeholder_overrides must be an object'})

    try:
        document_bytes, mimetype, filename = notice_service.render_notice_document(
            notice_id=notice_id,
            output_format=params['format'],
            user_id=get_jwt_identity(),
            template_id=request_payload.get('template_id') or request.args.get('template_id'),
            placeholder_overrides=placeholder_overrides,
        )
        if params['format'] == 'html':
            return Response(document_bytes, mimetype=mimetype)

        as_attachment = request.args.get('download', 'true').lower() == 'true'
        return send_file(
            BytesIO(document_bytes),
            mimetype=mimetype,
            as_attachment=as_attachment,
            download_name=filename,
        )
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/document/preview', methods=['POST'])
@admin_or_staff_required
def preview_notice_document(notice_id):
    payload = request.get_json(silent=True) or {}
    placeholder_overrides = payload.get('placeholder_overrides') or {}
    if not isinstance(placeholder_overrides, dict):
        return validation_error({'placeholder_overrides': 'placeholder_overrides must be an object'})
    draft = payload.get('draft')
    if draft is not None and not isinstance(draft, dict):
        return validation_error({'draft': 'draft must be an object'})

    try:
        preview = notice_service.preview_notice_document(
            notice_id,
            user_id=get_jwt_identity(),
            template_id=payload.get('template_id'),
            placeholder_overrides=placeholder_overrides,
            draft_payload=draft,
        )
        return success_response(data=preview)
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/release', methods=['POST'])
@admin_required
def release_notice(notice_id):
    data = request.get_json() or {}
    errors = validate_notice_release(data)
    if errors:
        return validation_error(errors)

    try:
        result = notice_service.release_notice(notice_id, data, user_id=get_jwt_identity())
        notice_detail = escalation_service.get_escalation_notice_detail(
            result['notice'].id,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data={
                'communication': result['communication'],
                'notice': notice_detail,
            },
            message='Notice marked released successfully',
            status_code=201,
        )
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/receipt', methods=['POST'])
@admin_or_staff_required
def record_notice_receipt(notice_id):
    data = request.get_json() or {}
    errors = validate_notice_receipt(data)
    if errors:
        return validation_error(errors)

    try:
        notice_service.record_notice_receipt(notice_id, data, user_id=get_jwt_identity())
        notice_detail = escalation_service.get_escalation_notice_detail(notice_id, user_id=get_jwt_identity())
        return success_response(data=notice_detail, message='Notice receipt recorded successfully')
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/dispatch-preview', methods=['POST'])
@admin_or_staff_required
def dispatch_preview(notice_id):
    data = request.get_json() or {}
    errors = validate_dispatch_request(data)
    if errors:
        return validation_error(errors)

    try:
        payload = email_service.prepare_notice_dispatch(
            notice_id,
            channel=data['channel'],
            magic_link_id=data.get('magic_link_id'),
            recipient_name=data.get('recipient_name'),
            recipient_destination=data.get('recipient_destination'),
            recipient_office=data.get('recipient_office'),
            reference_no=data.get('reference_no'),
            remarks=data.get('remarks'),
            user_id=get_jwt_identity(),
        )
        return success_response(data=payload)
    except (email_service.DispatchError, escalation_service.EscalationError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/notices/<int:notice_id>/dispatch-log', methods=['POST'])
@admin_required
@step_up_required
def dispatch_log(notice_id):
    data = request.get_json() or {}
    errors = validate_dispatch_request(data)
    if errors:
        return validation_error(errors)

    try:
        result = email_service.record_notice_dispatch(
            notice_id,
            channel=data['channel'],
            magic_link_id=data.get('magic_link_id'),
            recipient_name=data.get('recipient_name'),
            recipient_destination=data.get('recipient_destination'),
            recipient_office=data.get('recipient_office'),
            reference_no=data.get('reference_no'),
            remarks=data.get('remarks'),
            user_id=get_jwt_identity(),
        )
        notice_detail = escalation_service.get_escalation_notice_detail(notice_id, user_id=get_jwt_identity())
        return success_response(
            data={
                'communication': result['communication'],
                'notice': notice_detail,
            },
            message='Dispatch recorded successfully',
            status_code=201,
        )
    except (email_service.DispatchError, escalation_service.EscalationError) as exc:
        return error_response(exc.message, status_code=exc.status_code)


@escalation_bp.route('/generate-notice', methods=['POST'])
@admin_or_staff_required
def generate_notice():
    data = request.get_json() or {}
    errors = validate_generate_notice_request(data)
    if errors:
        return validation_error(errors)

    try:
        if data.get('sla_id') is not None:
            notice = escalation_service.generate_next_notice_for_sla(
                sla_id=data['sla_id'],
                user_id=get_jwt_identity(),
            )
            return success_response(
                data={
                    'generated_count': 1,
                    'generated_notice_ids': [notice.id],
                    'notice': escalation_service.get_escalation_notice_detail(notice.id, user_id=get_jwt_identity()),
                },
                message='Escalation notice generated successfully',
                status_code=201,
            )

        result = escalation_service.process_auto_escalations(user_id=get_jwt_identity())
        status_code = 201 if result['generated_count'] else 200
        return success_response(
            data=result,
            message='Escalation engine processed overdue deadlines',
            status_code=status_code,
        )
    except (escalation_service.EscalationError, notice_service.NoticeError) as exc:
        return error_response(exc.message, status_code=exc.status_code)
