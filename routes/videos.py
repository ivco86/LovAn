"""
API routes for YouTube video operations
"""

from flask import Blueprint, jsonify, request
from shared import db
from youtube_service import YouTubeService

videos_bp = Blueprint('videos', __name__)
youtube_service = YouTubeService(db)


@videos_bp.route('/api/videos', methods=['GET'])
def get_videos():
    """Get all YouTube videos with pagination"""
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    videos = db.get_all_youtube_videos(limit=limit, offset=offset)

    return jsonify({
        'videos': videos,
        'count': len(videos),
        'offset': offset,
        'limit': limit
    })


@videos_bp.route('/api/videos/<int:video_id>', methods=['GET'])
def get_video(video_id):
    """Get single YouTube video details"""
    video = db.get_youtube_video(video_id)

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Include keyframes and subtitles
    video['keyframes'] = db.get_video_keyframes(video_id)
    video['subtitles'] = db.get_video_subtitles(video_id)

    return jsonify(video)


@videos_bp.route('/api/videos/youtube/<youtube_id>', methods=['GET'])
def get_video_by_youtube_id(youtube_id):
    """Get video by YouTube ID"""
    video = db.get_youtube_video_by_youtube_id(youtube_id)

    if not video:
        return jsonify({'error': 'Video not found'}), 404

    video['keyframes'] = db.get_video_keyframes(video['id'])
    video['subtitles'] = db.get_video_subtitles(video['id'])

    return jsonify(video)


@videos_bp.route('/api/videos/info', methods=['GET'])
def get_video_info():
    """Get video information without downloading"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter required'}), 400

    try:
        info = youtube_service.get_video_info(url)
        if not info:
            return jsonify({'error': 'Failed to get video information'}), 400
    except RuntimeError as e:
        # yt-dlp not installed
        return jsonify({
            'error': str(e),
            'code': 'YTDLP_NOT_INSTALLED'
        }), 503
    except ValueError as e:
        # Invalid URL format
        return jsonify({
            'error': str(e),
            'code': 'INVALID_URL'
        }), 400
    except Exception as e:
        return jsonify({
            'error': f'Failed to get video information: {str(e)}',
            'code': 'UNKNOWN_ERROR'
        }), 500

    # Check if already in database
    existing = db.get_youtube_video_by_youtube_id(info['youtube_id'])
    info['exists_in_gallery'] = existing is not None
    if existing:
        info['gallery_id'] = existing['id']

    return jsonify(info)


@videos_bp.route('/api/videos/download', methods=['POST'])
def download_video():
    """Download a YouTube video"""
    data = request.json or {}
    url = data.get('url')

    if not url:
        return jsonify({'error': 'URL parameter required'}), 400

    download_subtitles = data.get('subtitles', True)
    extract_keyframes = data.get('keyframes', True)

    result = youtube_service.download_video(
        url,
        download_subtitles=download_subtitles,
        extract_keyframes=extract_keyframes
    )

    if not result:
        return jsonify({'error': 'Download failed'}), 500

    if result.get('status') == 'exists':
        return jsonify({
            'status': 'exists',
            'message': 'Video already in gallery',
            'video': result.get('video')
        }), 200

    return jsonify({
        'status': 'success',
        'youtube_id': result.get('youtube_id'),
        'image_id': result.get('image_id'),
        'youtube_video_id': result.get('youtube_video_id'),
        'title': result.get('title'),
        'duration': result.get('duration'),
        'keyframe_count': len(result.get('keyframes', [])),
        'subtitle_languages': list(result.get('parsed_subtitles', {}).keys())
    })


@videos_bp.route('/api/videos/<int:video_id>', methods=['DELETE'])
def delete_video(video_id):
    """Delete a YouTube video"""
    video = db.get_youtube_video(video_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    success = db.delete_youtube_video(video_id)
    if success:
        return jsonify({'success': True, 'message': 'Video deleted'})
    return jsonify({'error': 'Failed to delete video'}), 500


@videos_bp.route('/api/videos/<int:video_id>/keyframes', methods=['GET'])
def get_keyframes(video_id):
    """Get keyframes for a video"""
    video = db.get_youtube_video(video_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    keyframes = db.get_video_keyframes(video_id)
    return jsonify({
        'video_id': video_id,
        'keyframes': keyframes,
        'count': len(keyframes)
    })


@videos_bp.route('/api/videos/<int:video_id>/subtitles', methods=['GET'])
def get_subtitles(video_id):
    """Get subtitles for a video"""
    language = request.args.get('language')

    video = db.get_youtube_video(video_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    subtitles = db.get_video_subtitles(video_id, language=language)
    return jsonify({
        'video_id': video_id,
        'subtitles': subtitles,
        'count': len(subtitles)
    })


@videos_bp.route('/api/videos/search/subtitles', methods=['GET'])
def search_subtitles():
    """Search across all video subtitles"""
    query = request.args.get('q', '')
    limit = request.args.get('limit', 50, type=int)

    if not query:
        return jsonify({'error': 'Query parameter required'}), 400

    results = db.search_video_subtitles(query, limit=limit)

    return jsonify({
        'query': query,
        'results': results,
        'count': len(results)
    })
