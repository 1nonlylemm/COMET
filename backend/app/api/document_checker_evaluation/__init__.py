from flask import Blueprint


document_checker_evaluation_bp = Blueprint('document_checker_evaluation', __name__)


from . import routes  # noqa: E402,F401
