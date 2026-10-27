from flask import Blueprint

workbook_workspaces_bp = Blueprint('workbook_workspaces', __name__)

from . import routes  # noqa: E402,F401
