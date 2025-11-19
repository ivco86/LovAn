"""
Image operations - favorite, rename, open folder
"""

import os
import platform
import subprocess
from flask import jsonify, request
from werkzeug.utils import secure_filename

from shared import db, PHOTOS_DIR
from utils import get_full_filepath
from . import images_bp


@images_bp.route('/api/images/<int:image_id>/favorite', methods=['POST'])
def toggle_favorite(image_id):
    """Toggle favorite status"""
    new_status = db.toggle_favorite(image_id)

    return jsonify({
        'success': True,
        'image_id': image_id,
        'is_favorite': new_status
    })


@images_bp.route('/api/images/<int:image_id>/rename', methods=['POST'])
def rename_image(image_id):
    """Rename image file"""
    data = request.json
    new_filename = data.get('new_filename')

    if not new_filename:
        return jsonify({'error': 'new_filename is required'}), 400

    # Get current image
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    old_path = get_full_filepath(image['filepath'], PHOTOS_DIR)

    if not os.path.exists(old_path):
        return jsonify({'error': 'File not found on disk'}), 404

    # Sanitize filename
    new_filename = secure_filename(new_filename)

    # Keep same directory
    directory = os.path.dirname(old_path)
    new_path = os.path.join(directory, new_filename)

    # Check if target exists
    if os.path.exists(new_path):
        return jsonify({'error': 'File with that name already exists'}), 409

    try:
        # Rename file on disk
        os.rename(old_path, new_path)

        # Store relative path in database
        abs_photos_dir = os.path.abspath(PHOTOS_DIR)
        abs_new_path = os.path.abspath(new_path)
        relative_new_path = os.path.relpath(abs_new_path, abs_photos_dir)

        # Update database
        db.rename_image(image_id, relative_new_path, new_filename)

        return jsonify({
            'success': True,
            'image_id': image_id,
            'old_filename': image['filename'],
            'new_filename': new_filename,
            'new_filepath': new_path
        })
    except Exception as e:
        return jsonify({'error': f'Failed to rename: {str(e)}'}), 500


@images_bp.route('/api/images/<int:image_id>/open-folder', methods=['POST'])
def open_image_folder(image_id):
    """Open the folder containing the image in file explorer"""
    # Get image info
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    # Get full file path
    db_filepath = image.get('filepath', '')
    filepath = get_full_filepath(db_filepath, PHOTOS_DIR)

    # Debug logging
    print(f"[OPEN FOLDER DEBUG] Image ID: {image_id}")
    print(f"[OPEN FOLDER DEBUG] DB filepath: '{db_filepath}'")
    print(f"[OPEN FOLDER DEBUG] Full filepath: '{filepath}'")
    print(f"[OPEN FOLDER DEBUG] File exists: {os.path.exists(filepath)}")
    print(f"[OPEN FOLDER DEBUG] PHOTOS_DIR: '{PHOTOS_DIR}'")

    if not os.path.exists(filepath):
        print(f"[OPEN FOLDER DEBUG] ERROR: File not found!")
        return jsonify({
            'error': 'File not found on disk',
            'db_filepath': db_filepath,
            'full_filepath': filepath
        }), 404

    # Get directory path and absolute file path
    abs_filepath = os.path.abspath(filepath)
    folder_path = os.path.dirname(abs_filepath)
    print(f"[OPEN FOLDER DEBUG] Absolute filepath: '{abs_filepath}'")
    print(f"[OPEN FOLDER DEBUG] Folder to open: '{folder_path}'")

    try:
        system = platform.system()

        if system == 'Windows':
            # Windows: open Explorer and select the file (needs absolute path)
            print(f"[OPEN FOLDER DEBUG] Running: explorer /select, {abs_filepath}")
            subprocess.run(['explorer', '/select,', abs_filepath])
        elif system == 'Darwin':  # macOS
            # Mac: open Finder and select the file (needs absolute path)
            subprocess.run(['open', '-R', abs_filepath])
        else:  # Linux
            # Linux: open file manager in the folder
            # Try different file managers
            try:
                subprocess.run(['xdg-open', folder_path])
            except FileNotFoundError:
                try:
                    subprocess.run(['nautilus', folder_path])
                except FileNotFoundError:
                    try:
                        subprocess.run(['dolphin', folder_path])
                    except FileNotFoundError:
                        return jsonify({
                            'error': 'Could not detect file manager. Please install xdg-utils.',
                            'folder_path': folder_path
                        }), 500

        print(f"[OPEN FOLDER DEBUG] ✓ Command executed successfully")
        return jsonify({
            'success': True,
            'folder_path': folder_path
        })

    except Exception as e:
        return jsonify({
            'error': f'Failed to open folder: {str(e)}',
            'folder_path': folder_path
        }), 500
