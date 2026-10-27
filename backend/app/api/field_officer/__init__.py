from flask import Blueprint

field_officer_bp = Blueprint('field_officer', __name__)

from app.api.field_officer import routes  # noqa: E402,F401
