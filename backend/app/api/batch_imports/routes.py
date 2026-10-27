from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import batch_import_service
from app.utils.auth import admin_required
from app.utils.response import error_response, success_response

from . import batch_imports_bp


@batch_imports_bp.route('/targets', methods=['GET'])
@jwt_required()
@admin_required
def list_targets():
    return success_response(data=batch_import_service.list_targets())


@batch_imports_bp.route('/<string:target>', methods=['POST'])
@jwt_required()
@admin_required
def import_target(target):
    dry_run = str(request.form.get('dry_run', 'true')).lower() not in {'false', '0', 'no'}
    try:
        result = batch_import_service.process_upload(
            target=target,
            upload=request.files.get('file'),
            user_id=get_jwt_identity(),
            dry_run=dry_run,
        )
        message = 'Batch import preview prepared' if dry_run else 'Batch import completed'
        return success_response(data=result, message=message)
    except batch_import_service.BatchImportError as exc:
        return error_response(exc.message, errors=exc.errors, status_code=exc.status_code)

