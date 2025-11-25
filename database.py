"""
Database layer for AI Gallery
Handles all SQLite operations for images, boards, and relationships
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class Database:
    def __init__(self, db_path: str = "data/gallery.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get database connection with row factory and timeout"""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
    
    
    
    
        """Initialize database schema"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Images table
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
                analyzed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Boards table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS boards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                parent_id INTEGER,
                cover_image_id INTEGER,
                smart_rules TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_id) REFERENCES boards(id) ON DELETE CASCADE,
                FOREIGN KEY (cover_image_id) REFERENCES images(id) ON DELETE SET NULL
            )
        """)
        
        # Add smart_rules column if it doesn't exist (migration)
        cursor.execute("PRAGMA table_info(boards)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'smart_rules' not in columns:
            cursor.execute("ALTER TABLE boards ADD COLUMN smart_rules TEXT DEFAULT NULL")
            conn.commit()
        
        # Board-Image relationships (many-to-many)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS board_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (board_id) REFERENCES boards(id) ON DELETE CASCADE,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                UNIQUE(board_id, image_id)
            )
        """)
        
        # Add media_type column if it doesn't exist (migration)
        cursor.execute("PRAGMA table_info(images)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'media_type' not in columns:
            cursor.execute("ALTER TABLE images ADD COLUMN media_type TEXT DEFAULT 'image'")
            conn.commit()

        # Create indexes for performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_filepath ON images(filepath)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_favorite ON images(is_favorite)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_analyzed ON images(analyzed_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_created ON images(created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_media_type ON images(media_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_boards_parent ON boards(parent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_board_images_board ON board_images(board_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_board_images_image ON board_images(image_id)")

        # ============ AI FEATURES TABLES ============

        # EXIF metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exif_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                camera_make TEXT,
                camera_model TEXT,
                lens_model TEXT,
                iso INTEGER,
                aperture REAL,
                shutter_speed REAL,
                focal_length REAL,
                flash INTEGER,
                white_balance INTEGER,
                metering_mode INTEGER,
                exposure_mode INTEGER,
                exposure_compensation REAL,
                orientation INTEGER,
                date_taken TEXT,
                gps_latitude REAL,
                gps_longitude REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        """)

        # CLIP embeddings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                embedding BLOB NOT NULL,
                model_version TEXT DEFAULT 'clip-vit-base-patch32',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        """)

        # Color palette table (for future color search features)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS image_colors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                dominant_colors TEXT,
                color_palette TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        """)

        # ============ FACE RECOGNITION TABLES ============

        # Person groups (people identified in photos)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS person_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                cover_face_id INTEGER,
                face_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Detected faces in images
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS faces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER NOT NULL,
                person_group_id INTEGER,
                bounding_box TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                age INTEGER,
                gender TEXT,
                emotion TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
                FOREIGN KEY (person_group_id) REFERENCES person_groups(id) ON DELETE SET NULL
            )
        """)

        # Face embeddings (DeepFace vectors for similarity matching)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS face_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                face_id INTEGER UNIQUE NOT NULL,
                embedding BLOB NOT NULL,
                model_name TEXT DEFAULT 'Facenet',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (face_id) REFERENCES faces(id) ON DELETE CASCADE
            )
        """)

        # Audit log table (for tracking changes)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                changes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for AI features
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exif_image ON exif_data(image_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exif_camera ON exif_data(camera_make, camera_model)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exif_iso ON exif_data(iso)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exif_date ON exif_data(date_taken)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_exif_gps ON exif_data(gps_latitude, gps_longitude)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_embeddings_image ON image_embeddings(image_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_colors_image ON image_colors(image_id)")

        # Create indexes for face recognition
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_image ON faces(image_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_person ON faces(person_group_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_face_embeddings_face ON face_embeddings(face_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_person_groups_name ON person_groups(name)")

        # ============ YOUTUBE VIDEO TABLES ============

        # YouTube video metadata (extends images table for YouTube-specific data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS youtube_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id INTEGER UNIQUE NOT NULL,
                youtube_id TEXT UNIQUE NOT NULL,
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

        # Video keyframes (extracted frames for CLIP embeddings)
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
                FOREIGN KEY (embedding_id) REFERENCES image_embeddings(id) ON DELETE SET NULL,
                UNIQUE(youtube_video_id, frame_number)
            )
        """)

        # Video subtitles (parsed VTT data for search)
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

        # Create indexes for YouTube tables
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_videos_image ON youtube_videos(image_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_videos_youtube_id ON youtube_videos(youtube_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_youtube_videos_channel ON youtube_videos(channel_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyframes_video ON video_keyframes(youtube_video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_keyframes_timestamp ON video_keyframes(timestamp_ms)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtitles_video ON video_subtitles(youtube_video_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_subtitles_time ON video_subtitles(start_time_ms, end_time_ms)")

        # Full-text search index - check if needs migration
        cursor.execute("""
            SELECT sql FROM sqlite_master 
            WHERE type = 'table' AND name = 'images_fts'
        """)
        fts_table = cursor.fetchone()
        recreate_fts = False
        
        if not fts_table:
            # Create new FTS table
            self._create_fulltext_table(cursor)
            recreate_fts = True
        elif fts_table['sql'] and 'content=' in fts_table['sql'].lower():
            # Old schema with content=images, needs migration
            cursor.execute("DROP TABLE IF EXISTS images_fts")
            self._create_fulltext_table(cursor)
            recreate_fts = True
        
        conn.commit()
        conn.close()
        
        # Rebuild FTS index if needed
        if recreate_fts:
            self.rebuild_fulltext_index()
    
    # ============ IMAGE OPERATIONS ============
    
    def add_image(self, filepath: str, filename: str = None, width: int = None,
                  height: int = None, file_size: int = None, media_type: str = 'image') -> int:
        """Add new image/video to database"""
        # Extract filename from filepath if not provided
        if filename is None:
            from pathlib import Path
            filename = Path(filepath).name

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO images (filepath, filename, width, height, file_size, media_type)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (filepath, filename, width, height, file_size, media_type))

            image_id = cursor.lastrowid

            # Update FTS index
            cursor.execute("""
                INSERT INTO images_fts (rowid, filename, description, tags)
                VALUES (?, ?, '', '')
            """, (image_id, filename))

            conn.commit()
            return image_id
        except sqlite3.IntegrityError:
            # Image already exists
            cursor.execute("SELECT id FROM images WHERE filepath = ?", (filepath,))
            result = cursor.fetchone()
            return result['id'] if result else None
        finally:
            conn.close()
    
    def get_image(self, image_id: int) -> Optional[Dict]:
        """Get single image by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM images WHERE id = ?", (image_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return self._row_to_dict(result)
        return None
    
    def get_all_images(self, limit: int = 1000, offset: int = 0, 
                       favorites_only: bool = False,
                       media_type: Optional[str] = None,
                       analyzed: Optional[bool] = None) -> List[Dict]:
        """Get all images with pagination and optional filters"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM images"
        clauses = []
        params = []
        
        if favorites_only:
            clauses.append("is_favorite = 1")
        
        if media_type:
            clauses.append("media_type = ?")
            params.append(media_type)
        
        if analyzed is True:
            clauses.append("analyzed_at IS NOT NULL")
        elif analyzed is False:
            clauses.append("analyzed_at IS NULL")
        
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    def update_image_analysis(self, image_id: int, description: str, tags: List[str]):
        """Update image with AI analysis results"""
        tags_json = json.dumps(tags)
        tags_text = ' '.join(tags)
        
        try:
            self._apply_image_analysis_update(image_id, description, tags_json, tags_text)
        except sqlite3.DatabaseError as error:
            if "malformed" in str(error).lower():
                print("Detected corrupted full-text index, attempting rebuild...")
                self.rebuild_fulltext_index()
                # Retry the update
                self._apply_image_analysis_update(image_id, description, tags_json, tags_text)
            else:
                raise
    
    def _apply_image_analysis_update(self, image_id: int, description: str,
                                     tags_json: str, tags_text: str):
        """Internal helper to perform image analysis update with FTS sync"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE images 
                SET description = ?, tags = ?, analyzed_at = ?, updated_at = ?
                WHERE id = ?
            """, (description, tags_json, datetime.now(), datetime.now(), image_id))
            
            # Update FTS index
            cursor.execute("""
                UPDATE images_fts 
                SET description = ?, tags = ?
                WHERE rowid = ?
            """, (description, tags_text, image_id))
            
            conn.commit()
        finally:
            conn.close()
    
    def toggle_favorite(self, image_id: int) -> bool:
        """Toggle favorite status, return new status"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT is_favorite FROM images WHERE id = ?", (image_id,))
        result = cursor.fetchone()
        
        if result:
            new_status = not result['is_favorite']
            cursor.execute("""
                UPDATE images SET is_favorite = ?, updated_at = ? WHERE id = ?
            """, (new_status, datetime.now(), image_id))
            conn.commit()
            conn.close()
            return new_status
        
        conn.close()
        return False
    
    def rename_image(self, image_id: int, new_filepath: str, new_filename: str):
        """Update image filepath after rename"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE images 
            SET filepath = ?, filename = ?, updated_at = ?
            WHERE id = ?
        """, (new_filepath, new_filename, datetime.now(), image_id))
        
        # Update FTS index
        cursor.execute("""
            UPDATE images_fts SET filename = ? WHERE rowid = ?
        """, (new_filename, image_id))
        
        conn.commit()
        conn.close()
    
    def search_images(self, query: str, limit: int = 100) -> List[Dict]:
        """Full-text search across filename, description, tags"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Use FTS5 for full-text search
        cursor.execute("""
            SELECT i.* FROM images i
            JOIN images_fts fts ON i.id = fts.rowid
            WHERE images_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        """, (query, limit))
        
        results = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in results]

    def get_similar_images(self, image_id: int, limit: int = 6) -> List[Dict]:
        """Get similar images based on shared tags"""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get the source image's tags
        cursor.execute("SELECT tags FROM images WHERE id = ?", (image_id,))
        result = cursor.fetchone()

        if not result or not result['tags']:
            conn.close()
            return []

        try:
            source_tags = json.loads(result['tags'])
        except:
            conn.close()
            return []

        if not source_tags:
            conn.close()
            return []

        # Find images with matching tags (simplified approach without json_each)
        # Get all analyzed images with tags
        cursor.execute("""
            SELECT * FROM images
            WHERE id != ?
              AND analyzed_at IS NOT NULL
              AND tags IS NOT NULL
              AND tags != '[]'
            ORDER BY analyzed_at DESC
            LIMIT 50
        """, (image_id,))

        results = cursor.fetchall()
        conn.close()

        # Calculate similarity based on shared tags
        similar_images = []
        for row in results:
            try:
                img_tags = json.loads(row['tags'])
                shared_tags = set(source_tags) & set(img_tags)
                if len(shared_tags) > 0:
                    img_dict = self._row_to_dict(row)
                    img_dict['similarity_score'] = len(shared_tags)
                    similar_images.append(img_dict)
            except:
                continue

        # Sort by similarity and return top N
        similar_images.sort(key=lambda x: x['similarity_score'], reverse=True)
        return similar_images[:limit]

    def get_unanalyzed_images(self, limit: int = 100) -> List[Dict]:
        """Get images that haven't been analyzed yet"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM images 
            WHERE analyzed_at IS NULL 
            ORDER BY created_at ASC
            LIMIT ?
        """, (limit,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    def delete_image(self, image_id: int):
        """Delete image from database (also removes from all boards)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
        cursor.execute("DELETE FROM images_fts WHERE rowid = ?", (image_id,))

        conn.commit()
        conn.close()

    # ============ TAG OPERATIONS ============

    def get_all_tags(self) -> List[Dict]:
        """
        Get all unique tags with usage count, sorted by popularity
        Returns: [{'tag': 'sunset', 'count': 5}, ...]
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT tags FROM images
            WHERE tags IS NOT NULL AND tags != '[]'
        """)

        results = cursor.fetchall()
        conn.close()

        # Count tag occurrences
        tag_counts = {}
        for row in results:
            try:
                tags = json.loads(row['tags'])
                for tag in tags:
                    tag = tag.lower().strip()
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
            except:
                continue

        # Convert to list of dicts and sort by count
        tag_list = [{'tag': tag, 'count': count} for tag, count in tag_counts.items()]
        tag_list.sort(key=lambda x: x['count'], reverse=True)

        return tag_list

    def get_tag_suggestions(self, prefix: str = '', limit: int = 10) -> List[str]:
        """
        Get tag suggestions for autocomplete

        Args:
            prefix: String prefix to filter tags (case-insensitive)
            limit: Maximum number of suggestions to return

        Returns: List of tag strings sorted by popularity
        """
        all_tags = self.get_all_tags()

        if prefix:
            prefix_lower = prefix.lower()
            filtered = [t for t in all_tags if t['tag'].startswith(prefix_lower)]
        else:
            filtered = all_tags

        return [t['tag'] for t in filtered[:limit]]

    def get_related_tags(self, tag: str, limit: int = 10) -> List[Dict]:
        """
        Get tags that frequently appear together with the given tag

        Args:
            tag: The tag to find related tags for
            limit: Maximum number of related tags to return

        Returns: [{'tag': 'related_tag', 'co_occurrence': 3}, ...]
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        tag_lower = tag.lower().strip()

        # Find all images with this tag
        cursor.execute("""
            SELECT tags FROM images
            WHERE tags IS NOT NULL AND tags != '[]'
        """)

        results = cursor.fetchall()
        conn.close()

        # Count co-occurrences
        co_occurrences = {}
        for row in results:
            try:
                tags = json.loads(row['tags'])
                tags_lower = [t.lower().strip() for t in tags]

                # If this image has the target tag
                if tag_lower in tags_lower:
                    # Count all other tags
                    for other_tag in tags_lower:
                        if other_tag != tag_lower:
                            co_occurrences[other_tag] = co_occurrences.get(other_tag, 0) + 1
            except:
                continue

        # Convert to list and sort
        related = [{'tag': t, 'co_occurrence': count} for t, count in co_occurrences.items()]
        related.sort(key=lambda x: x['co_occurrence'], reverse=True)

        return related[:limit]

    # ============ BOARD OPERATIONS ============
    
    def create_board(self, name: str, description: str = None, 
                     parent_id: int = None) -> int:
        """Create new board"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO boards (name, description, parent_id)
            VALUES (?, ?, ?)
        """, (name, description, parent_id))
        
        board_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return board_id
    
    def get_board(self, board_id: int) -> Optional[Dict]:
        """Get single board by ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM boards WHERE id = ?", (board_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return self._row_to_dict(result)
        return None
    
    def get_all_boards(self) -> List[Dict]:
        """Get all boards"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM boards ORDER BY name")
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    def get_sub_boards(self, parent_id: int = None) -> List[Dict]:
        """Get boards with specific parent (or top-level if parent_id is None)"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if parent_id is None:
            cursor.execute("SELECT * FROM boards WHERE parent_id IS NULL ORDER BY name")
        else:
            cursor.execute("SELECT * FROM boards WHERE parent_id = ? ORDER BY name", (parent_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    def update_board(self, board_id: int, name: str = None, description: str = None):
        """Update board details"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if updates:
            updates.append("updated_at = ?")
            params.append(datetime.now())
            params.append(board_id)
            
            query = f"UPDATE boards SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            conn.commit()
        
        conn.close()

    def move_board(self, board_id: int, new_parent_id: int = None):
        """
        Move board to a new parent (or to top level if new_parent_id is None)
        Prevents circular dependencies
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Check if new_parent_id is the same as current board
        if new_parent_id == board_id:
            conn.close()
            raise ValueError("Board cannot be its own parent")

        # Check if new_parent_id would create a circular dependency
        # (i.e., new parent is a descendant of the board being moved)
        if new_parent_id is not None:
            all_sub_boards = self._get_all_sub_boards(board_id, cursor)
            sub_board_ids = [b['id'] for b in all_sub_boards]

            if new_parent_id in sub_board_ids:
                conn.close()
                raise ValueError("Cannot move board under its own sub-board (circular dependency)")

        # Update the parent_id
        cursor.execute("""
            UPDATE boards
            SET parent_id = ?, updated_at = ?
            WHERE id = ?
        """, (new_parent_id, datetime.now(), board_id))

        conn.commit()
        conn.close()

    def delete_board(self, board_id: int, delete_sub_boards: bool = False):
        """
        Delete board and optionally its sub-boards

        Args:
            board_id: Board to delete
            delete_sub_boards: If True, also delete all sub-boards recursively
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        if delete_sub_boards:
            # Get all sub-boards recursively
            sub_boards = self._get_all_sub_boards(board_id, cursor)

            # Delete sub-boards first (bottom-up)
            for sub_board_id in reversed(sub_boards):
                cursor.execute("DELETE FROM boards WHERE id = ?", (sub_board_id,))
                print(f"Deleted sub-board {sub_board_id}")

        # Delete the board itself
        cursor.execute("DELETE FROM boards WHERE id = ?", (board_id,))
        print(f"Deleted board {board_id}")

        conn.commit()
        conn.close()

    def _get_all_sub_boards(self, board_id: int, cursor) -> List[int]:
        """Recursively get all sub-board IDs"""
        sub_board_ids = []

        cursor.execute("SELECT id FROM boards WHERE parent_id = ?", (board_id,))
        direct_subs = cursor.fetchall()

        for sub in direct_subs:
            sub_id = sub['id']
            sub_board_ids.append(sub_id)
            # Recursively get sub-boards of this sub-board
            sub_board_ids.extend(self._get_all_sub_boards(sub_id, cursor))

        return sub_board_ids

    def merge_boards(self, source_board_id: int, target_board_id: int, delete_source: bool = True):
        """
        Merge source board into target board

        Args:
            source_board_id: Board to merge from
            target_board_id: Board to merge into
            delete_source: If True, delete source board after merge

        Returns:
            Number of images moved
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        # Get all images from source board
        cursor.execute("""
            SELECT image_id FROM board_images
            WHERE board_id = ?
        """, (source_board_id,))

        images = cursor.fetchall()
        moved_count = 0

        # Move images to target board
        for row in images:
            image_id = row['image_id']
            try:
                cursor.execute("""
                    INSERT INTO board_images (board_id, image_id)
                    VALUES (?, ?)
                """, (target_board_id, image_id))
                moved_count += 1
            except sqlite3.IntegrityError:
                # Already in target board, skip
                pass

        # Move sub-boards to target board
        cursor.execute("""
            UPDATE boards
            SET parent_id = ?
            WHERE parent_id = ?
        """, (target_board_id, source_board_id))

        sub_boards_moved = cursor.rowcount

        conn.commit()

        # Delete source board if requested
        if delete_source:
            cursor.execute("DELETE FROM boards WHERE id = ?", (source_board_id,))
            conn.commit()
            print(f"Merged board {source_board_id} into {target_board_id}: {moved_count} images, {sub_boards_moved} sub-boards moved")
        else:
            print(f"Copied {moved_count} images from board {source_board_id} to {target_board_id}")

        conn.close()
        return moved_count
    
    # ============ BOARD-IMAGE RELATIONSHIPS ============
    
    def get_parent_boards(self, board_id: int) -> List[int]:
        """Get all parent boards recursively (from direct parent up to root)"""
        parent_ids = []
        current_id = board_id

        conn = self.get_connection()
        cursor = conn.cursor()

        print(f"get_parent_boards: Looking for parents of board {board_id}")

        # Walk up the tree to find all parents
        max_depth = 10  # Prevent infinite loops
        depth = 0
        while depth < max_depth:
            cursor.execute("SELECT id, name, parent_id FROM boards WHERE id = ?", (current_id,))
            result = cursor.fetchone()

            if not result:
                print(f"  Board {current_id} not found in database!")
                break

            print(f"  Depth {depth}: Board {result['id']} ('{result['name']}') has parent_id={result['parent_id']}")

            if result['parent_id'] is None:
                print(f"  Reached root board (no parent)")
                break

            parent_id = result['parent_id']
            parent_ids.append(parent_id)
            current_id = parent_id
            depth += 1

        conn.close()
        print(f"get_parent_boards: Found {len(parent_ids)} parents: {parent_ids}")
        return parent_ids

    def add_image_to_board(self, board_id: int, image_id: int, auto_add_to_parents: bool = True):
        """
        Add image to board and optionally to all parent boards

        Args:
            board_id: The board to add the image to
            image_id: The image to add
            auto_add_to_parents: If True, also adds image to all parent boards
        """
        print(f"add_image_to_board: board_id={board_id}, image_id={image_id}, auto_add_to_parents={auto_add_to_parents}")

        conn = self.get_connection()
        cursor = conn.cursor()

        # Add to the specified board
        try:
            cursor.execute("""
                INSERT INTO board_images (board_id, image_id)
                VALUES (?, ?)
            """, (board_id, image_id))
            conn.commit()
            print(f"✓ Added image {image_id} to board {board_id}")
        except sqlite3.IntegrityError:
            # Already exists, ignore
            print(f"Image {image_id} already in board {board_id}")
            pass
        finally:
            conn.close()

        # Auto-add to parent boards if enabled
        if auto_add_to_parents:
            parent_ids = self.get_parent_boards(board_id)
            print(f"Found {len(parent_ids)} parent boards: {parent_ids}")

            if len(parent_ids) == 0:
                print(f"Board {board_id} has no parent boards")

            for parent_id in parent_ids:
                conn = self.get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO board_images (board_id, image_id)
                        VALUES (?, ?)
                    """, (parent_id, image_id))
                    conn.commit()
                    print(f"✓ Auto-added image {image_id} to parent board {parent_id}")
                except sqlite3.IntegrityError:
                    # Already exists, ignore
                    print(f"Image {image_id} already in parent board {parent_id}")
                    pass
                finally:
                    conn.close()
        else:
            print(f"Auto-add to parents is disabled")
    
    def remove_image_from_board(self, board_id: int, image_id: int):
        """Remove image from board"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM board_images 
            WHERE board_id = ? AND image_id = ?
        """, (board_id, image_id))
        
        conn.commit()
        conn.close()
    
    def get_board_images(self, board_id: int) -> List[Dict]:
        """Get all images in a board"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT i.* FROM images i
            JOIN board_images bi ON i.id = bi.image_id
            WHERE bi.board_id = ?
            ORDER BY bi.added_at DESC
        """, (board_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    def get_image_boards(self, image_id: int) -> List[Dict]:
        """Get all boards containing an image"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT b.* FROM boards b
            JOIN board_images bi ON b.id = bi.board_id
            WHERE bi.image_id = ?
            ORDER BY b.name
        """, (image_id,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [self._row_to_dict(row) for row in results]
    
    # ============ STATISTICS ============
    
    def get_stats(self) -> Dict:
        """Get database statistics"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Total images
        cursor.execute("SELECT COUNT(*) as count FROM images")
        total_images = cursor.fetchone()['count']
        
        # Analyzed images
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE analyzed_at IS NOT NULL")
        analyzed_images = cursor.fetchone()['count']
        
        # Favorite images
        cursor.execute("SELECT COUNT(*) as count FROM images WHERE is_favorite = 1")
        favorite_images = cursor.fetchone()['count']
        
        # Total boards
        cursor.execute("SELECT COUNT(*) as count FROM boards")
        total_boards = cursor.fetchone()['count']
        
        conn.close()
        
        return {
            'total_images': total_images,
            'analyzed_images': analyzed_images,
            'unanalyzed_images': total_images - analyzed_images,
            'favorite_images': favorite_images,
            'total_boards': total_boards
        }
    
    # ============ HELPER METHODS ============
    
    def rebuild_fulltext_index(self):
        """Rebuild the FTS index from the images table"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Drop and recreate FTS table with retries
            for attempt in range(3):
                try:
                    cursor.execute("DROP TABLE IF EXISTS images_fts")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" in str(exc).lower() and attempt < 2:
                        import time
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    raise
            
            self._create_fulltext_table(cursor)
            
            # Rebuild from images table
            cursor.execute("SELECT id, filename, description, tags FROM images")
            rows = cursor.fetchall()
            
            for row in rows:
                tags_list = []
                
                if row['tags']:
                    try:
                        tags_list = json.loads(row['tags'])
                    except json.JSONDecodeError:
                        # Corrupted tag data, skip gracefully
                        tags_list = []
                
                cursor.execute("""
                    INSERT INTO images_fts (rowid, filename, description, tags)
                    VALUES (?, ?, ?, ?)
                """, (
                    row['id'],
                    row['filename'] or '',
                    row['description'] or '',
                    ' '.join(tags_list)
                ))
            
            conn.commit()
        finally:
            conn.close()
    
    def _create_fulltext_table(self, cursor):
        """Create the FTS5 table with the expected schema (no content= clause)"""
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS images_fts USING fts5(
                filename, description, tags
            )
        """)
    
    def _row_to_dict(self, row) -> Dict:
        """Convert SQLite Row to dictionary"""
        if row is None:
            return None

        data = dict(row)

        # Parse JSON fields
        if 'tags' in data and data['tags']:
            try:
                data['tags'] = json.loads(data['tags'])
            except:
                data['tags'] = []
        else:
            data['tags'] = []

        # Parse smart_rules JSON
        if 'smart_rules' in data and data['smart_rules']:
            try:
                data['smart_rules'] = json.loads(data['smart_rules'])
            except:
                data['smart_rules'] = None
        else:
            data['smart_rules'] = None

        # Convert boolean
        if 'is_favorite' in data:
            data['is_favorite'] = bool(data['is_favorite'])

        return data

    # ============ EXIF OPERATIONS ============

    def save_exif_data(self, image_id: int, exif_data: Dict) -> bool:
        """Save EXIF metadata for an image"""
        if not exif_data:
            return False

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO exif_data (
                    image_id, camera_make, camera_model, lens_model,
                    iso, aperture, shutter_speed, focal_length,
                    flash, white_balance, metering_mode, exposure_mode,
                    exposure_compensation, orientation, date_taken,
                    gps_latitude, gps_longitude
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_id,
                exif_data.get('camera_make'),
                exif_data.get('camera_model'),
                exif_data.get('lens_model'),
                exif_data.get('iso'),
                exif_data.get('aperture'),
                exif_data.get('shutter_speed'),
                exif_data.get('focal_length'),
                exif_data.get('flash'),
                exif_data.get('white_balance'),
                exif_data.get('metering_mode'),
                exif_data.get('exposure_mode'),
                exif_data.get('exposure_compensation'),
                exif_data.get('orientation'),
                exif_data.get('date_taken'),
                exif_data.get('gps_latitude'),
                exif_data.get('gps_longitude')
            ))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving EXIF data: {e}")
            return False
        finally:
            conn.close()

    def get_exif_data(self, image_id: int) -> Optional[Dict]:
        """Get EXIF metadata for an image"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM exif_data WHERE image_id = ?", (image_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return dict(result)
        return None

    def search_by_exif(self, camera_make: str = None, camera_model: str = None,
                       min_iso: int = None, max_iso: int = None,
                       min_aperture: float = None, max_aperture: float = None,
                       min_focal_length: float = None, max_focal_length: float = None,
                       has_gps: bool = None, limit: int = 100) -> List[Dict]:
        """Search images by EXIF criteria"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = """
            SELECT i.* FROM images i
            JOIN exif_data e ON i.id = e.image_id
            WHERE 1=1
        """
        params = []

        if camera_make:
            query += " AND e.camera_make LIKE ?"
            params.append(f"%{camera_make}%")

        if camera_model:
            query += " AND e.camera_model LIKE ?"
            params.append(f"%{camera_model}%")

        if min_iso is not None:
            query += " AND e.iso >= ?"
            params.append(min_iso)

        if max_iso is not None:
            query += " AND e.iso <= ?"
            params.append(max_iso)

        if min_aperture is not None:
            query += " AND e.aperture >= ?"
            params.append(min_aperture)

        if max_aperture is not None:
            query += " AND e.aperture <= ?"
            params.append(max_aperture)

        if min_focal_length is not None:
            query += " AND e.focal_length >= ?"
            params.append(min_focal_length)

        if max_focal_length is not None:
            query += " AND e.focal_length <= ?"
            params.append(max_focal_length)

        if has_gps is not None:
            if has_gps:
                query += " AND e.gps_latitude IS NOT NULL AND e.gps_longitude IS NOT NULL"
            else:
                query += " AND (e.gps_latitude IS NULL OR e.gps_longitude IS NULL)"

        query += " ORDER BY i.created_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        results = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in results]

    def get_all_cameras(self) -> List[Dict]:
        """Get list of all cameras with image counts"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                camera_make,
                camera_model,
                COUNT(*) as count
            FROM exif_data
            WHERE camera_make != '' OR camera_model != ''
            GROUP BY camera_make, camera_model
            ORDER BY count DESC
        """)

        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    # ============ EMBEDDINGS OPERATIONS ============

    def save_embedding(self, image_id: int, embedding: bytes, model_version: str = 'clip-vit-base-patch32') -> bool:
        """Save CLIP embedding for an image"""
        if not embedding:
            return False

        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO image_embeddings (image_id, embedding, model_version)
                VALUES (?, ?, ?)
            """, (image_id, embedding, model_version))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error saving embedding: {e}")
            return False
        finally:
            conn.close()

    def get_embedding(self, image_id: int) -> Optional[bytes]:
        """Get CLIP embedding for an image"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT embedding FROM image_embeddings WHERE image_id = ?", (image_id,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return result['embedding']
        return None

    def get_all_embeddings(self, limit: int = None) -> List[Dict]:
        """Get all image embeddings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        query = "SELECT image_id as id, embedding FROM image_embeddings"
        if limit:
            query += f" LIMIT {limit}"

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        return [dict(row) for row in results]

    def count_embeddings(self) -> int:
        """Count images with embeddings"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM image_embeddings")
        result = cursor.fetchone()
        conn.close()

        return result['count'] if result else 0

    def get_images_without_embeddings(self, limit: int = 100) -> List[Dict]:
        """Get images that don't have embeddings yet"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT i.* FROM images i
            LEFT JOIN image_embeddings e ON i.id = e.image_id
            WHERE e.id IS NULL AND i.media_type = 'image'
            ORDER BY i.created_at DESC
            LIMIT ?
        """, (limit,))

        results = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in results]

    # ============ SMART BOARDS OPERATIONS ============

    def update_board_smart_rules(self, board_id: int, smart_rules: Dict) -> bool:
        """
        Update smart rules for a board
        
        Args:
            board_id: Board ID
            smart_rules: Dictionary with rules (will be stored as JSON)
                Example: {
                    'tags_include': ['sunset', 'sky'],
                    'tags_exclude': ['portrait'],
                    'description_contains': 'nature',
                    'min_confidence': 0.8
                }
        
        Returns:
            bool: True if successful
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            rules_json = json.dumps(smart_rules) if smart_rules else None
            cursor.execute("""
                UPDATE boards 
                SET smart_rules = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (rules_json, board_id))
            
            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating smart rules: {e}")
            return False
        finally:
            conn.close()

    def process_smart_boards(self, image_id: int) -> List[int]:
        """
        Run smart board rules against a specific image and auto-add to matching boards
        
        Args:
            image_id: Image ID to process
        
        Returns:
            List[int]: List of board IDs that the image was added to
        """
        # Get image data
        image = self.get_image(image_id)
        if not image:
            return []
        
        # Parse tags
        image_tags = []
        if image.get('tags'):
            try:
                if isinstance(image['tags'], str):
                    image_tags = json.loads(image['tags'])
                elif isinstance(image['tags'], list):
                    image_tags = image['tags']
            except:
                image_tags = []
        
        image_tags_set = set(t.lower().strip() for t in image_tags if t)
        image_description = (image.get('description') or '').lower()
        
        # Get all smart boards
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, smart_rules FROM boards WHERE smart_rules IS NOT NULL AND smart_rules != ''")
        smart_boards = cursor.fetchall()
        conn.close()
        
        added_to_boards = []
        
        for board in smart_boards:
            try:
                rules_json = board['smart_rules']
                if not rules_json:
                    continue
                    
                rules = json.loads(rules_json)
                match = False
                
                # RULE 1: Tags Include (at least one tag must match)
                if 'tags_include' in rules and rules['tags_include']:
                    required_tags = set(t.lower().strip() for t in rules['tags_include'] if t)
                    if required_tags and not required_tags.isdisjoint(image_tags_set):
                        match = True
                        print(f"[SMART BOARD] Image {image_id} matches board '{board['name']}' (tags_include: {required_tags})")
                
                # RULE 2: Tags Exclude (none of these tags should be present)
                if 'tags_exclude' in rules and rules['tags_exclude']:
                    excluded_tags = set(t.lower().strip() for t in rules['tags_exclude'] if t)
                    if excluded_tags and not excluded_tags.isdisjoint(image_tags_set):
                        match = False  # Exclude overrides include
                        print(f"[SMART BOARD] Image {image_id} excluded from board '{board['name']}' (tags_exclude: {excluded_tags})")
                        continue
                
                # RULE 3: Description Contains (text search in description)
                if 'description_contains' in rules and rules['description_contains']:
                    search_text = rules['description_contains'].lower()
                    if search_text in image_description:
                        match = True
                        print(f"[SMART BOARD] Image {image_id} matches board '{board['name']}' (description contains: '{search_text}')")
                
                # RULE 4: All Tags Required (all tags must be present)
                if 'tags_all' in rules and rules['tags_all']:
                    required_all = set(t.lower().strip() for t in rules['tags_all'] if t)
                    if required_all and required_all.issubset(image_tags_set):
                        match = True
                        print(f"[SMART BOARD] Image {image_id} matches board '{board['name']}' (tags_all: {required_all})")
                    elif required_all:
                        match = False  # If all tags required but not present, don't match
                
                # If match found, add to board
                if match:
                    self.add_image_to_board(board['id'], image_id, auto_add_to_parents=True)
                    added_to_boards.append(board['id'])
                    
            except Exception as e:
                print(f"[SMART BOARD] Error processing rules for board {board['id']} ({board.get('name', 'unknown')}): {e}")
                import traceback
                traceback.print_exc()
                continue
        
        if added_to_boards:
            print(f"[SMART BOARD] ✅ Auto-added image {image_id} to {len(added_to_boards)} smart board(s): {added_to_boards}")
        
        return added_to_boards

    def process_all_images_for_smart_board(self, board_id: int) -> int:
        """
        Process all existing images against a specific smart board (retroactive)
        Useful when creating a new smart board or updating rules
        
        Args:
            board_id: Board ID to process
        
        Returns:
            int: Number of images added
        """
        # Get all analyzed images
        all_images = self.get_all_images(limit=10000)
        added_count = 0
        
        for image in all_images:
            if image.get('tags') or image.get('description'):
                added_boards = self.process_smart_boards(image['id'])
                if board_id in added_boards:
                    added_count += 1

        return added_count

    # ============ FACE RECOGNITION OPERATIONS ============

    def add_face(self, image_id: int, bounding_box: Dict, confidence: float = 1.0,
                 age: int = None, gender: str = None, emotion: str = None) -> int:
        """
        Add a detected face to the database

        Args:
            image_id: Image ID where face was detected
            bounding_box: Dict with x, y, w, h coordinates
            confidence: Detection confidence (0-1)
            age: Detected age (optional)
            gender: Detected gender (optional)
            emotion: Detected emotion (optional)

        Returns:
            int: Face ID
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO faces (image_id, bounding_box, confidence, age, gender, emotion)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (image_id, json.dumps(bounding_box), confidence, age, gender, emotion))

            conn.commit()
            face_id = cursor.lastrowid
            return face_id
        except Exception as e:
            print(f"Error adding face: {e}")
            return None
        finally:
            conn.close()

    def add_face_embedding(self, face_id: int, embedding: bytes, model_name: str = 'Facenet') -> bool:
        """
        Store face embedding (DeepFace vector)

        Args:
            face_id: Face ID
            embedding: Serialized embedding vector (numpy array as bytes)
            model_name: DeepFace model name

        Returns:
            bool: Success
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT OR REPLACE INTO face_embeddings (face_id, embedding, model_name)
                VALUES (?, ?, ?)
            """, (face_id, embedding, model_name))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error adding face embedding: {e}")
            return False
        finally:
            conn.close()

    def get_faces_by_image(self, image_id: int) -> List[Dict]:
        """Get all faces detected in an image"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.*, fe.embedding, fe.model_name,
                   pg.name as person_name, pg.id as person_group_id
            FROM faces f
            LEFT JOIN face_embeddings fe ON f.id = fe.face_id
            LEFT JOIN person_groups pg ON f.person_group_id = pg.id
            WHERE f.image_id = ?
            ORDER BY f.id
        """, (image_id,))

        results = cursor.fetchall()
        conn.close()

        faces = []
        for row in results:
            face = self._row_to_dict(row)
            if face.get('bounding_box'):
                try:
                    face['bounding_box'] = json.loads(face['bounding_box'])
                except:
                    pass
            faces.append(face)

        return faces

    def get_all_face_embeddings(self) -> List[Tuple[int, bytes, int]]:
        """
        Get all face embeddings for clustering

        Returns:
            List of tuples: (face_id, embedding_bytes, person_group_id or None)
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT fe.face_id, fe.embedding, f.person_group_id
            FROM face_embeddings fe
            JOIN faces f ON fe.face_id = f.id
            ORDER BY fe.face_id
        """)

        results = cursor.fetchall()
        conn.close()

        return [(row['face_id'], row['embedding'], row['person_group_id']) for row in results]

    def create_person_group(self, name: str = None) -> int:
        """
        Create a new person group (represents one person)

        Args:
            name: Person name (optional, can be set later)

        Returns:
            int: Person group ID
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO person_groups (name, face_count)
                VALUES (?, 0)
            """, (name,))

            conn.commit()
            person_id = cursor.lastrowid
            return person_id
        except Exception as e:
            print(f"Error creating person group: {e}")
            return None
        finally:
            conn.close()

    def update_person_group_name(self, person_id: int, name: str) -> bool:
        """Update person group name"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE person_groups
                SET name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (name, person_id))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error updating person name: {e}")
            return False
        finally:
            conn.close()

    def assign_face_to_person(self, face_id: int, person_group_id: int) -> bool:
        """Assign a face to a person group"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE faces
                SET person_group_id = ?
                WHERE id = ?
            """, (person_group_id, face_id))

            # Update face count
            cursor.execute("""
                UPDATE person_groups
                SET face_count = (
                    SELECT COUNT(*) FROM faces WHERE person_group_id = ?
                ),
                updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (person_group_id, person_group_id))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error assigning face to person: {e}")
            return False
        finally:
            conn.close()

    def unassign_face(self, face_id: int) -> bool:
        """Remove face from its person group (make it unassigned)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get current person_group_id before unassigning
            cursor.execute("SELECT person_group_id FROM faces WHERE id = ?", (face_id,))
            result = cursor.fetchone()
            old_person_id = result['person_group_id'] if result else None

            # Set person_group_id to NULL
            cursor.execute("""
                UPDATE faces
                SET person_group_id = NULL
                WHERE id = ?
            """, (face_id,))

            # Update face count for the old person group
            if old_person_id:
                cursor.execute("""
                    UPDATE person_groups
                    SET face_count = (
                        SELECT COUNT(*) FROM faces WHERE person_group_id = ?
                    ),
                    updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (old_person_id, old_person_id))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error unassigning face: {e}")
            return False
        finally:
            conn.close()

    def get_all_person_groups(self) -> List[Dict]:
        """Get all person groups with face counts"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pg.*,
                   COUNT(DISTINCT f.id) as face_count,
                   COUNT(DISTINCT f.image_id) as image_count
            FROM person_groups pg
            LEFT JOIN faces f ON pg.id = f.person_group_id
            GROUP BY pg.id
            ORDER BY pg.name IS NULL, pg.name, pg.created_at DESC
        """)

        results = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in results]

    def get_person_group(self, person_id: int) -> Dict:
        """Get person group details"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT pg.*,
                   COUNT(DISTINCT f.id) as face_count,
                   COUNT(DISTINCT f.image_id) as image_count
            FROM person_groups pg
            LEFT JOIN faces f ON pg.id = f.person_group_id
            WHERE pg.id = ?
            GROUP BY pg.id
        """, (person_id,))

        result = cursor.fetchone()
        conn.close()

        return self._row_to_dict(result) if result else None

    def get_faces_by_person(self, person_id: int, limit: int = 100) -> List[Dict]:
        """Get all faces for a person group"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.*, i.filepath, i.filename, i.id as image_id
            FROM faces f
            JOIN images i ON f.image_id = i.id
            WHERE f.person_group_id = ?
            ORDER BY f.created_at DESC
            LIMIT ?
        """, (person_id, limit))

        results = cursor.fetchall()
        conn.close()

        faces = []
        for row in results:
            face = self._row_to_dict(row)
            if face.get('bounding_box'):
                try:
                    face['bounding_box'] = json.loads(face['bounding_box'])
                except:
                    pass
            faces.append(face)

        return faces

    def delete_person_group(self, person_id: int) -> bool:
        """Delete a person group (faces become unassigned)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM person_groups WHERE id = ?", (person_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting person group: {e}")
            return False
        finally:
            conn.close()

    def get_unassigned_faces(self, limit: int = 100) -> List[Dict]:
        """Get faces that haven't been assigned to any person"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT f.*, i.filepath, i.filename, i.id as image_id
            FROM faces f
            JOIN images i ON f.image_id = i.id
            WHERE f.person_group_id IS NULL
            ORDER BY f.created_at DESC
            LIMIT ?
        """, (limit,))

        results = cursor.fetchall()
        conn.close()

        faces = []
        for row in results:
            face = self._row_to_dict(row)
            if face.get('bounding_box'):
                try:
                    face['bounding_box'] = json.loads(face['bounding_box'])
                except:
                    pass
            faces.append(face)

        return faces

    # ============ YOUTUBE VIDEO OPERATIONS ============

    def add_youtube_video(self, image_id: int, youtube_id: str, metadata: Dict) -> Optional[int]:
        """
        Add YouTube video metadata linked to an image entry

        Args:
            image_id: The image ID (video entry in images table)
            youtube_id: YouTube video ID (e.g., 'dQw4w9WgXcQ')
            metadata: Dict with video metadata from yt-dlp

        Returns:
            int: YouTube video ID or None if failed
        """
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
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
        except sqlite3.IntegrityError as e:
            # Video already exists, get existing ID
            cursor.execute(
                "SELECT id FROM youtube_videos WHERE youtube_id = ?",
                (youtube_id,)
            )
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            print(f"Error adding YouTube video: {e}")
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
            # Parse JSON fields
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

    def add_video_keyframe(self, youtube_video_id: int, frame_number: int,
                           timestamp_ms: int, filepath: str) -> Optional[int]:
        """
        Add a keyframe extracted from a video

        Args:
            youtube_video_id: YouTube video ID (from youtube_videos table)
            frame_number: Frame sequence number
            timestamp_ms: Timestamp in milliseconds
            filepath: Path to the keyframe image

        Returns:
            int: Keyframe ID or None if failed
        """
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
            # Keyframe already exists
            cursor.execute(
                "SELECT id FROM video_keyframes WHERE youtube_video_id = ? AND frame_number = ?",
                (youtube_video_id, frame_number)
            )
            result = cursor.fetchone()
            return result['id'] if result else None
        except Exception as e:
            print(f"Error adding keyframe: {e}")
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

    def update_keyframe_analysis(self, keyframe_id: int, description: str, tags: List[str]):
        """Update keyframe with AI analysis"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                UPDATE video_keyframes
                SET description = ?, tags = ?
                WHERE id = ?
            """, (description, json.dumps(tags), keyframe_id))

            conn.commit()
        finally:
            conn.close()

    def add_video_subtitle(self, youtube_video_id: int, language: str,
                           start_time_ms: int, end_time_ms: int, text: str) -> Optional[int]:
        """
        Add a subtitle entry for a video

        Args:
            youtube_video_id: YouTube video ID
            language: Language code (e.g., 'en', 'bg')
            start_time_ms: Start time in milliseconds
            end_time_ms: End time in milliseconds
            text: Subtitle text

        Returns:
            int: Subtitle ID or None if failed
        """
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
            print(f"Error adding subtitle: {e}")
            return None
        finally:
            conn.close()

    def add_video_subtitles_batch(self, youtube_video_id: int, language: str,
                                  subtitles: List[Dict]) -> int:
        """
        Add multiple subtitle entries for a video

        Args:
            youtube_video_id: YouTube video ID
            language: Language code
            subtitles: List of dicts with start_time_ms, end_time_ms, text

        Returns:
            int: Number of subtitles added
        """
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
            print(f"Error adding subtitles batch: {e}")
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
        """
        Search across all video subtitles

        Returns list of matches with video info and timestamp
        """
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

    def delete_youtube_video(self, youtube_video_id: int) -> bool:
        """Delete a YouTube video and all related data (keyframes, subtitles)"""
        conn = self.get_connection()
        cursor = conn.cursor()

        try:
            # Get image_id before deleting
            cursor.execute("SELECT image_id FROM youtube_videos WHERE id = ?", (youtube_video_id,))
            result = cursor.fetchone()

            if result:
                image_id = result['image_id']
                # Delete YouTube video (cascades to keyframes and subtitles)
                cursor.execute("DELETE FROM youtube_videos WHERE id = ?", (youtube_video_id,))
                # Also delete from images table
                cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
                cursor.execute("DELETE FROM images_fts WHERE rowid = ?", (image_id,))

            conn.commit()
            return True
        except Exception as e:
            print(f"Error deleting YouTube video: {e}")
            return False
        finally:
            conn.close()