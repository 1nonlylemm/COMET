from io import BytesIO
from flask import current_app, request, send_file
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services import access_service, reporting_pdf_service, reporting_service
from app.utils.auth import admin_or_staff_required
from app.utils.fiscal_year import FiscalYearError, parse_fiscal_year_arg
from app.utils.response import error_response, success_response, validation_error

from . import reports_bp


@reports_bp.route('/monitoring-updates', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def monitoring_updates_report():
    try:
        data = reporting_service.get_monitoring_updates_report(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
            program_id=request.args.get('program_id', type=int),
            cluster_id=request.args.get('cluster_id', type=int),
            lgu_id=request.args.get('lgu_id', type=int),
            status=request.args.get('status'),
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@reports_bp.route('/analytics/deep-dive', methods=['GET'])
@jwt_required()
@admin_or_staff_required
def deep_dive_analytics():
    try:
        data = reporting_service.get_deep_dive_analytics(
            user_id=get_jwt_identity(),
            fiscal_year=parse_fiscal_year_arg(request.args),
            program_id=request.args.get('program_id', type=int),
            cluster_id=request.args.get('cluster_id', type=int),
            lgu_id=request.args.get('lgu_id', type=int),
            status=request.args.get('status'),
        )
        return success_response(data=data)
    except FiscalYearError as exc:
        return validation_error({'fiscal_year': str(exc)})
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)


@reports_bp.route('/monitoring-updates/export-pdf', methods=['POST'])
@jwt_required()
@admin_or_staff_required
def export_monitoring_updates_pdf():
    try:
        payload = request.get_json(silent=True)
        if payload is not None and not isinstance(payload, dict):
            return validation_error({'payload': 'Payload must be an object/dictionary.'})
        payload = payload or {}

        tabs_raw = payload.get('tabs')
        if tabs_raw is None:
            tabs = ['monitoring', 'documents']
        elif not isinstance(tabs_raw, list) or not tabs_raw:
            return validation_error({'tabs': 'Select one or more valid report sections.'})
        else:
            # Map/normalize legacy sections ('analytics' -> 'monitoring' + 'documents', 'risk' -> 'documents')
            normalized_tabs = []
            for tab in tabs_raw:
                if tab in ('monitoring', 'documents'):
                    if tab not in normalized_tabs:
                        normalized_tabs.append(tab)
                elif tab == 'analytics':
                    if 'monitoring' not in normalized_tabs:
                        normalized_tabs.append('monitoring')
                    if 'documents' not in normalized_tabs:
                        normalized_tabs.append('documents')
                elif tab == 'risk':
                    if 'documents' not in normalized_tabs:
                        normalized_tabs.append('documents')
                else:
                    return validation_error({'tabs': f'Invalid report section: {tab}'})
            if not normalized_tabs:
                return validation_error({'tabs': 'Select one or more valid report sections.'})
            tabs = normalized_tabs

        scope = payload.get('scope') or 'filtered'
        risk_detail = payload.get('risk_detail') or 'executive'
        orientation = payload.get('orientation') or 'landscape'
        record_detail = payload.get('record_detail', 'summary')

        filters_raw = payload.get('filters')
        if filters_raw is not None and not isinstance(filters_raw, dict):
            return validation_error({'filters': 'Filters must be an object/dictionary.'})
        filters = dict(filters_raw or {})

        if scope not in ('filtered', 'all'):
            return validation_error({'scope': 'Must be "filtered" or "all"'})
        if risk_detail not in ('executive', 'comprehensive'):
            return validation_error({'risk_detail': 'Must be "executive" or "comprehensive"'})
        if orientation not in ('landscape', 'portrait'):
            return validation_error({'orientation': 'Must be "landscape" or "portrait"'})
        if record_detail not in ('summary', 'full'):
            return validation_error({'record_detail': 'Must be "summary" or "full"'})

        try:
            fiscal_year = parse_fiscal_year_arg(filters)
        except FiscalYearError as exc:
            return validation_error({'fiscal_year': str(exc)})
        filters['fiscal_year'] = fiscal_year

        if 'project_ids' in filters:
            ids = filters['project_ids']
            if not isinstance(ids, list) or any(type(value) is not int or value <= 0 for value in ids):
                return validation_error({'project_ids': 'Must be a list of positive integer project IDs.'})
            filters['project_ids'] = list(dict.fromkeys(ids))

        if not isinstance(tabs, list) or not tabs or any(tab not in ('monitoring', 'documents') for tab in tabs):
            return validation_error({'tabs': 'Select one or more valid report sections.'})
        if 'search' in filters and not isinstance(filters['search'], str):
            return validation_error({'search': 'Search must be text.'})

        for int_field in ('program_id', 'cluster_id', 'lgu_id'):
            val = filters.get(int_field)
            if val not in (None, ''):
                try:
                    filters[int_field] = int(val)
                except (TypeError, ValueError):
                    return validation_error({int_field: f'{int_field} must be an integer.'})
            elif int_field in filters:
                filters[int_field] = None

        include_appendix = payload.get('include_appendix')

        pdf_bytes, filename = reporting_pdf_service.generate_reports_analytics_pdf(
            user_id=get_jwt_identity(),
            tabs=tabs,
            scope=scope,
            risk_detail=risk_detail,
            orientation=orientation,
            record_detail=record_detail,
            include_appendix=include_appendix,
            filters=filters,
        )

        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename,
        )
    except access_service.AccessError as exc:
        return error_response(exc.message, status_code=exc.status_code)
    except Exception as exc:
        current_app.logger.exception('Failed to generate reports PDF export: %s', exc)
        return error_response(f'Failed to generate PDF report: {exc}', status_code=500)

