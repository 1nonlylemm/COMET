from flask import Blueprint

batch_imports_bp = Blueprint('batch_imports', __name__)

from . import routes  # noqa: E402,F401
