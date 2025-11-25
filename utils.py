"""
Utility functions for AI Gallery
Helper functions for file handling, video processing, and image operations

Includes:
- Simple in-memory rate limiter
- File handling utilities
- Video frame extraction
"""

import os
import time
import threading
from collections import defaultdict
from functools import wraps
from flask import request, jsonify
from PIL import Image, ImageDraw
from pathlib import Path


# ============ RATE LIMITER ============

class RateLimiter:
    """
    Simple in-memory rate limiter.
    Tracks requests per IP with sliding window.
    """

    def __init__(self):
        self._requests = defaultdict(list)  # IP -> list of timestamps
        self._lock = threading.Lock()

    def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Identifier (usually IP address)
            limit: Max requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            # Clean old requests
            self._requests[key] = [t for t in self._requests[key] if t > cutoff]

            # Check limit
            if len(self._requests[key]) >= limit:
                return False

            # Record this request
            self._requests[key].append(now)
            return True

    def get_remaining(self, key: str, limit: int, window_seconds: int) -> int:
        """Get remaining requests for a key"""
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            recent = [t for t in self._requests[key] if t > cutoff]
            return max(0, limit - len(recent))


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(limit: int = 10, window: int = 60):
    """
    Decorator to rate limit API endpoints.

    Args:
        limit: Maximum requests per window
        window: Time window in seconds

    Usage:
        @app.route('/api/analyze')
        @rate_limit(limit=5, window=60)  # 5 requests per minute
        def analyze():
            ...
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get client identifier (IP address)
            client_ip = request.remote_addr or 'unknown'

            if not _rate_limiter.is_allowed(client_ip, limit, window):
                remaining = _rate_limiter.get_remaining(client_ip, limit, window)
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'message': f'Too many requests. Please wait before trying again.',
                    'limit': limit,
                    'window_seconds': window,
                    'remaining': remaining
                }), 429

            return f(*args, **kwargs)
        return wrapped
    return decorator


# ============ API RESPONSE CACHE ============

class ResponseCache:
    """
    Simple in-memory cache for API responses.
    TTL-based expiration with automatic cleanup.
    """

    def __init__(self, default_ttl: int = 60):
        self._cache = {}  # key -> (value, expiry_time)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def get(self, key: str):
        """Get cached value if not expired"""
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
        return None

    def set(self, key: str, value, ttl: int = None):
        """Set cache value with TTL"""
        expiry = time.time() + (ttl or self._default_ttl)
        with self._lock:
            self._cache[key] = (value, expiry)

    def invalidate(self, key: str = None, pattern: str = None):
        """Invalidate specific key, pattern, or all"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            elif pattern:
                # Remove keys matching pattern
                keys_to_remove = [k for k in self._cache if pattern in k]
                for k in keys_to_remove:
                    del self._cache[k]
            else:
                self._cache.clear()

    def cleanup(self):
        """Remove expired entries"""
        now = time.time()
        with self._lock:
            expired = [k for k, (_, exp) in self._cache.items() if now >= exp]
            for k in expired:
                del self._cache[k]


# Global cache instance
_response_cache = ResponseCache(default_ttl=60)


def cache_response(ttl: int = 60, key_prefix: str = ''):
    """
    Decorator to cache API response for GET requests.

    Args:
        ttl: Cache time-to-live in seconds
        key_prefix: Optional prefix for cache key

    Usage:
        @app.route('/api/images')
        @cache_response(ttl=30)
        def get_images():
            ...

    Note: Only caches GET requests. POST/PUT/DELETE bypass cache.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Only cache GET requests
            if request.method != 'GET':
                return f(*args, **kwargs)

            # Build cache key from endpoint + query params
            cache_key = f"{key_prefix}{request.path}?{request.query_string.decode()}"

            # Check cache
            cached = _response_cache.get(cache_key)
            if cached is not None:
                return cached

            # Execute function and cache result
            result = f(*args, **kwargs)
            _response_cache.set(cache_key, result, ttl)

            return result
        return wrapped
    return decorator


def invalidate_cache(pattern: str = None):
    """Invalidate cache entries matching pattern"""
    _response_cache.invalidate(pattern=pattern)


# Try to import opencv for video frame extraction
try:
    import cv2
    HAS_OPENCV = True
except ImportError:
    HAS_OPENCV = False
    print("Warning: opencv-python not installed. Video thumbnails will use placeholders.")

# Supported file formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
VIDEO_FORMATS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.m4v'}
ALL_MEDIA_FORMATS = SUPPORTED_FORMATS | VIDEO_FORMATS


def extract_video_frame(video_path, output_path, time_sec=1.0):
    """Extract a frame from video using opencv if available"""
    if not HAS_OPENCV:
        return False

    try:
        cap = cv2.VideoCapture(video_path)

        # Set position to specified second
        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_number = int(fps * time_sec)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)

        # Read frame
        ret, frame = cap.read()
        cap.release()

        if ret:
            # Convert BGR to RGB for PIL
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            return img
        return False
    except Exception as e:
        print(f"Error extracting video frame: {e}")
        return False


def create_video_placeholder(size=500):
    """Create a placeholder thumbnail for videos when opencv is not available"""
    img = Image.new('RGB', (size, int(size * 9/16)), color='#7b2cbf')

    # Add gradient effect
    draw = ImageDraw.Draw(img, 'RGBA')
    for i in range(img.height):
        alpha = int(255 * (1 - i / img.height))
        color = (255, 0, 110, alpha)
        draw.rectangle([(0, i), (img.width, i+1)], fill=color)

    # Add play icon
    center_x, center_y = img.width // 2, img.height // 2
    icon_size = 60

    # Draw white circle
    draw.ellipse(
        [(center_x - icon_size, center_y - icon_size),
         (center_x + icon_size, center_y + icon_size)],
        fill=(255, 255, 255, 230)
    )

    # Draw play triangle
    triangle = [
        (center_x - 20, center_y - 30),
        (center_x - 20, center_y + 30),
        (center_x + 30, center_y)
    ]
    draw.polygon(triangle, fill=(123, 44, 191))

    return img


def get_image_for_analysis(filepath, media_type='image'):
    """
    Get PIL Image for AI analysis
    For images: open directly
    For videos: extract frame at 1 second
    Returns: PIL Image object or None
    """
    if media_type == 'video':
        # Try to extract frame from video
        img = extract_video_frame(filepath, None, time_sec=1.0)
        if not img:
            # Fallback to placeholder if extraction fails
            print(f"Warning: Could not extract frame from video {filepath}, using placeholder")
            img = create_video_placeholder(800)
        return img
    else:
        # Regular image
        try:
            return Image.open(filepath)
        except Exception as e:
            print(f"Error opening image {filepath}: {e}")
            return None


def get_full_filepath(filepath, photos_dir):
    """
    Convert relative filepath to absolute path.
    Handles both old format (./photos/image.jpg) and new format (image.jpg)

    Args:
        filepath: Relative or absolute file path
        photos_dir: Base photos directory

    Returns:
        Full absolute file path
    """
    if not filepath:
        return filepath

    # If already absolute path, return as-is
    if os.path.isabs(filepath):
        return filepath

    # Normalize path separators
    normalized = filepath.replace('\\', '/')
    photos_dir_normalized = photos_dir.replace('\\', '/').lstrip('./')

    # Check if path already contains photos_dir (old format)
    # Examples: "./photos/image.jpg", "photos/image.jpg", "./photos/subfolder/image.jpg"
    if (normalized.startswith(photos_dir_normalized + '/') or
        normalized.startswith('./' + photos_dir_normalized + '/')):
        # Path already includes photos_dir, return as-is
        return filepath

    # New format - relative path without photos_dir
    return os.path.join(photos_dir, filepath)


def is_safe_path(filepath, base_dir):
    """
    Security check: Ensure filepath is within base_dir (prevent path traversal)

    Args:
        filepath: File path to check
        base_dir: Base directory that should contain the file

    Returns:
        True if path is safe, False otherwise
    """
    abs_filepath = os.path.abspath(filepath)
    abs_base_dir = os.path.abspath(base_dir)

    return abs_filepath.startswith(abs_base_dir)
