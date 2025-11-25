"""
CRUD operations for images - list, get, update, delete
"""

import os
from flask import jsonify, request
from shared import db
from . import images_bp


@images_bp.route('/api/images', methods=['GET'])
def get_images():
    """Get all images with optional filters"""
    limit = request.args.get('limit', 1000, type=int)
    offset = request.args.get('offset', 0, type=int)
    favorites_only = request.args.get('favorites', 'false').lower() == 'true'

    media_type = request.args.get('media_type')
    if media_type:
        media_type = media_type.strip().lower()
        if media_type in ('all', 'any'):
            media_type = None

    analyzed_param = request.args.get('analyzed')
    analyzed = None
    if analyzed_param is not None:
        analyzed_param = analyzed_param.strip().lower()
        if analyzed_param in ('true', '1'):
            analyzed = True
        elif analyzed_param in ('false', '0'):
            analyzed = False

    # YouTube filtering
    youtube_only = request.args.get('youtube_only', 'false').lower() == 'true'
    exclude_youtube = request.args.get('exclude_youtube', 'false').lower() == 'true'

    images = db.get_all_images(
        limit=limit,
        offset=offset,
        favorites_only=favorites_only,
        media_type=media_type,
        analyzed=analyzed,
        youtube_only=youtube_only,
        exclude_youtube=exclude_youtube
    )

    return jsonify({
        'images': images,
        'count': len(images),
        'offset': offset,
        'limit': limit
    })


@images_bp.route('/api/images/<int:image_id>', methods=['GET'])
def get_image(image_id):
    """Get single image details"""
    image = db.get_image(image_id)

    if not image:
        return jsonify({'error': 'Image not found'}), 404

    # Get boards containing this image
    boards = db.get_image_boards(image_id)
    image['boards'] = boards

    return jsonify(image)


@images_bp.route('/api/images/<int:image_id>', methods=['PATCH'])
def update_image(image_id):
    """Update image description and tags"""
    data = request.json

    # Get current image
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    description = data.get('description', '')
    tags = data.get('tags', [])

    try:
        # Use the database method to update image analysis
        # Clean up tags - remove empty strings
        clean_tags = [tag.strip() for tag in tags if tag and tag.strip()]

        # Update using the proper database method
        db.update_image_analysis(image_id, description, clean_tags)

        # Get updated image
        updated_image = db.get_image(image_id)

        return jsonify({
            'success': True,
            'image': updated_image
        })
    except Exception as e:
        return jsonify({'error': f'Failed to update: {str(e)}'}), 500


@images_bp.route('/api/images/<int:image_id>', methods=['DELETE'])
def delete_image(image_id):
    """Delete an image from database and optionally from disk"""
    delete_file = request.args.get('delete_file', 'false').lower() == 'true'

    # Get image details first
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    file_path = image.get('file_path')

    try:
        # Delete from database
        db.delete_image(image_id)

        # Optionally delete the actual file
        if delete_file and file_path and os.path.exists(file_path):
            os.remove(file_path)
            return jsonify({
                'success': True,
                'message': 'Image deleted from database and disk',
                'file_deleted': True
            })

        return jsonify({
            'success': True,
            'message': 'Image deleted from database',
            'file_deleted': False
        })
    except Exception as e:
        return jsonify({'error': f'Failed to delete: {str(e)}'}), 500
