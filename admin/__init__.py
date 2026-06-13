from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Import modules to register routes
from . import auth, routes, api
