from flask import Blueprint

regions_bp = Blueprint('regions', __name__, template_folder='../../templates')

from . import routes
