from flask import Blueprint


completion_bp = Blueprint('completion', __name__)


from . import routes  # noqa: E402,F401
from . import phase2c_routes  # noqa: E402,F401
