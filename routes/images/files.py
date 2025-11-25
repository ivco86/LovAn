"""
File serving - serve images, thumbnails, and handle file operations
"""

import os
import mimetypes
import requests
from io import BytesIO
from flask import jsonify, request, send_file
from PIL import Image

from shared import db, PHOTOS_DIR, DATA_DIR
from utils import get_full_filepath, extract_video_frame, create_video_placeholder
from . import images_bp


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
    """Serve thumbnail (resized image for grid) with caching"""
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

    # Check if this is a video
    is_video = image.get('media_type') == 'video'

    # Generate cache key from image ID, size, and modification time
    try:
        mtime = int(os.path.getmtime(abs_filepath))
        cache_filename = f"{image_id}_{size}_{mtime}.jpg"
        cache_path = os.path.join(thumbnail_cache_dir, cache_filename)

        # Check if cached thumbnail exists
        if os.path.exists(cache_path):
            return send_file(cache_path, mimetype='image/jpeg')

        # Generate and cache thumbnail
        img = None
        if is_video:
            # Check if this is a YouTube video with a thumbnail URL
            youtube_video = db.get_youtube_video_by_image_id(image_id)
            if youtube_video and youtube_video.get('thumbnail_url'):
                # Try to download and use YouTube thumbnail (usually higher quality and larger)
                try:
                    thumbnail_url = youtube_video['thumbnail_url']
                    # YouTube thumbnails have different sizes available:
                    # maxresdefault (1280x720) - highest quality
                    # hqdefault (480x360) - high quality
                    # mqdefault (320x180) - medium quality
                    # default (120x90) - low quality
                    
                    # Extract YouTube ID from thumbnail URL or use the youtube_id from database
                    youtube_id = youtube_video.get('youtube_id', '')
                    if not youtube_id and 'vi/' in thumbnail_url:
                        # Extract from URL like https://i.ytimg.com/vi/VIDEO_ID/default.jpg
                        parts = thumbnail_url.split('/vi/')
                        if len(parts) > 1:
                            youtube_id = parts[1].split('/')[0]
                    
                    # Try different qualities, starting with highest
                    if youtube_id:
                        for quality in ['maxresdefault', 'hqdefault', 'mqdefault', 'default']:
                            quality_url = f"https://i.ytimg.com/vi/{youtube_id}/{quality}.jpg"
                            try:
                                response = requests.get(quality_url, timeout=10, stream=True)
                                if response.status_code == 200:
                                    img_data = BytesIO(response.content)
                                    img = Image.open(img_data)
                                    print(f"[THUMBNAIL] Using YouTube thumbnail for image {image_id} (quality: {quality}, size: {img.size})")
                                    break
                            except Exception as e:
                                print(f"[THUMBNAIL] Failed to download {quality} thumbnail: {e}")
                                continue
                    else:
                        # Fallback to original thumbnail URL
                        try:
                            response = requests.get(thumbnail_url, timeout=10, stream=True)
                            if response.status_code == 200:
                                img_data = BytesIO(response.content)
                                img = Image.open(img_data)
                                print(f"[THUMBNAIL] Using original YouTube thumbnail for image {image_id}")
                        except Exception as e:
                            print(f"[THUMBNAIL] Failed to download original thumbnail: {e}")
                except Exception as e:
                    print(f"[THUMBNAIL] Error downloading YouTube thumbnail: {e}")
            
            # If YouTube thumbnail failed or doesn't exist, extract frame from video
            if not img:
                img = extract_video_frame(abs_filepath, cache_path, time_sec=1.0)

            if not img:
                # Fallback to placeholder if opencv not available or extraction failed
                img = create_video_placeholder(size)
        else:
            # Regular image processing
            img = Image.open(abs_filepath)

        # Resize thumbnail
        img.thumbnail((size, size), Image.Resampling.LANCZOS)

        # Convert RGBA to RGB (JPEG doesn't support transparency)
        if img.mode in ('RGBA', 'LA', 'P'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1])  # Use alpha channel as mask
            img = background

        # Higher quality for better visual appearance (92 is a good balance)
        img.save(cache_path, 'JPEG', quality=92, optimize=True)

        # Clean up old thumbnails for this image
        for old_file in os.listdir(thumbnail_cache_dir):
            if old_file.startswith(f"{image_id}_") and old_file != cache_filename:
                try:
                    os.remove(os.path.join(thumbnail_cache_dir, old_file))
                except:
                    pass

        return send_file(cache_path, mimetype='image/jpeg')
    except Exception as e:
        print(f"Error generating thumbnail for image {image_id}: {e}")

        # For videos, try to return placeholder
        if is_video:
            try:
                img = create_video_placeholder(size)
                img.save(cache_path, 'JPEG', quality=92)
                return send_file(cache_path, mimetype='image/jpeg')
            except Exception as e2:
                print(f"Failed to create video placeholder: {e2}")

        # Try to serve original file as fallback
        try:
            return send_file(abs_filepath, mimetype=mimetypes.guess_type(abs_filepath)[0])
        except Exception as e3:
            print(f"Failed to serve original file: {e3}")
            return jsonify({'error': 'Thumbnail generation failed'}), 500
