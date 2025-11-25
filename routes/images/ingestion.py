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
from image_hash_utils import compute_phash, compute_phash_from_bytes
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
                        # Compute and store perceptual hash for images
                        if media_type == 'image':
                            phash = compute_phash(full_filepath)
                            if phash:
                                db.update_image_phash(image_id, phash)

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

        # Compute perceptual hash for images before adding to DB
        phash = None
        duplicate_of = None
        if media_type == 'image':
            phash = compute_phash(filepath)
            # Check if this hash already exists (duplicate detection)
            if phash:
                existing = db.check_phash_exists(phash)
                if existing:
                    duplicate_of = existing

        # Add to database with just filename (relative to PHOTOS_DIR)
        image_id = db.add_image(
            filepath=filename,
            filename=filename,
            width=width,
            height=height,
            file_size=file_size,
            media_type=media_type
        )

        # Store the phash
        if phash and image_id:
            db.update_image_phash(image_id, phash)

        response = {
            'success': True,
            'image_id': image_id,
            'filename': filename,
            'filepath': filepath,
            'media_type': media_type
        }

        # Include duplicate warning if found
        if duplicate_of:
            response['duplicate_of'] = {
                'id': duplicate_of['id'],
                'filename': duplicate_of['filename']
            }
            response['is_duplicate'] = True

        return jsonify(response)

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@images_bp.route('/api/duplicates', methods=['GET'])
def find_duplicates():
    """Find all duplicate images based on perceptual hash"""
    try:
        duplicates = db.find_duplicate_phashes()
        return jsonify({
            'success': True,
            'duplicate_groups': len(duplicates),
            'duplicates': duplicates
        })
    except Exception as e:
        return jsonify({'error': f'Failed to find duplicates: {str(e)}'}), 500


@images_bp.route('/api/duplicates/compute-hashes', methods=['POST'])
def compute_missing_hashes():
    """Compute perceptual hashes for images that don't have them"""
    try:
        limit = request.args.get('limit', 100, type=int)
        images = db.get_images_without_phash(limit)

        computed = 0
        failed = 0

        for img in images:
            try:
                filepath = os.path.join(PHOTOS_DIR, img['filepath'])
                if os.path.exists(filepath):
                    phash = compute_phash(filepath)
                    if phash:
                        db.update_image_phash(img['id'], phash)
                        computed += 1
                    else:
                        failed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"Error computing hash for {img['filepath']}: {e}")
                failed += 1

        return jsonify({
            'success': True,
            'computed': computed,
            'failed': failed,
            'remaining': len(db.get_images_without_phash(1))
        })
    except Exception as e:
        return jsonify({'error': f'Failed to compute hashes: {str(e)}'}), 500


@images_bp.route('/api/images/<int:image_id>/similar-phash', methods=['GET'])
def find_similar_by_phash(image_id):
    """Find images similar to the given image using perceptual hash"""
    try:
        threshold = request.args.get('threshold', 10, type=int)
        phash = db.get_phash_by_id(image_id)

        if not phash:
            return jsonify({'error': 'Image has no perceptual hash'}), 404

        similar = db.find_similar_by_phash(phash, threshold)

        # Filter out the query image itself
        similar = [img for img in similar if img['id'] != image_id]

        return jsonify({
            'success': True,
            'count': len(similar),
            'similar': similar
        })
    except Exception as e:
        return jsonify({'error': f'Failed to find similar images: {str(e)}'}), 500


@images_bp.route('/api/duplicates/check', methods=['POST'])
def check_duplicate_before_upload():
    """Check if an image would be a duplicate before uploading"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Read file bytes
        file_bytes = file.read()

        # Compute hash from bytes
        phash = compute_phash_from_bytes(file_bytes)

        if not phash:
            return jsonify({
                'success': True,
                'is_duplicate': False,
                'message': 'Could not compute hash'
            })

        # Check if exists
        existing = db.check_phash_exists(phash)

        if existing:
            return jsonify({
                'success': True,
                'is_duplicate': True,
                'duplicate_of': {
                    'id': existing['id'],
                    'filename': existing['filename']
                }
            })

        return jsonify({
            'success': True,
            'is_duplicate': False
        })

    except Exception as e:
        return jsonify({'error': f'Check failed: {str(e)}'}), 500
