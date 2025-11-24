"""
EXIF metadata endpoints - extract, view, search by camera/settings
"""

import os
from flask import jsonify, request

from shared import db, PHOTOS_DIR
from utils import get_full_filepath
from exif_utils import (
    extract_exif_data,
    get_camera_list_from_exif_data,
    format_exif_for_display,
    sync_database_to_exif
)
from . import ai_bp


@ai_bp.route('/api/images/<int:image_id>/exif', methods=['GET'])
def get_image_exif(image_id):
    """Get EXIF data for an image"""
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    exif_data = db.get_exif_data(image_id)
    if not exif_data:
        return jsonify({
            'image_id': image_id,
            'has_exif': False,
            'message': 'No EXIF data available.'
        })
    
    formatted = format_exif_for_display(exif_data)
    return jsonify({
        'image_id': image_id,
        'has_exif': True,
        'exif': exif_data,
        'formatted': formatted
    })


@ai_bp.route('/api/images/<int:image_id>/exif/extract', methods=['POST'])
def extract_image_exif(image_id):
    """Extract EXIF data from image file"""
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    if image.get('media_type') == 'video':
        return jsonify({'error': 'No video EXIF support'}), 400
    
    filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    exif_data = extract_exif_data(filepath)
    if not exif_data:
        return jsonify({
            'success': False,
            'message': 'No EXIF data found'
        })

    success = db.save_exif_data(image_id, exif_data)
    if success:
        formatted = format_exif_for_display(exif_data)
        return jsonify({
            'success': True,
            'image_id': image_id,
            'exif': exif_data,
            'formatted': formatted
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Failed to save'
        }), 500


@ai_bp.route('/api/images/search/exif', methods=['POST'])
def search_images_by_exif():
    """Search images by EXIF metadata (camera, lens, settings, etc.)"""
    data = request.get_json() or {}
    limit = data.pop('limit', 100)
    
    # Pass remaining data as kwargs
    results = db.search_by_exif(limit=limit, **data)
    
    return jsonify({
        'results': results,
        'count': len(results),
        'criteria': data
    })


@ai_bp.route('/api/exif/cameras', methods=['GET'])
def get_cameras():
    """Get list of all cameras found in EXIF data"""
    cameras = db.get_all_cameras()
    return jsonify({
        'cameras': cameras,
        'count': len(cameras)
    })


@ai_bp.route('/api/images/<int:image_id>/exif/sync', methods=['POST'])
def sync_image_to_exif(image_id):
    """
    Sync image description and tags from database to EXIF metadata

    This writes AI-generated descriptions and tags directly into the image file's
    EXIF data, making them portable with the file.
    """
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    if image.get('media_type') == 'video':
        return jsonify({'error': 'Cannot write EXIF to video files'}), 400

    filepath = get_full_filepath(image['filepath'], PHOTOS_DIR)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    # Sync database data to EXIF
    result = sync_database_to_exif(filepath, {
        'description': image.get('description'),
        'tags': image.get('tags', [])
    })

    if result['success']:
        return jsonify({
            'success': True,
            'message': result['message'],
            'fields_written': result.get('fields_written', [])
        })
    else:
        return jsonify({
            'success': False,
            'message': result['message']
        }), 500
