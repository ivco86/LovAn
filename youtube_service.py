#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube Download Service for AI Gallery
Downloads videos using yt-dlp, extracts metadata, subtitles, and keyframes
"""

import os
import re
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

# Configuration
VIDEOS_DIR = os.getenv('VIDEOS_DIR', 'videos')
KEYFRAMES_DIR = os.getenv('KEYFRAMES_DIR', 'keyframes')
SUBTITLES_DIR = os.getenv('SUBTITLES_DIR', 'subtitles')
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

    def extract_youtube_id(self, url: str) -> Optional[str]:
        """Extract YouTube video ID from various URL formats"""
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

        return None

    def get_video_info(self, url: str) -> Optional[Dict]:
        """
        Get video metadata without downloading

        Args:
            url: YouTube URL or video ID

        Returns:
            Dict with video metadata or None if failed
        """
        youtube_id = self.extract_youtube_id(url)
        if not youtube_id:
            logger.error(f"Invalid YouTube URL: {url}")
            return None

        try:
            result = subprocess.run([
                'yt-dlp',
                '--dump-json',
                '--no-download',
                f'https://www.youtube.com/watch?v={youtube_id}'
            ], capture_output=True, text=True, timeout=60)

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
                'youtube_id': youtube_id,
                'title': info.get('title'),
                'channel_name': info.get('channel') or info.get('uploader'),
                'channel_id': info.get('channel_id'),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'upload_date': info.get('upload_date'),
                'thumbnail_url': info.get('thumbnail'),
                'webpage_url': info.get('webpage_url'),
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
                       extract_keyframes: bool = True,
                       progress_callback=None) -> Optional[Dict]:
        """
        Download a YouTube video with metadata, subtitles, and keyframes

        Args:
            url: YouTube URL or video ID
            download_subtitles: Whether to download subtitles
            extract_keyframes: Whether to extract keyframes
            progress_callback: Optional callback(stage, progress, message)

        Returns:
            Dict with download results or None if failed
        """
        youtube_id = self.extract_youtube_id(url)
        if not youtube_id:
            logger.error(f"Invalid YouTube URL: {url}")
            return None

        # Check if already downloaded
        if self.db:
            existing = self.db.get_youtube_video_by_youtube_id(youtube_id)
            if existing:
                logger.info(f"Video {youtube_id} already exists")
                return {
                    'status': 'exists',
                    'youtube_id': youtube_id,
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

        # Create video-specific directories
        video_dir = os.path.join(self.videos_dir, youtube_id)
        keyframe_dir = os.path.join(self.keyframes_dir, youtube_id)
        subtitle_dir = os.path.join(self.subtitles_dir, youtube_id)

        os.makedirs(video_dir, exist_ok=True)
        os.makedirs(keyframe_dir, exist_ok=True)
        os.makedirs(subtitle_dir, exist_ok=True)

        # Build yt-dlp command
        output_template = os.path.join(video_dir, '%(id)s.%(ext)s')
        cmd = [
            'yt-dlp',
            '-f', PREFERRED_FORMAT,
            '--merge-output-format', 'mp4',
            '-o', output_template,
            '--no-playlist',
        ]

        # Add subtitle options
        if download_subtitles:
            cmd.extend([
                '--write-subs',
                '--write-auto-subs',
                '--sub-langs', 'en,bg,ru,de,fr,es,it,pt,ja,ko,zh',
                '--sub-format', 'vtt/srt/best',
                '--convert-subs', 'vtt',
            ])

        cmd.append(f'https://www.youtube.com/watch?v={youtube_id}')

        try:
            # Run yt-dlp
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

            if result.returncode != 0:
                logger.error(f"yt-dlp download failed: {result.stderr}")
                return None

            # Find the downloaded video file
            video_file = None
            for file in os.listdir(video_dir):
                if file.endswith(('.mp4', '.mkv', '.webm')):
                    video_file = os.path.join(video_dir, file)
                    break

            if not video_file:
                logger.error("Video file not found after download")
                return None

            if progress_callback:
                progress_callback('download', 50, 'Video downloaded successfully')

            # Get video dimensions using ffprobe
            width, height, file_size = self._get_video_metadata(video_file)

            # Move subtitle files to subtitle directory
            subtitle_files = []
            for file in os.listdir(video_dir):
                if file.endswith('.vtt'):
                    src = os.path.join(video_dir, file)
                    dst = os.path.join(subtitle_dir, file)
                    os.rename(src, dst)
                    subtitle_files.append(dst)

            if progress_callback:
                progress_callback('processing', 60, 'Processing subtitles...')

            # Parse subtitles
            parsed_subtitles = {}
            for sub_file in subtitle_files:
                lang = self._extract_language_from_filename(sub_file)
                subtitles = self._parse_vtt(sub_file)
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
                'youtube_id': youtube_id,
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
                # Add to images table first
                image_id = self.db.add_image(
                    filepath=video_file,
                    filename=os.path.basename(video_file),
                    width=width,
                    height=height,
                    file_size=file_size,
                    media_type='video'
                )

                if image_id:
                    # Add YouTube metadata
                    info['subtitle_languages'] = list(parsed_subtitles.keys())
                    yt_video_id = self.db.add_youtube_video(image_id, youtube_id, info)

                    if yt_video_id:
                        result_data['image_id'] = image_id
                        result_data['youtube_video_id'] = yt_video_id

                        # Add subtitles to database
                        for lang, subs in parsed_subtitles.items():
                            self.db.add_video_subtitles_batch(yt_video_id, lang, subs)

                        # Add keyframes to database
                        for kf in keyframes:
                            self.db.add_video_keyframe(
                                yt_video_id,
                                kf['frame_number'],
                                kf['timestamp_ms'],
                                kf['filepath']
                            )

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
                'ffprobe',
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
                    'ffmpeg',
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
