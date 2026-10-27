from flask import g, has_request_context, jsonify, request


def success_response(data=None, message="Success", status_code=200, meta=None):
    response = {
        "success": True,
        "status": "success",
        "message": message,
    }
    if data is not None:
        response["data"] = data
    if meta is not None:
        response["meta"] = meta
    return jsonify(response), status_code


def error_response(message="An error occurred", errors=None, status_code=400, headers=None):
    response = {
        "success": False,
        "status": "error",
        "message": message,
    }
    if errors:
        response["errors"] = errors
    request_id = getattr(g, "request_id", None) if has_request_context() else None
    if request_id:
        response["request_id"] = request_id
    if headers:
        return jsonify(response), status_code, headers
    return jsonify(response), status_code


def paginate_response(query, schema_func=None, message="Success"):
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)
    per_page = min(per_page, 100)

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = paginated.items
    if schema_func:
        items = [schema_func(item) for item in items]

    return success_response(
        data=items,
        message=message,
        meta={
            "page": paginated.page,
            "per_page": paginated.per_page,
            "total_pages": paginated.pages,
            "total_items": paginated.total,
            "has_next": paginated.has_next,
            "has_prev": paginated.has_prev,
        },
    )


def validation_error(errors):
    return error_response(
        message="Validation failed",
        errors=errors,
        status_code=422,
    )


def not_found_error(entity="Resource", entity_id=None):
    identifier = f" with id {entity_id}" if entity_id else ""
    return error_response(
        message=f"{entity}{identifier} not found",
        status_code=404,
    )


def unauthorized_error(message="Authentication required", headers=None):
    return error_response(message=message, status_code=401, headers=headers)


def forbidden_error(message="You do not have permission to perform this action", headers=None):
    return error_response(message=message, status_code=403, headers=headers)
