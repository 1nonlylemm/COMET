from flask import Blueprint


library_bp = Blueprint('library', __name__)


from . import routes  # noqa: E402,F401
