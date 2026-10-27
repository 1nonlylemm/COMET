"""Shared document workflow transition endpoints.

These routes expose the Phase 1 shared state machine
(Draft -> Submitted -> Under Verification -> Staff Approved ->
Pending Provincial Approval -> Approved, plus Returned for Revision ->
Resubmitted) for any ProjectRequirement tagged with a document_category.

Role enforcement is performed in `requirement_workflow_service` (backend),
not just via route decorators, so these decorators are a first line of
defense only.
"""
from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.utils.auth import admin_or_staff_or_field_required
from app.services import access_service, requirement_workflow_service
from app.utils.response import success_response, error_response

from . import projects_bp


def _workflow_error_response(error):
    return error_response(error.message, status_code=error.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/workflow', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_requirement_workflow(requirement_id):
    try:
        data = requirement_workflow_service.get_requirement_workflow(
            requirement_id,
            user_id=get_jwt_identity(),
        )
        return success_response(data=data)
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/workflow/submit', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def submit_requirement_workflow(requirement_id):
    data = request.get_json(silent=True) or {}
    try:
        requirement = requirement_workflow_service.submit_requirement(
            requirement_id,
            user_id=get_jwt_identity(),
            note=data.get('note'),
        )
        return success_response(
            data=requirement_workflow_service._serialize_requirement_snapshot(requirement),
            message='Document submitted successfully.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/workflow/verify', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def verify_requirement_workflow(requirement_id):
    data = request.get_json(silent=True) or {}
    try:
        requirement = requirement_workflow_service.verify_requirement(
            requirement_id,
            user_id=get_jwt_identity(),
            note=data.get('note'),
        )
        return success_response(
            data=requirement_workflow_service._serialize_requirement_snapshot(requirement),
            message='Document moved to Under Verification.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/workflow/staff-approve', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def staff_approve_requirement_workflow(requirement_id):
    data = request.get_json(silent=True) or {}
    try:
        requirement = requirement_workflow_service.staff_approve_requirement(
            requirement_id,
            user_id=get_jwt_identity(),
            note=data.get('note'),
        )
        return success_response(
            data=requirement_workflow_service._serialize_requirement_snapshot(requirement),
            message='Document staff-approved and forwarded for Provincial Admin approval.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/workflow/provincial-approve', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def provincial_approve_requirement_workflow(requirement_id):
    data = request.get_json(silent=True) or {}
    try:
        requirement = requirement_workflow_service.provincial_approve_requirement(
            requirement_id,
            user_id=get_jwt_identity(),
            note=data.get('note'),
        )
        return success_response(
            data=requirement_workflow_service._serialize_requirement_snapshot(requirement),
            message='Document approved.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/workflow/return', methods=['POST'])
@jwt_required()
@admin_or_staff_or_field_required
def return_requirement_workflow(requirement_id):
    data = request.get_json(silent=True) or {}
    user_id = get_jwt_identity()
    try:
        requirement = requirement_workflow_service.return_requirement(
            requirement_id,
            user_id=user_id,
            reason=data.get('reason') or data.get('note') or data.get('review_notes'),
            deficiencies=data.get('deficiencies'),
        )
        snapshot = requirement_workflow_service._serialize_requirement_snapshot(requirement)
        deficiencies = requirement_workflow_service.list_deficiencies(
            requirement_id,
            user_id=user_id,
            state='all',
        )
        snapshot['deficiencies'] = deficiencies
        count_desc = f' with {len(deficiencies)} recorded deficiency item(s)' if deficiencies else ''
        return success_response(
            data=snapshot,
            message=f'Document returned for revision{count_desc}.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)
    except access_service.AccessError as e:
        return error_response(e.message, status_code=e.status_code)


@projects_bp.route('/requirements/<int:requirement_id>/deficiencies', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_requirement_deficiencies(requirement_id):
    state = request.args.get('state')
    try:
        data = requirement_workflow_service.list_deficiencies(
            requirement_id,
            user_id=get_jwt_identity(),
            state=state,
        )
        return success_response(data=data)
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)


@projects_bp.route('/requirements/<int:requirement_id>/deficiencies/<int:deficiency_id>/resolve', methods=['PATCH'])
@jwt_required()
@admin_or_staff_or_field_required
def resolve_requirement_deficiency(requirement_id, deficiency_id):
    data = request.get_json(silent=True) or {}
    resolution_state = data.get('resolution_state', 'resolved')
    resolution_notes = data.get('resolution_notes')
    try:
        data = requirement_workflow_service.resolve_deficiency(
            requirement_id,
            deficiency_id,
            user_id=get_jwt_identity(),
            resolution_state=resolution_state,
            resolution_notes=resolution_notes,
        )
        return success_response(
            data=data,
            message=f'Deficiency successfully marked as {resolution_state}.',
        )
    except requirement_workflow_service.WorkflowError as e:
        return _workflow_error_response(e)

