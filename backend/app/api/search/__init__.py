from flask import Blueprint

search_bp = Blueprint('search', __name__)

from app.api.search import routes  # noqa: E402,F401
