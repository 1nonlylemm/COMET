"""Phase 2C Completion Matrix API routes.

Exposes the five closeout document rows (Final SWA, FIR, COFA, Final
SORD, Proof of Return of Funds) shown on the existing Completion page.
Workflow transitions (submit/verify/staff-approve/provincial-approve/
return) reuse the existing Phase 1 endpoints under
`/api/projects/requirements/<id>/workflow/*` via each record's
`project_requirement_id` -- no duplicate transition routes are added
here, matching the Phase 2A/2B pattern exactly. System Administrators
have no operational access to these routes (enforced by
`admin_or_staff_or_field_required`, which excludes `system_admin`).
"""
from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import completion_documents_service
from app.utils.auth import admin_or_staff_or_field_required, admin_or_staff_required, field_officer_required
from app.utils.response import error_response, success_response

from . import completion_bp


def _error(exc):
    return error_response(exc.message, status_code=exc.status_code)


@completion_bp.route('/projects/<int:project_id>/documents', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def list_completion_documents(project_id):
    try:
        return success_response(data=completion_documents_service.list_completion_documents(
            project_id, user_id=get_jwt_identity(),
        ))
    except completion_documents_service.CompletionDocumentError as exc:
        return _error(exc)


@completion_bp.route('/projects/<int:project_id>/documents/<string:document_type>', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def get_completion_document(project_id, document_type):
    try:
        return success_response(data=completion_documents_service.get_completion_document(
            project_id, document_type, user_id=get_jwt_identity(),
        ))
    except completion_documents_service.CompletionDocumentError as exc:
        return _error(exc)


@completion_bp.route('/projects/<int:project_id>/documents/<string:document_type>/applicability', methods=['PUT'])
@jwt_required()
@admin_or_staff_required
def update_completion_document_applicability(project_id, document_type):
    data = request.get_json() or {}
    try:
        result = completion_documents_service.update_document_applicability(
            project_id, document_type, data, user_id=get_jwt_identity(),
        )
        return success_response(data=result, message='Applicability updated successfully.')
    except completion_documents_service.CompletionDocumentError as exc:
        return _error(exc)


@completion_bp.route('/projects/<int:project_id>/documents/<string:document_type>/metadata', methods=['PUT'])
@jwt_required()
@admin_or_staff_or_field_required
def update_completion_document_metadata(project_id, document_type):
    data = request.get_json() or {}
    try:
        result = completion_documents_service.update_document_metadata(
            project_id, document_type, data, user_id=get_jwt_identity(),
        )
        return success_response(data=result, message='Document metadata updated successfully.')
    except completion_documents_service.CompletionDocumentError as exc:
        return _error(exc)
