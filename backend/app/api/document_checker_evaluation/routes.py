from flask import request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.constants.roles import SYSTEM_ADMIN
from app.extensions import db
from app.models import DocumentCheckerEvaluationCase, DocumentCheckerEvaluationResult, User
from app.services import document_compliance_evaluation_service as evaluation_service
from app.utils.auth import checker_accuracy_report_reader_required, system_admin_required
from app.utils.response import error_response, success_response

from . import document_checker_evaluation_bp


@document_checker_evaluation_bp.route('/datasets', methods=['GET'])
@jwt_required()
@system_admin_required
def list_datasets():
    datasets = evaluation_service.list_datasets({
        'status': request.args.get('status'),
        'dataset_type': request.args.get('dataset_type'),
    })
    return success_response(data=[evaluation_service.serialize_dataset(item) for item in datasets])


@document_checker_evaluation_bp.route('/datasets', methods=['POST'])
@jwt_required()
@system_admin_required
def create_dataset():
    try:
        dataset = evaluation_service.create_dataset(
            request.get_json() or {},
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_dataset(dataset),
            message='Checker evaluation dataset created.',
            status_code=201,
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/datasets/<int:dataset_id>', methods=['GET'])
@jwt_required()
@system_admin_required
def get_dataset(dataset_id):
    try:
        dataset = evaluation_service.get_dataset(dataset_id)
        payload = evaluation_service.serialize_dataset(dataset)
        payload['cases'] = [
            evaluation_service.serialize_case(case)
            for case in dataset.cases.order_by(DocumentCheckerEvaluationCase.id.asc()).all()
        ]
        return success_response(data=payload)
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/datasets/<int:dataset_id>/cases', methods=['POST'])
@jwt_required()
@system_admin_required
def add_case(dataset_id):
    try:
        case = evaluation_service.add_case(
            dataset_id,
            request.get_json() or {},
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_case(case),
            message='Checker evaluation case added.',
            status_code=201,
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/datasets/<int:dataset_id>/status', methods=['PATCH'])
@jwt_required()
@system_admin_required
def update_dataset_status(dataset_id):
    try:
        dataset = evaluation_service.update_dataset_status(
            dataset_id,
            (request.get_json() or {}).get('status'),
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_dataset(dataset),
            message='Checker evaluation dataset status updated.',
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/datasets/import-manifest', methods=['POST'])
@jwt_required()
@system_admin_required
def import_manifest():
    try:
        payload = evaluation_service.import_manifest(
            request.get_json() or {},
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=payload,
            message='Checker evaluation manifest imported.',
            status_code=201,
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/gold-label-template/source-results', methods=['GET'])
@jwt_required()
@system_admin_required
def gold_label_source_results():
    payload = evaluation_service.list_gold_label_source_results({
        'limit': request.args.get('limit', type=int),
    })
    return success_response(data=payload)


@document_checker_evaluation_bp.route('/gold-label-template', methods=['POST'])
@jwt_required()
@system_admin_required
def gold_label_template():
    try:
        payload = evaluation_service.build_gold_label_template(request.get_json() or {})
        return success_response(
            data=payload,
            message='Gold label template generated.',
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/gold-label-template/sample', methods=['GET'])
@jwt_required()
@system_admin_required
def completed_gold_label_sample():
    return success_response(
        data=evaluation_service.build_completed_gold_label_sample(),
        message='Completed gold label sample generated.',
    )


@document_checker_evaluation_bp.route('/gold-label-template/reviewer-guide', methods=['GET'])
@jwt_required()
@system_admin_required
def gold_label_reviewer_guide():
    return success_response(
        data=evaluation_service.build_gold_label_reviewer_guide(),
        message='Reviewer gold-label guide exported.',
    )


@document_checker_evaluation_bp.route('/runs', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def list_runs():
    runs = evaluation_service.list_runs({
        'dataset_id': request.args.get('dataset_id', type=int),
        'status': request.args.get('status'),
    })
    return success_response(data=[evaluation_service.serialize_run(item) for item in runs])


@document_checker_evaluation_bp.route('/released-reports', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def list_released_reports():
    releases = evaluation_service.list_released_reports({
        'dataset_id': request.args.get('dataset_id', type=int),
        'run_id': request.args.get('run_id', type=int),
        'limit': request.args.get('limit', type=int),
    })
    return success_response(data=[evaluation_service.serialize_released_report(item) for item in releases])


@document_checker_evaluation_bp.route('/runs', methods=['POST'])
@jwt_required()
@system_admin_required
def create_run():
    data = request.get_json() or {}
    dataset_id = data.get('dataset_id')
    if dataset_id is None:
        return error_response('dataset_id is required.', status_code=422)
    try:
        run = evaluation_service.create_run(
            dataset_id,
            data,
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_run(run),
            message='Checker evaluation run created.',
            status_code=201,
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def get_run(run_id):
    try:
        run = evaluation_service.get_run(run_id)
        return success_response(data=evaluation_service.serialize_run(run))
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>/start', methods=['POST'])
@jwt_required()
@system_admin_required
def start_run(run_id):
    try:
        run = evaluation_service.run_evaluation(run_id, user_id=get_jwt_identity())
        return success_response(
            data=evaluation_service.serialize_run(run),
            message='Checker evaluation run completed.',
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>/release', methods=['POST'])
@jwt_required()
@system_admin_required
def release_run_report(run_id):
    try:
        release = evaluation_service.release_run_report(
            run_id,
            request.get_json(silent=True) or {},
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_released_report(release),
            message='Checker benchmark report released for operational viewing.',
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>/release/revoke', methods=['POST'])
@jwt_required()
@system_admin_required
def revoke_run_report(run_id):
    try:
        release = evaluation_service.revoke_run_report(
            run_id,
            request.get_json(silent=True) or {},
            user_id=get_jwt_identity(),
        )
        return success_response(
            data=evaluation_service.serialize_released_report(release),
            message='Checker benchmark report unpublished from operational viewing.',
        )
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>/results', methods=['GET'])
@jwt_required()
@system_admin_required
def list_run_results(run_id):
    try:
        run = evaluation_service.get_run(run_id)
        results = run.results.order_by(DocumentCheckerEvaluationResult.id.asc()).all()
        return success_response(data=[evaluation_service.serialize_result(item) for item in results])
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/runs/<int:run_id>/report', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def get_run_report(run_id):
    try:
        if _current_role() != SYSTEM_ADMIN and not evaluation_service.is_run_report_released(run_id):
            return error_response(
                'Benchmark report has not been released for operational viewing.',
                status_code=403,
            )
        return success_response(data=evaluation_service.build_run_report(run_id))
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/results/<int:result_id>', methods=['GET'])
@jwt_required()
@system_admin_required
def get_result(result_id):
    try:
        result = evaluation_service.get_result(result_id)
        return success_response(data=evaluation_service.serialize_result(result))
    except evaluation_service.DocumentCheckerEvaluationError as exc:
        return _evaluation_error(exc)


@document_checker_evaluation_bp.route('/summary', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def summary():
    data = evaluation_service.get_summary({
        'dataset_id': request.args.get('dataset_id', type=int),
    })
    return success_response(data=data)


@document_checker_evaluation_bp.route('/trends', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def trends():
    snapshots = evaluation_service.list_metric_trends({
        'dataset_id': request.args.get('dataset_id', type=int),
        'limit': request.args.get('limit', type=int),
    })
    return success_response(data=[evaluation_service.serialize_metric_snapshot(item) for item in snapshots])


@document_checker_evaluation_bp.route('/failures', methods=['GET'])
@jwt_required()
@system_admin_required
def failures():
    results = evaluation_service.list_failed_results({
        'dataset_id': request.args.get('dataset_id', type=int),
        'run_id': request.args.get('run_id', type=int),
        'limit': request.args.get('limit', type=int),
    })
    return success_response(data=[evaluation_service.serialize_result(item) for item in results])


@document_checker_evaluation_bp.route('/reviewer-feedback', methods=['GET'])
@jwt_required()
@checker_accuracy_report_reader_required
def reviewer_feedback():
    return success_response(data=evaluation_service.get_reviewer_feedback_summary())


def _evaluation_error(exc):
    return error_response(exc.message, errors=exc.details, status_code=exc.status_code)


def _current_role():
    identity = get_jwt_identity()
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None
    user = db.session.get(User, user_id)
    return user.role if user else None
