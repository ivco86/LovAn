"""
Images module - Blueprint registration and route imports
"""

from flask import Blueprint

# Create blueprint
images_bp = Blueprint('images', __name__)

# Import all routes to register them with blueprint
from . import crud
from . import files
from . import operations
from . import analysis
from . import search
from . import tags
from . import ingestion

__all__ = ['images_bp']

