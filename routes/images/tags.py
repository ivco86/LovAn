"""
Tag Management - get tags, suggestions, related tags
"""

from flask import jsonify, request
from shared import db
from . import images_bp


@images_bp.route('/api/tags', methods=['GET'])
def get_tags():
    """Get all tags with usage statistics"""
    try:
        tags = db.get_all_tags()
        return jsonify({
            'tags': tags,
            'count': len(tags)
        })
    except Exception as e:
        print(f"Error getting tags: {str(e)}")
        return jsonify({'error': f'Failed to get tags: {str(e)}'}), 500


@images_bp.route('/api/tags/suggestions', methods=['GET'])
def get_tag_suggestions():
    """Get tag suggestions for autocomplete"""
    try:
        prefix = request.args.get('prefix', '')
        limit = int(request.args.get('limit', 10))

        suggestions = db.get_tag_suggestions(prefix, limit)
        return jsonify({
            'suggestions': suggestions,
            'count': len(suggestions)
        })
    except Exception as e:
        print(f"Error getting tag suggestions: {str(e)}")
        return jsonify({'error': f'Failed to get tag suggestions: {str(e)}'}), 500


@images_bp.route('/api/tags/<tag>/related', methods=['GET'])
def get_related_tags(tag):
    """Get tags that frequently appear with the given tag"""
    try:
        limit = int(request.args.get('limit', 10))
        related = db.get_related_tags(tag, limit)
        return jsonify({
            'tag': tag,
            'related': related,
            'count': len(related)
        })
    except Exception as e:
        print(f"Error getting related tags: {str(e)}")
        return jsonify({'error': f'Failed to get related tags: {str(e)}'}), 500
