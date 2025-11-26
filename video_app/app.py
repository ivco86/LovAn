#!/usr/bin/env python3
"""
Video App - Standalone Video Management Application
Runs on port 5001

This is a separate application for video management, including:
- YouTube/TikTok/Facebook video downloads
- Subtitle management
- Video bookmarks and notes
- AI-powered highlight generation
- Translation and vocabulary
"""

import os
import sys
import logging

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify, send_from_directory
from flask_cors import CORS

# Import shared configuration
from shared import PHOTOS_DIR, DATA_DIR, DATABASE_PATH, LM_STUDIO_URL

# Import routes
from routes import videos_bp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Enable CORS for cross-origin requests
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Register blueprints
app.register_blueprint(videos_bp)


# ============ FRONTEND ROUTES ============

@app.route('/')
def index():
    """Serve main application page"""
    return render_template('index.html')


# ============ STATIC FILES ============

@app.route('/favicon.ico')
def favicon():
    """Serve favicon"""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <text y="75" font-size="75">🎬</text>
    </svg>'''
    return svg, 200, {'Content-Type': 'image/svg+xml'}


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory('static', filename)


@app.route('/photos/<path:filename>')
def serve_photos(filename):
    """Serve video/image files from photos directory"""
    return send_from_directory(PHOTOS_DIR, filename)


# ============ ERROR HANDLERS ============

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


# ============ MAIN ============

if __name__ == '__main__':
    # Ensure directories exist
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

    print(f"""
╔═══════════════════════════════════════════╗
║        Video App Starting...              ║
╚═══════════════════════════════════════════╝

📁 Photos Directory: {PHOTOS_DIR}
🤖 LM Studio URL: {LM_STUDIO_URL}
💾 Database: {DATABASE_PATH}

🌐 Open: http://localhost:5001

Press Ctrl+C to stop
    """)

    app.run(
        host='0.0.0.0',
        port=5001,
        debug=True
    )
