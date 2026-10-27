from flask import Blueprint

programs_bp = Blueprint('programs', __name__, url_prefix='/api/programs')

from app.api.programs import routes  # noqa: E402,F401