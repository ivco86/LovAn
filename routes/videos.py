"""
API routes for YouTube video operations
"""

import logging
from flask import Blueprint, jsonify, request
from shared import db
from youtube_service import YouTubeService

logger = logging.getLogger(__name__)

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
    original_subtitles = data.get('original_subtitles', True)
    extract_keyframes = data.get('keyframes', True)
    quality = data.get('quality', '1080')

    logger.info(f"📥 Starting download: url={url}, quality={quality}, subtitles={download_subtitles}, original_subs={original_subtitles}")

    result = youtube_service.download_video(
        url,
        download_subtitles=download_subtitles,
        original_subtitles=original_subtitles,
        extract_keyframes=extract_keyframes,
        quality=quality
    )

    if not result:
        logger.error("❌ Download returned None - failed completely")
        return jsonify({'error': 'Download failed'}), 500

    logger.info(f"📦 Download result: status={result.get('status')}, image_id={result.get('image_id')}, yt_video_id={result.get('youtube_video_id')}, video_path={result.get('video_path')}")

    if result.get('status') == 'exists':
        return jsonify({
            'status': 'exists',
            'message': 'Video already in gallery',
            'video': result.get('video')
        }), 200

    # Check if video was properly added to database
    if not result.get('image_id'):
        logger.warning("⚠️ Video downloaded but image_id is missing - database insertion may have failed")
    if not result.get('youtube_video_id'):
        logger.warning("⚠️ Video downloaded but youtube_video_id is missing - YouTube metadata not saved")

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


@videos_bp.route('/api/images/<int:image_id>/subtitles', methods=['GET'])
def get_subtitles_by_image(image_id):
    """Get subtitles for a YouTube video by its image_id"""
    language = request.args.get('language')

    # Get youtube video by image_id
    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Not a YouTube video or subtitles not available'}), 404

    subtitles = db.get_video_subtitles(video['id'], language=language)

    # Get available languages
    all_subtitles = db.get_video_subtitles(video['id'])
    languages = list(set(sub.get('language', 'unknown') for sub in all_subtitles))

    return jsonify({
        'image_id': image_id,
        'youtube_video_id': video['id'],
        'subtitles': subtitles,
        'languages': languages,
        'count': len(subtitles)
    })


@videos_bp.route('/api/images/<int:image_id>/subtitles.vtt', methods=['GET'])
def get_subtitles_vtt(image_id):
    """Get subtitles as VTT file for HTML5 video player track element"""
    from flask import Response

    language = request.args.get('language', 'en')

    # Get youtube video by image_id
    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return Response("WEBVTT\n\n", mimetype='text/vtt')

    subtitles = db.get_video_subtitles(video['id'], language=language)

    if not subtitles:
        # Try without language filter
        subtitles = db.get_video_subtitles(video['id'])

    # Generate VTT content
    vtt_content = "WEBVTT\n\n"

    for idx, sub in enumerate(subtitles):
        start_time = format_vtt_time(sub.get('start_time_ms', 0))
        end_time = format_vtt_time(sub.get('end_time_ms', 0))
        text = sub.get('text', '').replace('\n', ' ')

        vtt_content += f"{idx + 1}\n"
        vtt_content += f"{start_time} --> {end_time}\n"
        vtt_content += f"{text}\n\n"

    return Response(vtt_content, mimetype='text/vtt')


def format_vtt_time(ms):
    """Format milliseconds to VTT timestamp (HH:MM:SS.mmm)"""
    total_seconds = ms // 1000
    milliseconds = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


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
