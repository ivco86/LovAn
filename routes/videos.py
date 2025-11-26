"""
API routes for YouTube video operations
"""

import os
import logging
from flask import Blueprint, jsonify, request
from shared import db, PHOTOS_DIR
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


# ============ VIDEO BOOKMARKS ============

@videos_bp.route('/api/videos/<int:video_id>/bookmarks', methods=['GET'])
def get_bookmarks(video_id):
    """Get all bookmarks for a video"""
    bookmarks = db.get_video_bookmarks(video_id)
    return jsonify({
        'video_id': video_id,
        'bookmarks': bookmarks,
        'count': len(bookmarks)
    })


@videos_bp.route('/api/videos/<int:video_id>/bookmarks', methods=['POST'])
def add_bookmark(video_id):
    """Add a bookmark to a video"""
    data = request.json or {}

    timestamp_ms = data.get('timestamp_ms')
    title = data.get('title')

    if timestamp_ms is None or not title:
        return jsonify({'error': 'timestamp_ms and title are required'}), 400

    bookmark_id = db.add_video_bookmark(
        youtube_video_id=video_id,
        timestamp_ms=timestamp_ms,
        title=title,
        description=data.get('description'),
        color=data.get('color', '#ff4444')
    )

    if bookmark_id:
        return jsonify({
            'success': True,
            'bookmark_id': bookmark_id
        }), 201
    return jsonify({'error': 'Failed to add bookmark'}), 500


@videos_bp.route('/api/bookmarks/<int:bookmark_id>', methods=['PUT'])
def update_bookmark(bookmark_id):
    """Update a bookmark"""
    data = request.json or {}

    success = db.update_video_bookmark(
        bookmark_id=bookmark_id,
        title=data.get('title'),
        description=data.get('description'),
        color=data.get('color'),
        timestamp_ms=data.get('timestamp_ms')
    )

    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Bookmark not found or update failed'}), 404


@videos_bp.route('/api/bookmarks/<int:bookmark_id>', methods=['DELETE'])
def delete_bookmark(bookmark_id):
    """Delete a bookmark"""
    success = db.delete_video_bookmark(bookmark_id)

    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Bookmark not found'}), 404


@videos_bp.route('/api/images/<int:image_id>/bookmarks', methods=['GET'])
def get_bookmarks_by_image(image_id):
    """Get bookmarks for a video by image_id"""
    bookmarks = db.get_bookmarks_by_image_id(image_id)
    return jsonify({
        'image_id': image_id,
        'bookmarks': bookmarks,
        'count': len(bookmarks)
    })


@videos_bp.route('/api/images/<int:image_id>/bookmarks', methods=['POST'])
def add_bookmark_by_image(image_id):
    """Add a bookmark to a video by image_id"""
    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    data = request.json or {}

    timestamp_ms = data.get('timestamp_ms')
    title = data.get('title')

    if timestamp_ms is None or not title:
        return jsonify({'error': 'timestamp_ms and title are required'}), 400

    bookmark_id = db.add_video_bookmark(
        youtube_video_id=video['id'],
        timestamp_ms=timestamp_ms,
        title=title,
        description=data.get('description'),
        color=data.get('color', '#ff4444')
    )

    if bookmark_id:
        return jsonify({
            'success': True,
            'bookmark_id': bookmark_id
        }), 201
    return jsonify({'error': 'Failed to add bookmark'}), 500


# ============ TRANSCRIPT EXPORT ============

@videos_bp.route('/api/images/<int:image_id>/transcript', methods=['GET'])
def export_transcript(image_id):
    """Export transcript in various formats (txt, srt, vtt, json)"""
    from flask import Response

    format_type = request.args.get('format', 'txt').lower()
    language = request.args.get('language')

    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    subtitles = db.get_video_subtitles(video['id'], language=language)
    if not subtitles:
        subtitles = db.get_video_subtitles(video['id'])

    video_title = video.get('title', 'transcript')
    safe_title = ''.join(c for c in video_title if c.isalnum() or c in ' -_')[:50]

    if format_type == 'txt':
        # Plain text without timestamps
        content = '\n'.join(sub.get('text', '') for sub in subtitles)
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="{safe_title}.txt"'}
        )

    elif format_type == 'txt_timestamps':
        # Plain text with timestamps
        lines = []
        for sub in subtitles:
            time_str = format_time_readable(sub.get('start_time_ms', 0))
            lines.append(f"[{time_str}] {sub.get('text', '')}")
        content = '\n'.join(lines)
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="{safe_title}_timestamped.txt"'}
        )

    elif format_type == 'srt':
        # SRT format
        content = ""
        for idx, sub in enumerate(subtitles, 1):
            start = format_srt_time(sub.get('start_time_ms', 0))
            end = format_srt_time(sub.get('end_time_ms', 0))
            text = sub.get('text', '').replace('\n', ' ')
            content += f"{idx}\n{start} --> {end}\n{text}\n\n"
        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': f'attachment; filename="{safe_title}.srt"'}
        )

    elif format_type == 'vtt':
        # WebVTT format
        content = "WEBVTT\n\n"
        for idx, sub in enumerate(subtitles, 1):
            start = format_vtt_time(sub.get('start_time_ms', 0))
            end = format_vtt_time(sub.get('end_time_ms', 0))
            text = sub.get('text', '').replace('\n', ' ')
            content += f"{idx}\n{start} --> {end}\n{text}\n\n"
        return Response(
            content,
            mimetype='text/vtt',
            headers={'Content-Disposition': f'attachment; filename="{safe_title}.vtt"'}
        )

    elif format_type == 'json':
        return jsonify({
            'title': video_title,
            'subtitles': subtitles
        })

    else:
        return jsonify({'error': f'Unknown format: {format_type}'}), 400


def format_srt_time(ms):
    """Format milliseconds to SRT timestamp (HH:MM:SS,mmm)"""
    total_seconds = ms // 1000
    milliseconds = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def format_time_readable(ms):
    """Format milliseconds to readable time (MM:SS)"""
    total_seconds = ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


# ============ VIDEO CLIPS EXPORT ============

@videos_bp.route('/api/images/<int:image_id>/clip', methods=['POST'])
def create_video_clip(image_id):
    """Create a video clip from start to end time"""
    import subprocess
    import tempfile
    from flask import send_file

    data = request.json or {}
    start_ms = data.get('start_ms', 0)
    end_ms = data.get('end_ms')
    include_subtitles = data.get('include_subtitles', False)

    if end_ms is None:
        return jsonify({'error': 'end_ms is required'}), 400

    if end_ms <= start_ms:
        return jsonify({'error': 'end_ms must be greater than start_ms'}), 400

    # Get video file path
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Video not found'}), 404

    video_path = os.path.join(PHOTOS_DIR, image['filepath'])
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found'}), 404

    # Convert ms to seconds
    start_sec = start_ms / 1000
    duration_sec = (end_ms - start_ms) / 1000

    # Create temp output file
    output_filename = f"clip_{image_id}_{start_ms}_{end_ms}.mp4"
    output_path = os.path.join(tempfile.gettempdir(), output_filename)

    try:
        # Build ffmpeg command
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(start_sec),
            '-i', video_path,
            '-t', str(duration_sec),
            '-c:v', 'libx264',
            '-c:a', 'aac',
            '-preset', 'fast',
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"FFmpeg error: {result.stderr.decode()}")
            return jsonify({'error': 'Failed to create clip'}), 500

        return send_file(
            output_path,
            mimetype='video/mp4',
            as_attachment=True,
            download_name=output_filename
        )

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Clip creation timed out'}), 500
    except Exception as e:
        logger.error(f"Error creating clip: {e}")
        return jsonify({'error': str(e)}), 500


# ============ AI VIDEO SUMMARY ============

@videos_bp.route('/api/images/<int:image_id>/summary', methods=['POST'])
def generate_video_summary(image_id):
    """Generate AI summary from video transcript"""
    from ai_service import ai_service

    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    # Get transcript
    transcript = db.get_full_transcript(video['id'])

    if not transcript or len(transcript.strip()) < 50:
        return jsonify({'error': 'Not enough transcript data for summary'}), 400

    # Truncate if too long (keep first ~8000 chars for API limits)
    if len(transcript) > 8000:
        transcript = transcript[:8000] + "..."

    prompt = f"""Analyze this video transcript and provide:
1. A brief summary (2-3 sentences)
2. Key topics/themes (bullet points)
3. Important timestamps/moments to note (if mentioned)

Video Title: {video.get('title', 'Unknown')}

Transcript:
{transcript}

Format your response as:
## Summary
[summary here]

## Key Topics
- [topic 1]
- [topic 2]
...

## Notable Moments
- [moment 1]
- [moment 2]
..."""

    try:
        # Use AI service to generate summary
        summary = ai_service.analyze_text(prompt)

        if not summary:
            return jsonify({'error': 'AI service failed to generate summary'}), 500

        return jsonify({
            'success': True,
            'summary': summary,
            'video_title': video.get('title'),
            'transcript_length': len(transcript)
        })

    except Exception as e:
        logger.error(f"Error generating summary: {e}")
        return jsonify({'error': f'AI analysis failed: {str(e)}'}), 500


@videos_bp.route('/api/images/<int:image_id>/summary', methods=['GET'])
def get_video_summary(image_id):
    """Get cached summary or generate new one"""
    # For now, just redirect to POST to generate
    # In future, could cache summaries in database
    return jsonify({
        'message': 'Use POST to generate a summary',
        'endpoint': f'/api/images/{image_id}/summary'
    }), 200


# ============ FRAME CAPTURE ============

@videos_bp.route('/api/images/<int:image_id>/capture-frame', methods=['POST'])
def capture_video_frame(image_id):
    """Capture a frame from video at specified timestamp and save to gallery"""
    import subprocess
    from datetime import datetime

    data = request.json or {}
    timestamp_ms = data.get('timestamp_ms', 0)

    # Get video file path
    image = db.get_image(image_id)
    if not image:
        return jsonify({'error': 'Video not found'}), 404

    video_path = os.path.join(PHOTOS_DIR, image['filepath'])
    if not os.path.exists(video_path):
        return jsonify({'error': 'Video file not found'}), 404

    # Generate output filename
    timestamp_sec = timestamp_ms / 1000
    video_name = os.path.splitext(os.path.basename(image['filepath']))[0]
    time_str = f"{int(timestamp_sec // 60):02d}m{int(timestamp_sec % 60):02d}s"
    output_filename = f"{video_name}_frame_{time_str}_{datetime.now().strftime('%H%M%S')}.jpg"
    output_path = os.path.join(PHOTOS_DIR, output_filename)

    try:
        # Use FFmpeg to extract frame
        cmd = [
            'ffmpeg', '-y',
            '-ss', str(timestamp_sec),
            '-i', video_path,
            '-vframes', '1',
            '-q:v', '2',  # High quality JPEG
            output_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=30)

        if result.returncode != 0 or not os.path.exists(output_path):
            logger.error(f"FFmpeg error: {result.stderr.decode()}")
            return jsonify({'error': 'Failed to capture frame'}), 500

        # Add captured frame to gallery
        file_size = os.path.getsize(output_path)
        new_image_id = db.add_image(
            output_filename,
            filename=output_filename,
            file_size=file_size,
            media_type='image'
        )

        if not new_image_id:
            return jsonify({'error': 'Failed to add frame to gallery'}), 500

        # Copy tags from video to captured frame
        if image.get('tags'):
            db.update_image(new_image_id, tags=image['tags'])

        return jsonify({
            'success': True,
            'image_id': new_image_id,
            'filename': output_filename,
            'timestamp_ms': timestamp_ms
        })

    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Frame capture timed out'}), 500
    except Exception as e:
        logger.error(f"Error capturing frame: {e}")
        return jsonify({'error': str(e)}), 500


# ============ VIDEO NOTES ============

@videos_bp.route('/api/images/<int:image_id>/notes', methods=['GET'])
def get_video_notes(image_id):
    """Get all timestamped notes for a video"""
    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    notes = db.get_video_notes(video['id'])
    return jsonify({
        'image_id': image_id,
        'notes': notes,
        'count': len(notes)
    })


@videos_bp.route('/api/images/<int:image_id>/notes', methods=['POST'])
def add_video_note(image_id):
    """Add a timestamped note to a video"""
    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    data = request.json or {}
    timestamp_ms = data.get('timestamp_ms')
    content = data.get('content')

    if timestamp_ms is None or not content:
        return jsonify({'error': 'timestamp_ms and content are required'}), 400

    note_id = db.add_video_note(
        youtube_video_id=video['id'],
        timestamp_ms=timestamp_ms,
        content=content
    )

    if note_id:
        return jsonify({
            'success': True,
            'note_id': note_id
        }), 201
    return jsonify({'error': 'Failed to add note'}), 500


@videos_bp.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_video_note(note_id):
    """Update a video note"""
    data = request.json or {}

    success = db.update_video_note(
        note_id=note_id,
        content=data.get('content'),
        timestamp_ms=data.get('timestamp_ms')
    )

    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Note not found or update failed'}), 404


@videos_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_video_note(note_id):
    """Delete a video note"""
    success = db.delete_video_note(note_id)

    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Note not found'}), 404


@videos_bp.route('/api/images/<int:image_id>/notes/export', methods=['GET'])
def export_video_notes(image_id):
    """Export video notes as markdown"""
    from flask import Response

    video = db.get_youtube_video_by_image_id(image_id)
    if not video:
        return jsonify({'error': 'Video not found'}), 404

    notes = db.get_video_notes(video['id'])

    # Generate markdown
    md_content = f"# Notes: {video.get('title', 'Video')}\n\n"

    for note in sorted(notes, key=lambda x: x.get('timestamp_ms', 0)):
        time_str = format_time_readable(note.get('timestamp_ms', 0))
        md_content += f"## [{time_str}]\n{note.get('content', '')}\n\n"

    video_title = video.get('title', 'notes')
    safe_title = ''.join(c for c in video_title if c.isalnum() or c in ' -_')[:50]

    return Response(
        md_content,
        mimetype='text/markdown',
        headers={'Content-Disposition': f'attachment; filename="{safe_title}_notes.md"'}
    )


# ============ TRANSLATION & VOCABULARY (Language Reactor style) ============

@videos_bp.route('/api/translate', methods=['POST'])
def translate_word():
    """Translate a word using AI and free translation APIs"""
    import requests as req
    from ai_service import ai_service

    data = request.json or {}
    word = data.get('word', '').strip()
    source_lang = data.get('source', 'en')
    target_lang = data.get('target', 'bg')
    context = data.get('context', '')
    use_ai = data.get('use_ai', True)  # Enable AI by default

    if not word:
        return jsonify({'error': 'Word is required'}), 400

    translations = []

    # Language names for AI prompt
    lang_names = {
        'en': 'English', 'bg': 'Bulgarian', 'de': 'German', 'fr': 'French',
        'es': 'Spanish', 'it': 'Italian', 'ru': 'Russian', 'pt': 'Portuguese'
    }
    source_name = lang_names.get(source_lang, source_lang)
    target_name = lang_names.get(target_lang, target_lang)

    # Try AI translation first (more contextual)
    if use_ai:
        try:
            prompt = f"""Translate the {source_name} word "{word}" to {target_name}.
Context sentence: "{context}"

Provide:
1. The most accurate translation for this context
2. 1-2 alternative translations if applicable
3. Brief usage note (optional)

Format your response as:
Translation: [main translation]
Alternatives: [alt1], [alt2]
Note: [brief note about usage]

Be concise. If the word has multiple meanings, focus on the one that fits the context."""

            ai_response = ai_service.analyze_text(prompt)
            if ai_response:
                # Parse AI response
                lines = ai_response.strip().split('\n')
                for line in lines:
                    if line.startswith('Translation:'):
                        main_trans = line.replace('Translation:', '').strip()
                        if main_trans and main_trans.lower() != word.lower():
                            translations.append({
                                'source': 'AI',
                                'translation': main_trans,
                                'is_ai': True
                            })
                    elif line.startswith('Alternatives:'):
                        alts = line.replace('Alternatives:', '').strip()
                        for alt in alts.split(','):
                            alt = alt.strip()
                            if alt and alt.lower() != word.lower() and not any(t['translation'] == alt for t in translations):
                                translations.append({
                                    'source': 'AI',
                                    'translation': alt,
                                    'is_ai': True
                                })
                    elif line.startswith('Note:'):
                        note = line.replace('Note:', '').strip()
                        if translations and note:
                            translations[0]['note'] = note
        except Exception as e:
            logger.warning(f"AI translation error: {e}")

    # Try MyMemory API as fallback/additional source
    try:
        mymemory_url = f"https://api.mymemory.translated.net/get"
        params = {
            'q': word,
            'langpair': f'{source_lang}|{target_lang}'
        }
        response = req.get(mymemory_url, params=params, timeout=5)
        if response.ok:
            mm_data = response.json()
            if mm_data.get('responseStatus') == 200:
                main_translation = mm_data.get('responseData', {}).get('translatedText', '')
                if main_translation and main_translation.lower() != word.lower():
                    # Check if not already in translations
                    if not any(t['translation'].lower() == main_translation.lower() for t in translations):
                        translations.append({
                            'source': 'MyMemory',
                            'translation': main_translation
                        })
                # Get alternative translations
                matches = mm_data.get('matches', [])
                for match in matches[:3]:
                    trans = match.get('translation', '')
                    if trans and trans.lower() != word.lower():
                        if not any(t['translation'].lower() == trans.lower() for t in translations):
                            translations.append({
                                'source': 'MyMemory',
                                'translation': trans,
                                'quality': match.get('quality', 0)
                            })
    except Exception as e:
        logger.warning(f"MyMemory translation error: {e}")

    # Check if word is already in vocabulary
    saved_word = db.get_vocabulary_word(word, source_lang, target_lang)

    return jsonify({
        'word': word,
        'source_language': source_lang,
        'target_language': target_lang,
        'translations': translations[:5],  # Limit to 5
        'context': context,
        'is_saved': saved_word is not None,
        'saved_data': saved_word
    })


@videos_bp.route('/api/vocabulary', methods=['GET'])
def get_vocabulary_list():
    """Get all saved vocabulary"""
    search = request.args.get('search', '')
    source = request.args.get('source', 'en')
    target = request.args.get('target', 'bg')
    limit = request.args.get('limit', 100, type=int)
    offset = request.args.get('offset', 0, type=int)

    words = db.get_vocabulary(
        source_language=source,
        target_language=target,
        search=search if search else None,
        limit=limit,
        offset=offset
    )

    total = db.get_vocabulary_count()

    return jsonify({
        'words': words,
        'total': total,
        'limit': limit,
        'offset': offset
    })


@videos_bp.route('/api/vocabulary', methods=['POST'])
def save_vocabulary_word():
    """Save a word to vocabulary"""
    data = request.json or {}
    word = data.get('word', '').strip()
    translation = data.get('translation', '').strip()

    if not word or not translation:
        return jsonify({'error': 'Word and translation are required'}), 400

    vocab_id = db.add_vocabulary(
        word=word,
        translation=translation,
        source_language=data.get('source_language', 'en'),
        target_language=data.get('target_language', 'bg'),
        context_sentence=data.get('context_sentence'),
        video_id=data.get('video_id'),
        timestamp_ms=data.get('timestamp_ms'),
        notes=data.get('notes')
    )

    if vocab_id:
        return jsonify({'success': True, 'id': vocab_id}), 201
    return jsonify({'error': 'Failed to save word'}), 500


@videos_bp.route('/api/vocabulary/<int:vocab_id>', methods=['DELETE'])
def delete_vocabulary_word(vocab_id):
    """Delete a word from vocabulary"""
    success = db.delete_vocabulary(vocab_id)
    if success:
        return jsonify({'success': True})
    return jsonify({'error': 'Word not found'}), 404


@videos_bp.route('/api/vocabulary/export', methods=['GET'])
def export_vocabulary():
    """Export vocabulary as CSV or Anki format"""
    from flask import Response
    import csv
    import io

    format_type = request.args.get('format', 'csv')
    source = request.args.get('source', 'en')
    target = request.args.get('target', 'bg')

    words = db.get_vocabulary(source_language=source, target_language=target, limit=10000)

    if format_type == 'anki':
        # Anki tab-separated format
        content = ""
        for word in words:
            front = word['word']
            back = f"{word['translation']}"
            if word.get('context_sentence'):
                back += f"<br><br><i>{word['context_sentence']}</i>"
            content += f"{front}\t{back}\n"

        return Response(
            content,
            mimetype='text/plain',
            headers={'Content-Disposition': 'attachment; filename="vocabulary_anki.txt"'}
        )
    else:
        # CSV format
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Word', 'Translation', 'Context', 'Notes', 'Created'])

        for word in words:
            writer.writerow([
                word['word'],
                word['translation'],
                word.get('context_sentence', ''),
                word.get('notes', ''),
                word.get('created_at', '')
            ])

        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename="vocabulary.csv"'}
        )


# ============ AI VIDEO HIGHLIGHTS ============

@videos_bp.route('/api/images/<int:image_id>/highlight', methods=['POST'])
def generate_video_highlight(image_id):
    """Generate an AI-powered highlight video (TikTok/Shorts style)"""
    from youtube_service import YouTubeService

    try:
        data = request.json or {}
        target_duration = data.get('duration', 30)  # Default 30 seconds

        # Validate duration
        if target_duration < 10 or target_duration > 120:
            return jsonify({'error': 'Duration must be between 10 and 120 seconds'}), 400

        # Get video info
        video = db.get_youtube_video_by_image_id(image_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404

        logger.info(f"Generating highlight for video {video.get('id')}, image_id={image_id}")

        # Check if video has subtitles
        subtitles = db.get_video_subtitles(video['id'])
        if not subtitles:
            return jsonify({
                'error': 'No subtitles available for this video. Subtitles are required for AI highlight generation.'
            }), 400

        logger.info(f"Found {len(subtitles)} subtitles for video")

        # Generate highlight
        youtube_service = YouTubeService(db)
        result = youtube_service.generate_ai_highlight(video['id'], target_duration=target_duration)

        if result:
            return jsonify({
                'success': True,
                'highlight_path': result['highlight_path'],
                'highlight_url': f"/highlights/{os.path.basename(result['highlight_path'])}",
                'segments': result['segments'],
                'summary': result['summary'],
                'duration_ms': result['duration_ms'],
                'duration_formatted': format_time_readable(result['duration_ms'])
            })
        else:
            return jsonify({'error': 'Failed to generate highlight video'}), 500

    except Exception as e:
        logger.error(f"Error in generate_video_highlight: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@videos_bp.route('/api/images/<int:image_id>/highlight/preview', methods=['POST'])
def preview_highlight_segments(image_id):
    """Preview AI-selected highlight segments without generating video"""
    from ai_service import ai_service

    try:
        data = request.json or {}
        target_duration = data.get('duration', 30)

        # Get video info
        video = db.get_youtube_video_by_image_id(image_id)
        if not video:
            return jsonify({'error': 'Video not found'}), 404

        logger.info(f"Preview highlight for video {video.get('id')}, image_id={image_id}")

        # Get subtitles
        subtitles = db.get_video_subtitles(video['id'])
        if not subtitles:
            return jsonify({'error': 'No subtitles available'}), 400

        logger.info(f"Found {len(subtitles)} subtitles, analyzing...")

        # Analyze subtitles
        video_duration_ms = (video.get('duration') or 0) * 1000
        analysis = ai_service.analyze_subtitles_for_highlights(
            subtitles,
            target_duration=target_duration,
            video_duration_ms=video_duration_ms
        )

        if analysis:
            return jsonify({
                'success': True,
                'segments': analysis['segments'],
                'summary': analysis.get('summary', ''),
                'total_duration_ms': analysis.get('total_duration_ms', 0),
                'hook_segment_index': analysis.get('hook_segment_index', 0)
            })
        else:
            return jsonify({'error': 'AI analysis failed'}), 500

    except Exception as e:
        logger.error(f"Error in preview_highlight_segments: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@videos_bp.route('/highlights/<path:filename>')
def serve_highlight(filename):
    """Serve highlight videos"""
    from flask import send_from_directory
    highlights_dir = os.path.join('data', 'highlights')
    return send_from_directory(highlights_dir, filename)
