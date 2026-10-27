from flask import Blueprint


monitoring_bp = Blueprint('monitoring', __name__)


from . import routes  # noqa: E402,F401
from . import phase2a_routes  # noqa: E402,F401
from . import phase2b_routes  # noqa: E402,F401
