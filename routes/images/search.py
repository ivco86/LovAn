"""
Search & Discovery - search images, similar images, reverse search
"""

from flask import jsonify, request
from shared import db
from reverse_image_search import ReverseImageSearch, get_copyright_tips, get_usage_detection_tips
from . import images_bp


@images_bp.route('/api/images/<int:image_id>/similar', methods=['GET'])
def get_similar_images(image_id):
    """Find similar images using embeddings"""
    limit = request.args.get('limit', 20, type=int)

    try:
        # Get similar images from database
        similar = db.get_similar_images(image_id, limit)

        return jsonify({
            'image_id': image_id,
            'similar': similar,
            'count': len(similar)
        })

    except Exception as e:
        print(f"Error finding similar images for {image_id}: {str(e)}")
        return jsonify({'error': f'Failed to find similar images: {str(e)}'}), 500


@images_bp.route('/api/images/search', methods=['GET'])
def search_images():
    """Search images by query"""
    query = request.args.get('q', '').strip()

    if not query:
        return jsonify({'error': 'Query parameter "q" is required'}), 400

    results = db.search_images(query)

    return jsonify({
        'query': query,
        'results': results,
        'count': len(results)
    })


@images_bp.route('/api/images/<int:image_id>/reverse-search', methods=['GET'])
def get_reverse_search_options(image_id):
    """Get reverse image search options for an image"""
    # Get image info
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Image not found'}), 404

    # Construct image URL (accessible from client)
    image_url = f'/api/images/{image_id}/file'

    # Get all search options
    search_options = ReverseImageSearch.get_all_search_options(image_id, image_url)

    # Get helpful tips
    copyright_tips = get_copyright_tips()
    usage_tips = get_usage_detection_tips()

    # Get search guide
    search_guide = ReverseImageSearch.create_search_guide()

    return jsonify({
        'success': True,
        'image_id': image_id,
        'image_filename': image['filename'],
        'search_options': search_options,
        'copyright_tips': copyright_tips,
        'usage_detection_tips': usage_tips,
        'search_guide': search_guide
    })
