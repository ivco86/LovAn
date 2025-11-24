"""
AI module - EXIF metadata and semantic search with CLIP embeddings
"""

from flask import Blueprint

# Create blueprint
ai_bp = Blueprint('ai', __name__)

# Import all routes to register them with blueprint
from . import exif
from . import embeddings
from . import chat

__all__ = ['ai_bp']
