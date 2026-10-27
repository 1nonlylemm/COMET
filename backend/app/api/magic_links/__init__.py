from flask import Blueprint


magic_links_bp = Blueprint('magic_links', __name__)


from . import routes
