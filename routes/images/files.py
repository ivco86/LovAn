"""
File serving - serve images, thumbnails, and handle file operations
Optimized with async thumbnail generation and caching
"""

import os
import mimetypes
import requests
import threading
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from flask import jsonify, request, send_file
from PIL import Image

from shared import db, PHOTOS_DIR, DATA_DIR
from utils import get_full_filepath, extract_video_frame, create_video_placeholder
from . import images_bp

# Thread pool for async thumbnail generation
_thumbnail_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="thumb_")
_pending_thumbnails = set()  # Track in-progress thumbnails
_pending_lock = threading.Lock()


def _generate_thumbnail_background(image_id: int, size: int, abs_filepath: str,
                                    cache_path: str, is_video: bool, youtube_video: dict = None):
    """Generate thumbnail in background thread"""
    try:
        img = None

        if is_video and youtube_video and youtube_video.get('thumbnail_url'):
            # Try YouTube thumbnail with shorter timeout
            youtube_id = youtube_video.get('youtube_id', '')
            if not youtube_id and 'vi/' in youtube_video.get('thumbnail_url', ''):
                parts = youtube_video['thumbnail_url'].split('/vi/')
                if len(parts) > 1:
                    youtube_id = parts[1].split('/')[0]

            if youtube_id:
                # Try only 2 qualities with short timeout
                for quality in ['hqdefault', 'mqdefault']:
                    try:
                        quality_url = f"https://i.ytimg.com/vi/{youtube_id}/{quality}.jpg"
                        response = requests.get(quality_url, timeout=3, stream=True)
                        if response.status_code == 200:
                            img = Image.open(BytesIO(response.content))
                            break
                    except:
                        continue

        if not img and is_video:
            img = extract_video_frame(abs_filepath, cache_path, time_sec=1.0)
            if not img:
                img = create_video_placeholder(size)
        elif not img:
            img = Image.open(abs_filepath)

        # Use BILINEAR for faster resizing (3x faster than LANCZOS)
        img.thumbnail((size, size), Image.Resampling.BILINEAR)

        # Convert RGBA to RGB
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])
            img = background

        # Save without optimize for speed (quality 85 is good enough for thumbnails)
        img.save(cache_path, 'JPEG', quality=85)

    except Exception as e:
        print(f"[THUMBNAIL] Background generation failed for {image_id}: {e}")
    finally:
        with _pending_lock:
            _pending_thumbnails.discard(f"{image_id}_{size}")


@images_bp.route('/api/images/<int:image_id>/file', methods=['GET'])
def serve_image(image_id):
    """Serve actual image file"""
    image = db.get_image(image_id)

    if not image:
        return jsonify({'error': 'Image not found'}), 404

    filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)

    # Security: Validate filepath is within PHOTOS_DIR
    abs_filepath = os.path.abspath(filepath)
    abs_photos_dir = os.path.abspath(PHOTOS_DIR)

    if not abs_filepath.startswith(abs_photos_dir):
        print(f"Security: Path traversal attempt blocked: {filepath}")
        return jsonify({'error': 'Invalid file path'}), 403

    if not os.path.exists(abs_filepath):
        return jsonify({'error': 'File not found on disk'}), 404

    # Additional check: ensure it's actually a file, not a directory
    if not os.path.isfile(abs_filepath):
        return jsonify({'error': 'Invalid file'}), 403

    return send_file(abs_filepath, mimetype=mimetypes.guess_type(abs_filepath)[0])


@images_bp.route('/api/images/<int:image_id>/thumbnail', methods=['GET'])
def serve_thumbnail(image_id):
    """Serve thumbnail with async generation and caching for fast response"""
    size = request.args.get('size', 300, type=int)
    size = min(size, 1000)  # Prevent abuse

    image = db.get_image(image_id)

    if not image:
        return jsonify({'error': 'Image not found'}), 404

    filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)

    # Security: Validate filepath is within PHOTOS_DIR
    abs_filepath = os.path.abspath(filepath)
    abs_photos_dir = os.path.abspath(PHOTOS_DIR)

    if not abs_filepath.startswith(abs_photos_dir):
        print(f"Security: Path traversal attempt blocked: {filepath}")
        return jsonify({'error': 'Invalid file path'}), 403

    if not os.path.exists(abs_filepath):
        return jsonify({'error': 'File not found on disk'}), 404

    if not os.path.isfile(abs_filepath):
        return jsonify({'error': 'Invalid file'}), 403

    # Thumbnail caching
    thumbnail_cache_dir = os.path.join(DATA_DIR, 'thumbnails')
    os.makedirs(thumbnail_cache_dir, exist_ok=True)

    is_video = image.get('media_type') == 'video'

    try:
        mtime = int(os.path.getmtime(abs_filepath))
        cache_filename = f"{image_id}_{size}_{mtime}.jpg"
        cache_path = os.path.join(thumbnail_cache_dir, cache_filename)

        # Fast path: return cached thumbnail immediately
        if os.path.exists(cache_path):
            return send_file(cache_path, mimetype='image/jpeg')

        # Check if generation is already in progress
        pending_key = f"{image_id}_{size}"
        with _pending_lock:
            if pending_key in _pending_thumbnails:
                # Return placeholder while generating
                return _serve_placeholder(size, is_video)
            _pending_thumbnails.add(pending_key)

        # Get YouTube video info if needed (quick DB lookup)
        youtube_video = None
        if is_video:
            youtube_video = db.get_youtube_video_by_image_id(image_id)

        # For regular images, try fast synchronous generation first
        if not is_video:
            try:
                img = Image.open(abs_filepath)
                img.thumbnail((size, size), Image.Resampling.BILINEAR)

                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    if img.mode in ('RGBA', 'LA'):
                        background.paste(img, mask=img.split()[-1])
                    img = background

                img.save(cache_path, 'JPEG', quality=85)

                with _pending_lock:
                    _pending_thumbnails.discard(pending_key)

                # Clean up old thumbnails asynchronously
                _thumbnail_executor.submit(_cleanup_old_thumbnails,
                                           thumbnail_cache_dir, image_id, cache_filename)

                return send_file(cache_path, mimetype='image/jpeg')
            except Exception as e:
                print(f"[THUMBNAIL] Fast generation failed for {image_id}: {e}")
                with _pending_lock:
                    _pending_thumbnails.discard(pending_key)

        # For videos or if fast path failed, use async generation
        _thumbnail_executor.submit(
            _generate_thumbnail_background,
            image_id, size, abs_filepath, cache_path, is_video, youtube_video
        )

        return _serve_placeholder(size, is_video)

    except Exception as e:
        print(f"Error in thumbnail route for image {image_id}: {e}")
        return _serve_placeholder(size, is_video)


def _serve_placeholder(size: int, is_video: bool):
    """Return a quick placeholder image"""
    try:
        img = create_video_placeholder(size) if is_video else Image.new('RGB', (size, size), (240, 240, 240))
        buffer = BytesIO()
        img.save(buffer, 'JPEG', quality=70)
        buffer.seek(0)
        return send_file(buffer, mimetype='image/jpeg')
    except:
        return jsonify({'error': 'Placeholder generation failed'}), 500


def _cleanup_old_thumbnails(cache_dir: str, image_id: int, current_filename: str):
    """Clean up old thumbnails in background"""
    try:
        for old_file in os.listdir(cache_dir):
            if old_file.startswith(f"{image_id}_") and old_file != current_filename:
                try:
                    os.remove(os.path.join(cache_dir, old_file))
                except:
                    pass
    except:
        pass
