from flask import Blueprint

projects_bp = Blueprint('projects', __name__)

from app.api.projects import routes  # noqa: E402,F401
from app.api.projects import workflow_routes  # noqa: E402,F401