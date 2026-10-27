from flask import request
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.utils.auth import admin_required
from app.services import lgu_service
from app.utils.response import (
    success_response, error_response, not_found_error, validation_error
)
from app.api.lgus.schemas import (
    validate_cluster_create, validate_cluster_update,
    validate_lgu_create, validate_lgu_update,
    validate_field_assignment, validate_staff_assignment,
    validate_lgu_toggle_active,
)

from . import lgu_bp


def _parse_bool_arg(name):
    value = request.args.get(name)
    if value is None:
        return None, None

    normalized = value.strip().lower()
    if normalized == 'true':
        return True, None
    if normalized == 'false':
        return False, None
    return None, {name: f'{name} must be true or false'}


# ── Cluster Endpoints ──────────────────────────────────────────────────────

@lgu_bp.route('/clusters', methods=['POST'])
@jwt_required()
@admin_required
def create_cluster():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_cluster_create(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        cluster = lgu_service.create_cluster(
            name=data['name'],
            description=data.get('description'),
            user_id=user_id,
        )
        return success_response(
            data=lgu_service._serialize_cluster(cluster),
            message='Cluster created successfully',
            status_code=201,
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/clusters', methods=['GET'])
@jwt_required()
def list_clusters():
    search = request.args.get('search')
    try:
        clusters = lgu_service.list_clusters(search=search, user_id=get_jwt_identity())
        return success_response(data=clusters)
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/clusters/<int:cluster_id>', methods=['GET'])
@jwt_required()
def get_cluster(cluster_id):
    try:
        cluster = lgu_service.get_cluster(cluster_id, user_id=get_jwt_identity())
        return success_response(data=lgu_service._serialize_cluster(cluster))
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/clusters/<int:cluster_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_cluster(cluster_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_cluster_update(data)
    if errors:
        return validation_error(errors)

    try:
        cluster = lgu_service.update_cluster(cluster_id, data, user_id=get_jwt_identity())
        return success_response(
            data=lgu_service._serialize_cluster(cluster),
            message='Cluster updated successfully',
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/clusters/<int:cluster_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def delete_cluster(cluster_id):
    try:
        result = lgu_service.delete_cluster(cluster_id, user_id=get_jwt_identity())
        return success_response(message=result['message'])
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


# ── LGU Endpoints ──────────────────────────────────────────────────────────

@lgu_bp.route('', methods=['POST'])
@jwt_required()
@admin_required
def create_lgu():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_lgu_create(data)
    if errors:
        return validation_error(errors)

    try:
        user_id = get_jwt_identity()
        lgu = lgu_service.create_lgu(
            name=data['name'],
            municipality=data['municipality'],
            province=data.get('province', 'Laguna'),
            cluster_id=data.get('cluster_id'),
            mayor_name=data.get('mayor_name'),
            mayor_email=data.get('mayor_email'),
            contact_person=data.get('contact_person'),
            contact_email=data.get('contact_email'),
            contact_phone=data.get('contact_phone'),
            user_id=user_id,
        )
        return success_response(
            data=lgu_service._serialize_lgu(lgu),
            message='LGU created successfully',
            status_code=201,
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('', methods=['GET'])
@jwt_required()
def list_lgus():
    search = request.args.get('search')
    cluster_id = request.args.get('cluster_id', type=int)
    is_active, bool_errors = _parse_bool_arg('is_active')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    if bool_errors:
        return validation_error(bool_errors)

    try:
        result = lgu_service.list_lgus(
            search=search, cluster_id=cluster_id,
            is_active=is_active, page=page, per_page=per_page,
            user_id=get_jwt_identity(),
        )
        return success_response(data=result['lgus'], meta={
            'page': result['page'],
            'per_page': result['per_page'],
            'total': result['total'],
            'pages': result['pages'],
        })
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/<int:lgu_id>', methods=['GET'])
@jwt_required()
def get_lgu(lgu_id):
    try:
        lgu = lgu_service.get_lgu(lgu_id, user_id=get_jwt_identity())
        return success_response(data=lgu_service._serialize_lgu(lgu))
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/<int:lgu_id>', methods=['PUT'])
@jwt_required()
@admin_required
def update_lgu(lgu_id):
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_lgu_update(data)
    if errors:
        return validation_error(errors)

    try:
        lgu = lgu_service.update_lgu(lgu_id, data, user_id=get_jwt_identity())
        return success_response(
            data=lgu_service._serialize_lgu(lgu),
            message='LGU updated successfully',
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/<int:lgu_id>/toggle-active', methods=['POST'])
@jwt_required()
@admin_required
def toggle_lgu_active(lgu_id):
    data = request.get_json(silent=True) or {}
    errors = validate_lgu_toggle_active(data)
    if errors:
        return validation_error(errors)

    try:
        lgu = lgu_service.toggle_lgu_active(
            lgu_id,
            user_id=get_jwt_identity(),
            is_active=data.get('is_active') if 'is_active' in data else None,
        )
        status = 'activated' if lgu.is_active else 'deactivated'
        return success_response(
            data=lgu_service._serialize_lgu(lgu),
            message=f'LGU {status} successfully',
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


# ── Staff Assignment Endpoints ─────────────────────────────────────────────

@lgu_bp.route('/staff-assignments', methods=['POST'])
@jwt_required()
@admin_required
def assign_staff():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_staff_assignment(data)
    if errors:
        return validation_error(errors)

    try:
        assignment = lgu_service.assign_staff_to_cluster(
            user_id=data['user_id'],
            cluster_id=data['cluster_id'],
            actor_user_id=get_jwt_identity(),
        )
        return success_response(
            data=lgu_service._serialize_assignment(assignment),
            message='User assigned to cluster successfully',
            status_code=201,
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/staff-assignments', methods=['GET'])
@jwt_required()
@admin_required
def list_assignments():
    cluster_id = request.args.get('cluster_id', type=int)
    user_id = request.args.get('user_id', type=int)
    is_active, bool_errors = _parse_bool_arg('is_active')
    if bool_errors:
        return validation_error(bool_errors)

    try:
        assignments = lgu_service.list_assignments(
            cluster_id=cluster_id, user_id=user_id, is_active=is_active,
            scope_type='cluster',
        )
        return success_response(data=assignments)
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/staff-assignments/<int:assignment_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def remove_assignment(assignment_id):
    try:
        result = lgu_service.remove_assignment(assignment_id, user_id=get_jwt_identity())
        return success_response(message=result['message'])
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/field-assignments', methods=['POST'])
@jwt_required()
@admin_required
def assign_field_officer():
    data = request.get_json()
    if not data:
        return error_response('No data provided', status_code=400)

    errors = validate_field_assignment(data)
    if errors:
        return validation_error(errors)

    try:
        assignment = lgu_service.assign_field_officer_to_lgu(
            user_id=data['user_id'],
            lgu_id=data['lgu_id'],
            actor_user_id=get_jwt_identity(),
        )
        return success_response(
            data=lgu_service._serialize_assignment(assignment),
            message='Field officer assigned to LGU successfully',
            status_code=201,
        )
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/field-assignments', methods=['GET'])
@jwt_required()
@admin_required
def list_field_assignments():
    lgu_id = request.args.get('lgu_id', type=int)
    user_id = request.args.get('user_id', type=int)
    is_active, bool_errors = _parse_bool_arg('is_active')
    if bool_errors:
        return validation_error(bool_errors)

    try:
        assignments = lgu_service.list_assignments(
            lgu_id=lgu_id, user_id=user_id, is_active=is_active,
            scope_type='lgu',
        )
        return success_response(data=assignments)
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)


@lgu_bp.route('/field-assignments/<int:assignment_id>', methods=['DELETE'])
@jwt_required()
@admin_required
def remove_field_assignment(assignment_id):
    try:
        result = lgu_service.remove_assignment(assignment_id, user_id=get_jwt_identity())
        return success_response(message=result['message'])
    except lgu_service.LguError as e:
        return error_response(e.message, status_code=e.status_code)
