from flask import Blueprint

lgu_bp = Blueprint('lgus', __name__)

from . import routes