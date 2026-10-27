from flask import Blueprint


system_admin_bp = Blueprint('system_admin', __name__)

from . import routes  # noqa: E402,F401
