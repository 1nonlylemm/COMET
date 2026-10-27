from flask import Blueprint

sla_bp = Blueprint('sla', __name__)

from . import routes  # noqa: E402, F401