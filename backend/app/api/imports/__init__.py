from flask import Blueprint


imports_bp = Blueprint('imports', __name__)


from . import routes  # noqa: E402,F401
