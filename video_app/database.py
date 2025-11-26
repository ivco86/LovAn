"""
Database layer for Video App
Handles all SQLite operations for videos, subtitles, bookmarks, notes, vocabulary
"""

import os
import sqlite3
import json
import threading
import time
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL (Time To Live) cache for expensive operations"""

    def __init__(self, ttl_seconds: int = 60):
        self.ttl = ttl_seconds
        self._cache = {}
        self._timestamps = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        """Get cached value if not expired"""
        with self._lock:
            if key in self._cache:
                if time.time() - self._timestamps[key] < self.ttl:
                    return self._cache[key]
                else:
                    del self._cache[key]
                    del self._timestamps[key]
        return None

    def set(self, key: str, value):
        """Set cache value with current timestamp"""
        with self._lock:
            self._cache[key] = value
            self._timestamps[key] = time.time()

    def invalidate(self, key: str = None):
        """Invalidate specific key or all cache"""
        with self._lock:
            if key:
                self._cache.pop(key, None)
                self._timestamps.pop(key, None)
            else:
                self._cache.clear()
                self._timestamps.clear()


class VideoDatabase:
    def __init__(self, db_path: str = "data/gallery.db"):
        # Ensure the directory exists before creating database
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self.db_path = db_path
        self._local = threading.local()
        self._lock = threading.Lock()
        self._cache = TTLCache(ttl_seconds=60)
        self.init_database()

    def get_connection(self):
        """Get database connection with row factory and timeout"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self):
        """Context manager for database connections."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                self.db_path,
                timeout=30.0,
                check_same_thread=False
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")

        conn = self._local.conn
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close_connection(self):
        """Close the thread-local connection if it exists"""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None

    def init_database(self):
        """Initialize database schema for video tables"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Images table (for video file entries)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT UNIQUE NOT NULL,
                filename TEXT NOT NULL,
                description TEXT,
                tags TEXT,
                width INTEGER,
                height INTEGER,
                file_size INTEGER,
                is_favorite BOOLEAN DEFAULT 0,
                media_type TEXT DEFAULT 'video',
                analyzed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # YouTube videos table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS youtube_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE,
                youtube_id TEXT UNIQUE,
                title TEXT,
                channel_name TEXT,
                channel_id TEXT,
                duration INTEGER,
                view_count INTEGER,
                like_count INTEGER,
                upload_date TEXT,
                thumbnail_url TEXT,
                webpage_url TEXT,
                categories TEXT,
                video_format TEXT,
                audio_format TEXT,
                resolution TEXT,
                fps REAL,
                has_subtitles BOOLEAN DEFAULT 0,
                subtitle_languages TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        """)

        # Video keyframes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_keyframes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_video_id INTEGER NOT NULL,
                frame_number INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                filepath TEXT NOT NULL,
                description TEXT,
                tags TEXT,
                embedding_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (youtube_video_id) REFERENCES youtube_videos(id) ON DELETE CASCADE,
                UNIQUE(youtube_video_id, frame_number)
            )
        """)

        # Video subtitles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_subtitles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_video_id INTEGER NOT NULL,
                language TEXT NOT NULL,
                start_time_ms INTEGER NOT NULL,
                end_time_ms INTEGER NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (youtube_video_id) REFERENCES youtube_videos(id) ON DELETE CASCADE
            )
        """)

        # Video bookmarks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_video_id INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                color TEXT DEFAULT '#ff4444',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (youtube_video_id) REFERENCES youtube_videos(id) ON DELETE CASCADE
            )
        """)

        # Video notes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                youtube_video_id INTEGER NOT NULL,
                timestamp_ms INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (youtube_video_id) REFERENCES youtube_videos(id) ON DELETE CASCADE
            )
        """)

        # Vocabulary table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vocabulary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                translation TEXT NOT NULL,
                source_language TEXT DEFAULT 'en',
                target_language TEXT DEFAULT 'bg',
                context_sentence TEXT,
                video_id INTEGER,
                timestamp_ms INTEGER,
                notes TEXT,
                mastery_level INTEGER DEFAULT 0,
                review_count INTEGER DEFAULT 0,
                last_reviewed TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(word, source_language, target_language)
            )
        """)

        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_videos_youtube_id ON youtube_videos(youtube_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_videos_image_id ON youtube_videos(image_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_subtitles_video_id ON video_subtitles(youtube_video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_subtitles_language ON video_subtitles(language)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_keyframes_video_id ON video_keyframes(youtube_video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_bookmarks_video_id ON video_bookmarks(youtube_video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_video_notes_video_id ON video_notes(youtube_video_id)")

        conn.commit()
        conn.close()

    # ============ IMAGE/VIDEO FILE OPERATIONS ============

    def add_image(self, filepath: str, filename: str = None, file_size: int = None,
                  media_type: str = 'video', width: int = None, height: int = None) -> Optional[int]:
        """Add a video/image file entry"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO images (filepath, filename, file_size, media_type, width, height)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filepath, filename or os.path.basename(filepath), file_size, media_type, width, height))

            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            logger.error(f"Error adding image: {e}")
            return None
        finally:
            conn.close()

    def get_image(self, image_id: int) -> Optional[Dict]:
        """Get image/video by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        result = cursor.fetchone()
        conn.close()

        return dict(result) if result else None

    def update_image(self, image_id: int, **kwargs) -> bool:
        """Update image/video entry"""
        conn = self.get_connection()
        cursor = conn.cursor()

        allowed_fields = ['description', 'tags', 'is_favorite', 'width', 'height']
        updates = []
        values = []

        for field in allowed_fields:
            if field in kwargs:
                updates.append(f"{field} = ?")
                values.append(kwargs[field])

        if not updates:
            conn.close()
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(image_id)

        try:
            cursor.execute(f"""
                UPDATE images SET {', '.join(updates)}
                WHERE id = ?
            """, values)
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating image: {e}")
            return False
        finally:
            conn.close()

    def get_all_videos(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all video files"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM images
            WHERE media_type = 'video'
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    # ============ YOUTUBE VIDEO OPERATIONS ============

    def add_youtube_video(self, image_id: int, youtube_id: str, metadata: Dict) -> Optional[int]:
        """Add YouTube video metadata linked to an image entry"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute(
                "SELECT id FROM youtube_videos WHERE image_id = ? OR youtube_id = ?",
                (image_id, youtube_id)
            )
            existing = cursor.fetchone()
            if existing:
                return existing['id']

            categories = metadata.get('categories', [])
            subtitle_langs = metadata.get('subtitle_languages', [])

            cursor.execute("""
                INSERT INTO youtube_videos (
                    image_id, youtube_id, title, channel_name, channel_id,
                    duration, view_count, like_count, upload_date,
                    thumbnail_url, webpage_url, categories,
                    video_format, audio_format, resolution, fps,
                    has_subtitles, subtitle_languages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_id,
                youtube_id,
                metadata.get('title'),
                metadata.get('channel_name') or metadata.get('uploader'),
                metadata.get('channel_id'),
                metadata.get('duration'),
                metadata.get('view_count'),
                metadata.get('like_count'),
                metadata.get('upload_date'),
                metadata.get('thumbnail_url') or metadata.get('thumbnail'),
                metadata.get('webpage_url'),
                json.dumps(categories) if categories else None,
                metadata.get('video_format') or metadata.get('vcodec'),
                metadata.get('audio_format') or metadata.get('acodec'),
                metadata.get('resolution'),
                metadata.get('fps'),
                bool(subtitle_langs),
                json.dumps(subtitle_langs) if subtitle_langs else None
            ))

            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute(
                "SELECT id FROM youtube_videos WHERE youtube_id = ?",
                (youtube_id,)
            )
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            logger.error(f"Error adding YouTube video: {e}")
            return None
        finally:
            conn.close()

    def get_youtube_video(self, youtube_video_id: int) -> Optional[Dict]:
        """Get YouTube video by its ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT yv.*, i.filepath, i.filename, i.width, i.height, i.file_size
            FROM youtube_videos yv
            JOIN images i ON yv.image_id = i.id
            WHERE yv.id = ?
        """, (youtube_video_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            data = dict(result)
            if data.get('categories'):
                try:
                    data['categories'] = json.loads(data['categories'])
                except:
                    data['categories'] = []
            if data.get('subtitle_languages'):
                try:
                    data['subtitle_languages'] = json.loads(data['subtitle_languages'])
                except:
                    data['subtitle_languages'] = []
            return data
        return None

    def get_youtube_video_by_youtube_id(self, youtube_id: str) -> Optional[Dict]:
        """Get YouTube video by YouTube video ID"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT yv.*, i.filepath, i.filename, i.width, i.height, i.file_size
            FROM youtube_videos yv
            JOIN images i ON yv.image_id = i.id
            WHERE yv.youtube_id = ?
        """, (youtube_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            data = dict(result)
            if data.get('categories'):
                try:
                    data['categories'] = json.loads(data['categories'])
                except:
                    data['categories'] = []
            if data.get('subtitle_languages'):
                try:
                    data['subtitle_languages'] = json.loads(data['subtitle_languages'])
                except:
                    data['subtitle_languages'] = []
            return data
        return None

    def get_youtube_video_by_image_id(self, image_id: int) -> Optional[Dict]:
        """Get YouTube video by image_id"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT yv.*
            FROM youtube_videos yv
            WHERE yv.image_id = ?
        """, (image_id,))

        result = cursor.fetchone()
        conn.close()

        if result:
            data = dict(result)
            if data.get('categories'):
                try:
                    data['categories'] = json.loads(data['categories'])
                except:
                    data['categories'] = []
            if data.get('subtitle_languages'):
                try:
                    data['subtitle_languages'] = json.loads(data['subtitle_languages'])
                except:
                    data['subtitle_languages'] = []
            return data
        return None

    def get_all_youtube_videos(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get all YouTube videos with pagination"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT yv.*, i.filepath, i.filename, i.width, i.height, i.file_size
            FROM youtube_videos yv
            JOIN images i ON yv.image_id = i.id
            ORDER BY yv.created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))

        results = cursor.fetchall()
        conn.close()

        videos = []
        for row in results:
            data = dict(row)
            if data.get('categories'):
                try:
                    data['categories'] = json.loads(data['categories'])
                except:
                    data['categories'] = []
            if data.get('subtitle_languages'):
                try:
                    data['subtitle_languages'] = json.loads(data['subtitle_languages'])
                except:
                    data['subtitle_languages'] = []
            videos.append(data)

        return videos

    def delete_youtube_video(self, youtube_video_id: int) -> bool:
        """Delete a YouTube video and all related data"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT image_id FROM youtube_videos WHERE id = ?", (youtube_video_id,))
            result = cursor.fetchone()

            if result:
                image_id = result['image_id']
                cursor.execute("DELETE FROM youtube_videos WHERE id = ?", (youtube_video_id,))
                cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error deleting YouTube video: {e}")
            return False
        finally:
            conn.close()

    # ============ VIDEO KEYFRAMES ============

    def add_video_keyframe(self, youtube_video_id: int, frame_number: int,
                           timestamp_ms: int, filepath: str) -> Optional[int]:
        """Add a keyframe extracted from a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO video_keyframes (youtube_video_id, frame_number, timestamp_ms, filepath)
                VALUES (?, ?, ?, ?)
            """, (youtube_video_id, frame_number, timestamp_ms, filepath))

            conn.commit()
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            cursor.execute(
                "SELECT id FROM video_keyframes WHERE youtube_video_id = ? AND frame_number = ?",
                (youtube_video_id, frame_number)
            )
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            logger.error(f"Error adding keyframe: {e}")
            return None
        finally:
            conn.close()

    def get_video_keyframes(self, youtube_video_id: int) -> List[Dict]:
        """Get all keyframes for a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM video_keyframes
            WHERE youtube_video_id = ?
            ORDER BY frame_number
        """, (youtube_video_id,))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    # ============ VIDEO SUBTITLES ============

    def add_video_subtitle(self, youtube_video_id: int, language: str,
                           start_time_ms: int, end_time_ms: int, text: str) -> Optional[int]:
        """Add a subtitle entry for a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO video_subtitles (youtube_video_id, language, start_time_ms, end_time_ms, text)
                VALUES (?, ?, ?, ?, ?)
            """, (youtube_video_id, language, start_time_ms, end_time_ms, text))

            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding subtitle: {e}")
            return None
        finally:
            conn.close()

    def add_video_subtitles_batch(self, youtube_video_id: int, language: str,
                                  subtitles: List[Dict]) -> int:
        """Add multiple subtitle entries for a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        count = 0
        try:
            for sub in subtitles:
                cursor.execute("""
                    INSERT INTO video_subtitles (youtube_video_id, language, start_time_ms, end_time_ms, text)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    youtube_video_id,
                    language,
                    sub['start_time_ms'],
                    sub['end_time_ms'],
                    sub['text']
                ))
                count += 1

            conn.commit()
        except Exception as e:
            logger.error(f"Error adding subtitles batch: {e}")
        finally:
            conn.close()

        return count

    def get_video_subtitles(self, youtube_video_id: int, language: str = None) -> List[Dict]:
        """Get subtitles for a video, optionally filtered by language"""
        conn = self.get_connection()
        cursor = conn.cursor()

        if language:
            cursor.execute("""
                SELECT * FROM video_subtitles
                WHERE youtube_video_id = ? AND language = ?
                ORDER BY start_time_ms
            """, (youtube_video_id, language))
        else:
            cursor.execute("""
                SELECT * FROM video_subtitles
                WHERE youtube_video_id = ?
                ORDER BY language, start_time_ms
            """, (youtube_video_id,))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def search_video_subtitles(self, query: str, limit: int = 50) -> List[Dict]:
        """Search across all video subtitles"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT vs.*, yv.youtube_id, yv.title, yv.channel_name, i.filepath
            FROM video_subtitles vs
            JOIN youtube_videos yv ON vs.youtube_video_id = yv.id
            JOIN images i ON yv.image_id = i.id
            WHERE vs.text LIKE ?
            ORDER BY yv.created_at DESC
            LIMIT ?
        """, (f'%{query}%', limit))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def get_full_transcript(self, youtube_video_id: int, language: str = None) -> str:
        """Get full transcript text for a video"""
        subtitles = self.get_video_subtitles(youtube_video_id, language)
        return ' '.join(sub.get('text', '') for sub in subtitles)

    # ============ VIDEO BOOKMARKS ============

    def add_video_bookmark(self, youtube_video_id: int, timestamp_ms: int, title: str,
                          description: str = None, color: str = '#ff4444') -> Optional[int]:
        """Add a bookmark/chapter to a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO video_bookmarks (youtube_video_id, timestamp_ms, title, description, color)
                VALUES (?, ?, ?, ?, ?)
            """, (youtube_video_id, timestamp_ms, title, description, color))

            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding bookmark: {e}")
            return None
        finally:
            conn.close()

    def get_video_bookmarks(self, youtube_video_id: int) -> List[Dict]:
        """Get all bookmarks for a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM video_bookmarks
            WHERE youtube_video_id = ?
            ORDER BY timestamp_ms
        """, (youtube_video_id,))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def update_video_bookmark(self, bookmark_id: int, title: str = None,
                             description: str = None, color: str = None,
                             timestamp_ms: int = None) -> bool:
        """Update a bookmark"""
        conn = self.get_connection()
        cursor = conn.cursor()

        updates = []
        values = []

        if title is not None:
            updates.append("title = ?")
            values.append(title)
        if description is not None:
            updates.append("description = ?")
            values.append(description)
        if color is not None:
            updates.append("color = ?")
            values.append(color)
        if timestamp_ms is not None:
            updates.append("timestamp_ms = ?")
            values.append(timestamp_ms)

        if not updates:
            return False

        values.append(bookmark_id)

        try:
            cursor.execute(f"""
                UPDATE video_bookmarks SET {', '.join(updates)}
                WHERE id = ?
            """, values)

            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating bookmark: {e}")
            return False
        finally:
            conn.close()

    def delete_video_bookmark(self, bookmark_id: int) -> bool:
        """Delete a bookmark"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM video_bookmarks WHERE id = ?", (bookmark_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting bookmark: {e}")
            return False
        finally:
            conn.close()

    def get_bookmarks_by_image_id(self, image_id: int) -> List[Dict]:
        """Get bookmarks for a video by its image_id"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT vb.* FROM video_bookmarks vb
            JOIN youtube_videos yv ON vb.youtube_video_id = yv.id
            WHERE yv.image_id = ?
            ORDER BY vb.timestamp_ms
        """, (image_id,))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    # ============ VIDEO NOTES ============

    def add_video_note(self, youtube_video_id: int, timestamp_ms: int, content: str) -> Optional[int]:
        """Add a timestamped note to a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO video_notes (youtube_video_id, timestamp_ms, content)
                VALUES (?, ?, ?)
            """, (youtube_video_id, timestamp_ms, content))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding video note: {e}")
            return None
        finally:
            conn.close()

    def get_video_notes(self, youtube_video_id: int) -> List[Dict]:
        """Get all notes for a video"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM video_notes
            WHERE youtube_video_id = ?
            ORDER BY timestamp_ms
        """, (youtube_video_id,))

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def update_video_note(self, note_id: int, content: str = None, timestamp_ms: int = None) -> bool:
        """Update a video note"""
        conn = self.get_connection()
        cursor = conn.cursor()

        updates = []
        values = []

        if content is not None:
            updates.append("content = ?")
            values.append(content)
        if timestamp_ms is not None:
            updates.append("timestamp_ms = ?")
            values.append(timestamp_ms)

        if not updates:
            conn.close()
            return False

        updates.append("updated_at = CURRENT_TIMESTAMP")
        values.append(note_id)

        try:
            cursor.execute(f"""
                UPDATE video_notes SET {', '.join(updates)}
                WHERE id = ?
            """, values)
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating video note: {e}")
            return False
        finally:
            conn.close()

    def delete_video_note(self, note_id: int) -> bool:
        """Delete a video note"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM video_notes WHERE id = ?", (note_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting video note: {e}")
            return False
        finally:
            conn.close()

    # ============ VOCABULARY ============

    def add_vocabulary(self, word: str, translation: str,
                       source_language: str = 'en', target_language: str = 'bg',
                       context_sentence: str = None, video_id: int = None,
                       timestamp_ms: int = None, notes: str = None) -> Optional[int]:
        """Add a word to vocabulary"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO vocabulary (word, translation, source_language, target_language,
                                       context_sentence, video_id, timestamp_ms, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(word, source_language, target_language)
                DO UPDATE SET
                    translation = excluded.translation,
                    context_sentence = COALESCE(excluded.context_sentence, context_sentence),
                    video_id = COALESCE(excluded.video_id, video_id),
                    timestamp_ms = COALESCE(excluded.timestamp_ms, timestamp_ms)
            """, (word.lower().strip(), translation, source_language, target_language,
                  context_sentence, video_id, timestamp_ms, notes))
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding vocabulary: {e}")
            return None
        finally:
            conn.close()

    def get_vocabulary(self, source_language: str = None, target_language: str = None,
                       search: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get vocabulary words with optional filtering"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM vocabulary WHERE 1=1"
        params = []

        if source_language:
            query += " AND source_language = ?"
            params.append(source_language)
        if target_language:
            query += " AND target_language = ?"
            params.append(target_language)
        if search:
            query += " AND (word LIKE ? OR translation LIKE ?)"
            params.extend([f'%{search}%', f'%{search}%'])

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def get_vocabulary_word(self, word: str, source_language: str = 'en',
                            target_language: str = 'bg') -> Optional[Dict]:
        """Check if a word exists in vocabulary"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM vocabulary
            WHERE word = ? AND source_language = ? AND target_language = ?
        """, (word.lower().strip(), source_language, target_language))

        result = cursor.fetchone()
        conn.close()

        return dict(result) if result else None

    def delete_vocabulary(self, vocab_id: int) -> bool:
        """Delete a vocabulary entry"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM vocabulary WHERE id = ?", (vocab_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error deleting vocabulary: {e}")
            return False
        finally:
            conn.close()

    def get_vocabulary_count(self) -> int:
        """Get total vocabulary count"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM vocabulary")
        result = cursor.fetchone()
        conn.close()
        return result['count'] if result else 0
