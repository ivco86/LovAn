#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Video Download Service for AI Gallery
Downloads videos from YouTube, TikTok, Facebook and other platforms using yt-dlp
Extracts metadata, subtitles, and keyframes

Supported platforms:
- YouTube (youtube.com, youtu.be)
- TikTok (tiktok.com)
- Facebook (facebook.com, fb.watch)
- Instagram (instagram.com)
- Twitter/X (twitter.com, x.com)
- And 1000+ other sites supported by yt-dlp

Performance improvements:
- Background download support with ThreadPoolExecutor
- Reduced timeout for faster error handling
- Non-blocking subprocess calls
"""

import os
import re
import json
import subprocess
import logging
import shutil
import sys
import threading
import hashlib
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from datetime import datetime

logger = logging.getLogger(__name__)

# Thread pool for background downloads
_download_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='youtube_')
_active_downloads: Dict[str, Future] = {}  # Track active downloads by youtube_id
_downloads_lock = threading.Lock()

# Configuration
# Import PHOTOS_DIR after checking for circular import
try:
    from shared import PHOTOS_DIR as SHARED_PHOTOS_DIR
except ImportError:
    # Fallback if shared not available
    SHARED_PHOTOS_DIR = os.getenv('PHOTOS_DIR', './photos')

# Use PHOTOS_DIR for videos so they appear in the gallery
VIDEOS_DIR = os.getenv('VIDEOS_DIR', None) or SHARED_PHOTOS_DIR
KEYFRAMES_DIR = os.getenv('KEYFRAMES_DIR', os.path.join('data', 'youtube_keyframes'))
SUBTITLES_DIR = os.getenv('SUBTITLES_DIR', os.path.join('data', 'youtube_subtitles'))
PREFERRED_FORMAT = os.getenv('YT_FORMAT', 'bestvideo[height<=1080]+bestaudio/best[height<=1080]')
KEYFRAME_INTERVAL = int(os.getenv('KEYFRAME_INTERVAL', '30'))  # seconds between keyframes

# Ensure directories exist
for directory in [VIDEOS_DIR, KEYFRAMES_DIR, SUBTITLES_DIR]:
    os.makedirs(directory, exist_ok=True)


class YouTubeService:
    """Service for downloading and processing YouTube videos"""

    def __init__(self, db=None):
        self.db = db
        self.videos_dir = VIDEOS_DIR
        self.keyframes_dir = KEYFRAMES_DIR
        self.subtitles_dir = SUBTITLES_DIR
        self.ytdlp_command = self._find_ytdlp_command()
        self.ffmpeg_cmd = self._find_ffmpeg_command()
        self.ffprobe_cmd = self._find_ffprobe_command()
    
    def _find_ytdlp_command(self) -> list:
        """Find yt-dlp executable or use python -m yt_dlp"""
        # First try to find yt-dlp in PATH
        ytdlp_path = shutil.which('yt-dlp')
        if ytdlp_path:
            return [ytdlp_path]
        
        # Check for yt-dlp.exe in Python Scripts directory (Windows)
        if sys.platform == 'win32':
            scripts_dir = os.path.join(sys.prefix, 'Scripts')
            ytdlp_exe = os.path.join(scripts_dir, 'yt-dlp.exe')
            if os.path.exists(ytdlp_exe):
                return [ytdlp_exe]
        
        # Fallback to python -m yt_dlp
        return [sys.executable, '-m', 'yt_dlp']

    def _find_ffmpeg_command(self) -> str:
        """Find ffmpeg executable - check local folder first, then PATH"""
        # Check for ffmpeg.exe in current directory (Windows local install)
        local_ffmpeg = os.path.join(os.getcwd(), 'ffmpeg.exe')
        if os.path.exists(local_ffmpeg):
            return local_ffmpeg

        # Check in PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            return ffmpeg_path

        # Fallback - hope it's in PATH
        return 'ffmpeg'

    def _find_ffprobe_command(self) -> str:
        """Find ffprobe executable - check local folder first, then PATH"""
        # Check for ffprobe.exe in current directory (Windows local install)
        local_ffprobe = os.path.join(os.getcwd(), 'ffprobe.exe')
        if os.path.exists(local_ffprobe):
            return local_ffprobe

        # Check in PATH
        ffprobe_path = shutil.which('ffprobe')
        if ffprobe_path:
            return ffprobe_path

        # Fallback - hope it's in PATH
        return 'ffprobe'

    def detect_platform(self, url: str) -> str:
        """Detect the video platform from URL"""
        url_lower = url.lower()

        if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
            return 'youtube'
        elif 'tiktok.com' in url_lower:
            return 'tiktok'
        elif 'facebook.com' in url_lower or 'fb.watch' in url_lower or 'fb.com' in url_lower:
            return 'facebook'
        elif 'instagram.com' in url_lower:
            return 'instagram'
        elif 'twitter.com' in url_lower or 'x.com' in url_lower:
            return 'twitter'
        elif 'vimeo.com' in url_lower:
            return 'vimeo'
        elif 'dailymotion.com' in url_lower:
            return 'dailymotion'
        elif 'twitch.tv' in url_lower:
            return 'twitch'
        else:
            return 'other'

    def extract_video_id(self, url: str) -> str:
        """Extract video ID from URL or generate one for the platform"""
        platform = self.detect_platform(url)

        if platform == 'youtube':
            # Try to extract YouTube ID
            patterns = [
                r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)([a-zA-Z0-9_-]{11})',
                r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
            ]
            for pattern in patterns:
                match = re.search(pattern, url)
                if match:
                    return match.group(1)
            # Check if it's already just an ID
            if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
                return url

        elif platform == 'tiktok':
            # Extract TikTok video ID
            match = re.search(r'/video/(\d+)', url)
            if match:
                return f"tt_{match.group(1)}"
            # Handle short URLs
            match = re.search(r'tiktok\.com/@[^/]+/video/(\d+)', url)
            if match:
                return f"tt_{match.group(1)}"

        elif platform == 'facebook':
            # Extract Facebook video ID
            match = re.search(r'/videos/(\d+)', url)
            if match:
                return f"fb_{match.group(1)}"
            match = re.search(r'v=(\d+)', url)
            if match:
                return f"fb_{match.group(1)}"

        elif platform == 'instagram':
            # Extract Instagram post ID
            match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
            if match:
                return f"ig_{match.group(1)}"

        elif platform == 'twitter':
            # Extract Twitter/X video ID
            match = re.search(r'/status/(\d+)', url)
            if match:
                return f"tw_{match.group(1)}"

        # Fallback: generate hash-based ID from URL
        url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
        return f"{platform[:2]}_{url_hash}"

    def extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats (legacy method)"""
        video_id = self.extract_video_id(url)
        # For non-YouTube platforms, we still return an ID
        return video_id if video_id else None

    def get_video_info(self, url: str) -> Optional[Dict]:
        """
        Get video metadata without downloading

        Args:
            url: Video URL from any supported platform

        Returns:
            Dict with video metadata or None if failed
        """
        video_id = self.extract_video_id(url)
        platform = self.detect_platform(url)

        if not video_id:
            error_msg = f"Could not extract video ID from URL: '{url}'"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Check if yt-dlp is available using the found command
        try:
            result = subprocess.run(
                self.ytdlp_command + ['--version'],
                capture_output=True,
                timeout=10,
                text=True
            )
            if result.returncode != 0:
                logger.warning(f"yt-dlp version check failed: {result.stderr}")
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
            logger.warning(f"Could not verify yt-dlp installation: {e}")

        # Build the URL to use
        if platform == 'youtube' and len(video_id) == 11:
            fetch_url = f'https://www.youtube.com/watch?v={video_id}'
        else:
            fetch_url = url  # Use original URL for other platforms

        try:
            result = subprocess.run(
                self.ytdlp_command + [
                    '--dump-json',
                    '--no-download',
                    fetch_url
                ],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr}")
                return None

            info = json.loads(result.stdout)

            # Extract subtitle languages
            subtitle_langs = []
            if info.get('subtitles'):
                subtitle_langs.extend(list(info['subtitles'].keys()))
            if info.get('automatic_captions'):
                for lang in info['automatic_captions'].keys():
                    if lang not in subtitle_langs:
                        subtitle_langs.append(f"{lang} (auto)")

            return {
                'youtube_id': video_id,  # Keep for compatibility
                'video_id': video_id,
                'platform': platform,
                'title': info.get('title'),
                'channel_name': info.get('channel') or info.get('uploader'),
                'channel_id': info.get('channel_id'),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'upload_date': info.get('upload_date'),
                'thumbnail_url': info.get('thumbnail'),
                'webpage_url': info.get('webpage_url') or url,
                'categories': info.get('categories', []),
                'description': info.get('description'),
                'resolution': f"{info.get('width', 0)}x{info.get('height', 0)}",
                'fps': info.get('fps'),
                'vcodec': info.get('vcodec'),
                'acodec': info.get('acodec'),
                'subtitle_languages': subtitle_langs,
                'has_subtitles': bool(subtitle_langs),
            }

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp timeout while getting video info")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse yt-dlp output: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            return None

    def download_video(self, url: str, download_subtitles: bool = True,
                       original_subtitles: bool = True,
                       extract_keyframes: bool = True,
                       quality: str = '1080',
                       progress_callback=None) -> Optional[Dict]:
        """
        Download a video from YouTube, TikTok, Facebook or other platforms

        Args:
            url: Video URL from any supported platform
            download_subtitles: Whether to download auto-generated subtitles
            original_subtitles: Whether to download original subtitles
            extract_keyframes: Whether to extract keyframes
            quality: Video quality (best, 1080, 720, 480, 360)
            progress_callback: Optional callback(stage, progress, message)

        Returns:
            Dict with download results or None if failed
        """
        video_id = self.extract_video_id(url)
        platform = self.detect_platform(url)

        if not video_id:
            logger.error(f"Could not extract video ID from URL: {url}")
            return None

        logger.info(f"Downloading video: platform={platform}, video_id={video_id}")

        # Check if already downloaded
        if self.db:
            existing = self.db.get_youtube_video_by_youtube_id(video_id)
            if existing:
                logger.info(f"Video {video_id} already exists")
                return {
                    'status': 'exists',
                    'youtube_id': video_id,
                    'video': existing
                }

        if progress_callback:
            progress_callback('info', 0, 'Getting video information...')

        # Get video info first
        info = self.get_video_info(url)
        if not info:
            return None

        if progress_callback:
            progress_callback('download', 10, f'Downloading: {info["title"]}')

        # Create directories - save video directly in PHOTOS_DIR
        video_dir = self.videos_dir  # Use PHOTOS_DIR directly (no subdirectory)
        keyframe_dir = os.path.join(self.keyframes_dir, video_id)
        subtitle_dir = os.path.join(self.subtitles_dir, video_id)

        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(keyframe_dir, exist_ok=True)
        os.makedirs(subtitle_dir, exist_ok=True)

        # Build yt-dlp command - save directly to PHOTOS_DIR with descriptive name
        # Use title for filename (sanitized)
        safe_title = re.sub(r'[^\w\s-]', '', info.get('title', video_id)).strip()[:100]
        safe_title = re.sub(r'[-\s]+', '_', safe_title)
        output_template = os.path.join(video_dir, f'{safe_title}_{video_id}.%(ext)s')

        # Build format string based on quality setting
        if quality == 'best':
            format_str = 'bestvideo+bestaudio/best'
        else:
            height = int(quality)
            format_str = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'

        cmd = self.ytdlp_command + [
            '-f', format_str,
            '--merge-output-format', 'mp4',
            '-o', output_template,
            '--no-playlist',
        ]

        # Add subtitle options
        sub_langs = []
        if download_subtitles:
            # Auto-generated subtitles (usually English)
            cmd.append('--write-auto-subs')
            sub_langs.append('en')

        if original_subtitles:
            # Original manual subtitles in all available languages
            cmd.append('--write-subs')
            sub_langs.append('all')

        if sub_langs:
            cmd.extend([
                '--sub-langs', ','.join(set(sub_langs)),
                '--sub-format', 'vtt/srt/best',
                '--convert-subs', 'vtt',
            ])

        # Add common options
        cmd.extend([
            '--retries', '3',
            '--fragment-retries', '3',
            '--ignore-errors',  # Continue downloading even if subtitles fail
            '--no-abort-on-error',  # Don't abort on non-fatal errors
        ])

        # Add platform-specific options
        if platform == 'youtube':
            cmd.extend([
                '--extractor-args', 'youtube:player_client=android',  # Use android client (more reliable)
            ])
            download_url = f'https://www.youtube.com/watch?v={video_id}'
        elif platform == 'tiktok':
            # TikTok doesn't support subtitles in the same way
            cmd.extend([
                '--extractor-args', 'tiktok:api_hostname=api22-normal-c-useast2a.tiktokv.com',
            ])
            download_url = url
        elif platform == 'facebook':
            # Facebook may require cookies for some videos
            download_url = url
        else:
            # Use original URL for other platforms
            download_url = url

        cmd.append(download_url)

        # Log the command being run
        logger.info(f"Running yt-dlp command: {' '.join(cmd)}")

        try:
            # Run yt-dlp
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            # Log yt-dlp output for debugging
            if result.stdout:
                logger.info(f"yt-dlp stdout: {result.stdout[:2000]}")
            if result.stderr:
                logger.warning(f"yt-dlp stderr: {result.stderr[:2000]}")

            # Find the downloaded video file - MUST contain the video_id in filename
            video_file = None
            if os.path.exists(video_dir):
                video_extensions = ('.mp4', '.mkv', '.webm', '.avi', '.mov')
                for file in os.listdir(video_dir):
                    # Only match files that contain the video_id (our naming convention)
                    # Also skip partial download files (.part, .temp)
                    if video_id in file and file.endswith(video_extensions):
                        if not file.endswith('.part') and '.temp' not in file:
                            full_path = os.path.join(video_dir, file)
                            if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
                                video_file = full_path
                                print(f"[YT DEBUG] Found matching video file: {file}")
                                break

            # Check if download succeeded or if video file exists despite errors
            if result.returncode != 0:
                if video_file and os.path.exists(video_file):
                    # Video was downloaded, but some operations (like subtitles) failed
                    # This is acceptable - we can continue without subtitles
                    logger.warning(f"Video downloaded but some operations failed: {result.stderr[:200]}")
                else:
                    # No video file found, this is a real error
                    logger.error(f"yt-dlp download failed: {result.stderr}")
                    logger.error(f"Looked in directory: {video_dir}")
                    logger.error(f"Files in directory: {os.listdir(video_dir) if os.path.exists(video_dir) else 'Directory does not exist'}")
                    return None
            elif not video_file:
                # Command succeeded but no video file found - strange
                logger.error("Video file not found after successful download")
                logger.error(f"Looked in directory: {video_dir}")
                logger.error(f"Files in directory: {os.listdir(video_dir) if os.path.exists(video_dir) else 'Directory does not exist'}")
                return None
            
            logger.info(f"Video file found: {video_file}")
            print(f"[YT DEBUG] Video file found: {video_file}")
            print(f"[YT DEBUG] Video dir: {video_dir}")
            print(f"[YT DEBUG] Files in dir: {os.listdir(video_dir)}")

            if progress_callback:
                progress_callback('download', 50, 'Video downloaded successfully')

            # Get video dimensions using ffprobe
            width, height, file_size = self._get_video_metadata(video_file)

            # Move subtitle files to subtitle directory
            subtitle_files = []
            logger.info(f"Looking for subtitle files in: {video_dir}")
            for file in os.listdir(video_dir):
                logger.info(f"Found file: {file}")
                if file.endswith('.vtt'):
                    src = os.path.join(video_dir, file)
                    dst = os.path.join(subtitle_dir, file)
                    try:
                        # Remove existing file if it exists
                        if os.path.exists(dst):
                            os.remove(dst)
                            logger.info(f"Removed existing subtitle file: {dst}")
                        os.rename(src, dst)
                        subtitle_files.append(dst)
                        logger.info(f"Moved subtitle file: {file} -> {dst}")
                    except Exception as e:
                        logger.error(f"Error moving subtitle file {file}: {e}")
                        # Try to use the file from source location instead
                        if os.path.exists(src):
                            subtitle_files.append(src)
                            logger.info(f"Using subtitle from source: {src}")

            logger.info(f"Total subtitle files found: {len(subtitle_files)}")

            if progress_callback:
                progress_callback('processing', 60, 'Processing subtitles...')

            # Parse subtitles
            parsed_subtitles = {}
            for sub_file in subtitle_files:
                lang = self._extract_language_from_filename(sub_file)
                logger.info(f"Parsing subtitle file: {sub_file}, detected language: {lang}")
                subtitles = self._parse_vtt(sub_file)
                logger.info(f"Parsed {len(subtitles)} subtitle entries from {sub_file}")
                if subtitles:
                    parsed_subtitles[lang] = subtitles

            # Extract keyframes
            keyframes = []
            if extract_keyframes:
                if progress_callback:
                    progress_callback('keyframes', 70, 'Extracting keyframes...')
                keyframes = self._extract_keyframes(video_file, keyframe_dir, info.get('duration', 0))

            if progress_callback:
                progress_callback('database', 90, 'Saving to database...')

            # Save to database
            result_data = {
                'status': 'success',
                'youtube_id': video_id,  # Keep for compatibility
                'video_id': video_id,
                'platform': platform,
                'video_path': video_file,
                'title': info['title'],
                'duration': info['duration'],
                'width': width,
                'height': height,
                'file_size': file_size,
                'subtitle_files': subtitle_files,
                'parsed_subtitles': parsed_subtitles,
                'keyframes': keyframes,
                'metadata': info
            }

            if self.db:
                # Calculate relative path from PHOTOS_DIR for database storage
                # Use just filename (relative to PHOTOS_DIR) like other images
                filename_only = os.path.basename(video_file)
                
                print(f"[YT DEBUG] Adding video to database: filepath={filename_only}")

                # Add to images table with just filename (like upload/scan functions do)
                image_id = self.db.add_image(
                    filepath=filename_only,
                    filename=filename_only,
                    width=width,
                    height=height,
                    file_size=file_size,
                    media_type='video'
                )

                if image_id:
                    print(f"[YT DEBUG] ✅ Video added to images table: image_id={image_id}")
                else:
                    print(f"[YT DEBUG] ❌ add_image returned None - video may already exist")
                    # Try to get existing image_id
                    try:
                        conn = self.db.get_connection()
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM images WHERE filepath = ? OR filename = ?", (filename_only, filename_only))
                        result = cursor.fetchone()
                        if result:
                            image_id = result['id']
                            logger.info(f"Video already exists in database with image_id: {image_id}")
                        conn.close()
                    except Exception as e:
                        logger.error(f"Error checking existing video: {e}")

                if image_id:
                    # Add video metadata (works for all platforms, stored in youtube_videos table)
                    info['subtitle_languages'] = list(parsed_subtitles.keys())
                    info['platform'] = platform
                    print(f"[YT DEBUG] 🎬 Adding video metadata: image_id={image_id}, video_id={video_id}, platform={platform}")
                    yt_video_id = self.db.add_youtube_video(image_id, video_id, info)

                    if yt_video_id:
                        print(f"[YT DEBUG] ✅ YouTube video added to youtube_videos: yt_video_id={yt_video_id}")
                        result_data['image_id'] = image_id
                        result_data['youtube_video_id'] = yt_video_id

                        # Add subtitles to database
                        for lang, subs in parsed_subtitles.items():
                            logger.info(f"📝 Adding {len(subs)} subtitles for language: {lang}")
                            self.db.add_video_subtitles_batch(yt_video_id, lang, subs)

                        # Add keyframes to database
                        for kf in keyframes:
                            self.db.add_video_keyframe(
                                yt_video_id,
                                kf['frame_number'],
                                kf['timestamp_ms'],
                                kf['filepath']
                            )
                        print(f"[YT DEBUG] 🖼️ Added {len(keyframes)} keyframes")
                    else:
                        print(f"[YT DEBUG] ❌ add_youtube_video returned None for image_id={image_id}")
                else:
                    print(f"[YT DEBUG] ❌ No image_id - cannot add YouTube metadata")

            if progress_callback:
                progress_callback('complete', 100, 'Download complete!')

            return result_data

        except subprocess.TimeoutExpired:
            logger.error("yt-dlp download timeout")
            return None
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return None

    def _get_video_metadata(self, video_path: str) -> Tuple[int, int, int]:
        """Get video dimensions and file size using ffprobe"""
        try:
            result = subprocess.run([
                self.ffprobe_cmd,  # Use local ffprobe if available
                '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height',
                '-of', 'json',
                video_path
            ], capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                streams = data.get('streams', [])
                if streams:
                    width = streams[0].get('width', 0)
                    height = streams[0].get('height', 0)
                    file_size = os.path.getsize(video_path)
                    return width, height, file_size

        except Exception as e:
            logger.error(f"Error getting video metadata: {e}")

        file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
        return 0, 0, file_size

    def _extract_language_from_filename(self, filename: str) -> str:
        """Extract language code from subtitle filename"""
        # Pattern: video_id.lang.vtt or video_id.lang-auto.vtt
        name = os.path.basename(filename)
        parts = name.replace('.vtt', '').split('.')

        if len(parts) >= 2:
            lang_part = parts[-1]
            # Remove any auto-generated suffix
            lang_part = lang_part.replace('-auto', '').split('-')[0]
            return lang_part

        return 'unknown'

    def _parse_vtt(self, vtt_path: str) -> List[Dict]:
        """
        Parse VTT subtitle file into list of subtitle entries

        Returns:
            List of dicts with start_time_ms, end_time_ms, text
        """
        if not os.path.exists(vtt_path):
            return []

        subtitles = []
        try:
            with open(vtt_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Remove WEBVTT header and metadata
            lines = content.split('\n')
            in_cue = False
            current_times = None
            current_text = []

            for line in lines:
                line = line.strip()

                # Skip header and empty lines
                if line.startswith('WEBVTT') or line.startswith('Kind:') or line.startswith('Language:'):
                    continue

                # Check for timestamp line
                time_match = re.match(
                    r'(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})',
                    line
                )

                if time_match:
                    # Save previous cue if exists
                    if current_times and current_text:
                        text = ' '.join(current_text)
                        # Remove HTML tags and formatting
                        text = re.sub(r'<[^>]+>', '', text)
                        text = text.strip()

                        if text:
                            subtitles.append({
                                'start_time_ms': current_times[0],
                                'end_time_ms': current_times[1],
                                'text': text
                            })

                    # Parse new timestamps
                    start_str, end_str = time_match.groups()
                    current_times = (
                        self._vtt_time_to_ms(start_str),
                        self._vtt_time_to_ms(end_str)
                    )
                    current_text = []
                    in_cue = True

                elif in_cue and line:
                    current_text.append(line)
                elif not line:
                    in_cue = False

            # Don't forget the last cue
            if current_times and current_text:
                text = ' '.join(current_text)
                text = re.sub(r'<[^>]+>', '', text)
                text = text.strip()

                if text:
                    subtitles.append({
                        'start_time_ms': current_times[0],
                        'end_time_ms': current_times[1],
                        'text': text
                    })

        except Exception as e:
            logger.error(f"Error parsing VTT file {vtt_path}: {e}")

        return subtitles

    def _vtt_time_to_ms(self, time_str: str) -> int:
        """Convert VTT timestamp to milliseconds"""
        # Handle both HH:MM:SS.mmm and MM:SS.mmm formats
        parts = time_str.split(':')

        if len(parts) == 3:
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds, ms = parts[2].split('.')
            seconds = int(seconds)
            ms = int(ms)
        elif len(parts) == 2:
            hours = 0
            minutes = int(parts[0])
            seconds, ms = parts[1].split('.')
            seconds = int(seconds)
            ms = int(ms)
        else:
            return 0

        return (hours * 3600 + minutes * 60 + seconds) * 1000 + ms

    def _extract_keyframes(self, video_path: str, output_dir: str,
                           duration: int) -> List[Dict]:
        """
        Extract keyframes from video at regular intervals

        Args:
            video_path: Path to video file
            output_dir: Directory to save keyframes
            duration: Video duration in seconds

        Returns:
            List of keyframe info dicts
        """
        if not duration or duration <= 0:
            return []

        keyframes = []
        frame_number = 0

        # Calculate timestamps for keyframes
        timestamps = []
        current = 0
        while current < duration:
            timestamps.append(current)
            current += KEYFRAME_INTERVAL

        # Always include a frame near the end
        if duration > KEYFRAME_INTERVAL and (duration - timestamps[-1]) > 5:
            timestamps.append(duration - 2)

        for timestamp in timestamps:
            output_file = os.path.join(output_dir, f'frame_{frame_number:04d}.jpg')

            try:
                result = subprocess.run([
                    self.ffmpeg_cmd,  # Use local ffmpeg if available
                    '-ss', str(timestamp),
                    '-i', video_path,
                    '-vframes', '1',
                    '-q:v', '2',
                    '-y',
                    output_file
                ], capture_output=True, timeout=30)

                if result.returncode == 0 and os.path.exists(output_file):
                    keyframes.append({
                        'frame_number': frame_number,
                        'timestamp_ms': int(timestamp * 1000),
                        'filepath': output_file
                    })
                    frame_number += 1

            except Exception as e:
                logger.error(f"Error extracting keyframe at {timestamp}s: {e}")

        return keyframes

    def format_duration(self, seconds: int) -> str:
        """Format duration in seconds to human-readable string"""
        if not seconds:
            return "Unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def format_views(self, count: int) -> str:
        """Format view count to human-readable string"""
        if not count:
            return "0"

        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f}B"
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)

    # ============ BACKGROUND DOWNLOAD METHODS ============

    def download_video_async(
            self,
            url: str,
            download_subtitles: bool = True,
            extract_keyframes: bool = True,
            on_complete: Callable = None,
            on_error: Callable = None
    ) -> str:
        """
        Start a background video download (non-blocking).

        Args:
            url: YouTube URL or video ID
            download_subtitles: Whether to download subtitles
            extract_keyframes: Whether to extract keyframes
            on_complete: Callback(result_dict) when download finishes
            on_error: Callback(exception) when download fails

        Returns:
            youtube_id for tracking the download status
        """
        youtube_id = self.extract_youtube_id(url)
        if not youtube_id:
            raise ValueError(f"Invalid YouTube URL: {url}")

        # Check if already downloading
        with _downloads_lock:
            if youtube_id in _active_downloads:
                future = _active_downloads[youtube_id]
                if not future.done():
                    logger.info(f"Download already in progress for {youtube_id}")
                    return youtube_id

        def download_task():
            try:
                result = self.download_video(
                    url,
                    download_subtitles=download_subtitles,
                    extract_keyframes=extract_keyframes
                )
                if on_complete:
                    on_complete(result)
                return result
            except Exception as e:
                logger.error(f"Background download failed for {youtube_id}: {e}")
                if on_error:
                    on_error(e)
                raise
            finally:
                # Clean up tracking
                with _downloads_lock:
                    _active_downloads.pop(youtube_id, None)

        # Submit to thread pool
        future = _download_executor.submit(download_task)

        with _downloads_lock:
            _active_downloads[youtube_id] = future

        logger.info(f"Started background download for {youtube_id}")
        return youtube_id

    def get_download_status(self, youtube_id: str) -> dict:
        """
        Get the status of a background download.

        Returns:
            dict with 'status' ('pending', 'running', 'completed', 'failed', 'not_found')
            and optional 'result' or 'error'
        """
        with _downloads_lock:
            if youtube_id not in _active_downloads:
                return {'status': 'not_found'}

            future = _active_downloads[youtube_id]

            if not future.done():
                return {'status': 'running'}

            try:
                result = future.result(timeout=0)
                return {'status': 'completed', 'result': result}
            except Exception as e:
                return {'status': 'failed', 'error': str(e)}

    def cancel_download(self, youtube_id: str) -> bool:
        """
        Attempt to cancel a background download.

        Returns:
            True if cancelled, False if not found or already completed
        """
        with _downloads_lock:
            if youtube_id not in _active_downloads:
                return False

            future = _active_downloads[youtube_id]
            cancelled = future.cancel()

            if cancelled:
                _active_downloads.pop(youtube_id, None)
                logger.info(f"Cancelled download for {youtube_id}")

            return cancelled

    def get_active_downloads(self) -> List[str]:
        """Get list of youtube_ids currently being downloaded"""
        with _downloads_lock:
            return [
                yt_id for yt_id, future in _active_downloads.items()
                if not future.done()
            ]
