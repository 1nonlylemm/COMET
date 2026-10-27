from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import access_service, dashboard_service
from app.utils.auth import admin_or_staff_or_field_required
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.utils.response import error_response, success_response, validation_error

from . import dashboard_bp


@dashboard_bp.route('/operations', methods=['GET'])
@jwt_required()
@admin_or_staff_or_field_required
def operations_dashboard():
    try:
        fiscal_year = parse_fiscal_year_arg(request.args)
        data = dashboard_service.get_operations_dashboard(
            user_id=get_jwt_identity(),
            fiscal_year=fiscal_year,
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)
