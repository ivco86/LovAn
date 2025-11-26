"""
Shared objects and configuration for Video App
Standalone video management application
"""

import os

# Get the directory where this file is located
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configuration from environment variables (with defaults relative to parent LovAn directory)
PHOTOS_DIR = os.path.abspath(os.environ.get('PHOTOS_DIR', os.path.join(BASE_DIR, 'photos')))
DATA_DIR = os.path.abspath(os.environ.get('DATA_DIR', os.path.join(BASE_DIR, 'data')))
LM_STUDIO_URL = os.environ.get('LM_STUDIO_URL', 'http://localhost:1234')
DATABASE_PATH = os.path.abspath(os.environ.get('DATABASE_PATH', os.path.join(DATA_DIR, 'gallery.db')))

# Video-specific directories
KEYFRAMES_DIR = os.path.join(DATA_DIR, 'youtube_keyframes')
SUBTITLES_DIR = os.path.join(DATA_DIR, 'youtube_subtitles')
HIGHLIGHTS_DIR = os.path.join(DATA_DIR, 'highlights')

# Ensure directories exist
for directory in [PHOTOS_DIR, DATA_DIR, KEYFRAMES_DIR, SUBTITLES_DIR, HIGHLIGHTS_DIR]:
    os.makedirs(directory, exist_ok=True)
