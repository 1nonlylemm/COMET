from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import global_search_service
from app.utils.auth import admin_or_staff_or_field_required
from app.utils.response import success_response, validation_error
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg

from . import search_bp


@search_bp.route('', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def global_search():
    query = request.args.get('q') or request.args.get('search')
    if not query or not str(query).strip():
        return validation_error({'q': 'Search query is required.'})

    try:
        result = global_search_service.global_search(
            query,
            types=request.args.get('types'),
            per_type=request.args.get('per_type', 5, type=int),
            fiscal_year=parse_fiscal_year_arg(request.args),
            user_id=get_jwt_identity(),
        )
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    return success_response(data=result)
