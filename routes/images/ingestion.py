"""
Ingestion - upload files, scan directory for new images/videos
"""

import os
from pathlib import Path
from flask import jsonify, request
from werkzeug.utils import secure_filename
from PIL import Image

from shared import db, PHOTOS_DIR
from utils import ALL_MEDIA_FORMATS, VIDEO_FORMATS
from . import images_bp


@images_bp.route('/api/scan', methods=['POST'])
def scan_directory():
    """Scan photos directory for new images and videos"""
    if not os.path.exists(PHOTOS_DIR):
        return jsonify({'error': f'Photos directory not found: {PHOTOS_DIR}'}), 404

    found_media = []
    new_media = []
    skipped = 0

    # Walk through directory
    for root, dirs, files in os.walk(PHOTOS_DIR):
        for filename in files:
            ext = Path(filename).suffix.lower()

            if ext in ALL_MEDIA_FORMATS:
                full_filepath = os.path.join(root, filename)
                found_media.append(full_filepath)

                try:
                    # Store relative path from PHOTOS_DIR
                    abs_photos_dir = os.path.abspath(PHOTOS_DIR)
                    abs_filepath = os.path.abspath(full_filepath)
                    relative_path = os.path.relpath(abs_filepath, abs_photos_dir)

                    file_size = os.path.getsize(full_filepath)
                    width = None
                    height = None
                    media_type = 'video' if ext in VIDEO_FORMATS else 'image'

                    # Get dimensions for images only
                    if media_type == 'image':
                        img = Image.open(full_filepath)
                        width, height = img.size
                        img.close()

                    # Try to add to database with relative path
                    image_id = db.add_image(
                        filepath=relative_path,
                        filename=filename,
                        width=width,
                        height=height,
                        file_size=file_size,
                        media_type=media_type
                    )

                    if image_id:
                        new_media.append({
                            'id': image_id,
                            'filename': filename,
                            'filepath': full_filepath,
                            'media_type': media_type
                        })
                    else:
                        skipped += 1

                except Exception as e:
                    print(f"Error processing {full_filepath}: {e}")
                    skipped += 1

    return jsonify({
        'success': True,
        'found': len(found_media),
        'new': len(new_media),
        'skipped': skipped,
        'images': new_media
    })


@images_bp.route('/api/upload', methods=['POST'])
def upload_image():
    """Upload image or video file"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Check file extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALL_MEDIA_FORMATS:
        return jsonify({'error': f'Unsupported format: {ext}'}), 400

    try:
        # Sanitize filename
        filename = secure_filename(file.filename)

        # Ensure photos directory exists
        os.makedirs(PHOTOS_DIR, exist_ok=True)

        # Save file
        filepath = os.path.join(PHOTOS_DIR, filename)

        # Handle duplicates
        counter = 1
        base_name = Path(filename).stem
        while os.path.exists(filepath):
            filename = f"{base_name}_{counter}{ext}"
            filepath = os.path.join(PHOTOS_DIR, filename)
            counter += 1

        file.save(filepath)

        # Get file info
        file_size = os.path.getsize(filepath)
        width = None
        height = None
        media_type = 'video' if ext in VIDEO_FORMATS else 'image'

        # Get dimensions for images only
        if media_type == 'image':
            img = Image.open(filepath)
            width, height = img.size
            img.close()

        # Add to database with just filename (relative to PHOTOS_DIR)
        image_id = db.add_image(
            filepath=filename,
            filename=filename,
            width=width,
            height=height,
            file_size=file_size,
            media_type=media_type
        )

        return jsonify({
            'success': True,
            'image_id': image_id,
            'filename': filename,
            'filepath': filepath,
            'media_type': media_type
        })

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500
