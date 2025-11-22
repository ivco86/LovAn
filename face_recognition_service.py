"""
Face Recognition Service using DeepFace
Detects faces, generates embeddings, and clusters faces into person groups
"""

import numpy as np
import io
from PIL import Image
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class FaceRecognitionService:
    """Service for face detection and recognition using DeepFace"""

    def __init__(self, model_name='Facenet', detector_backend='opencv'):
        """
        Initialize face recognition service

        Args:
            model_name: DeepFace model ('VGG-Face', 'Facenet', 'ArcFace', 'OpenFace', 'DeepFace', 'DeepID', 'Dlib')
            detector_backend: Face detector ('opencv', 'ssd', 'dlib', 'mtcnn', 'retinaface')
        """
        self.model_name = model_name
        self.detector_backend = detector_backend
        self.enabled = False

        try:
            from deepface import DeepFace
            self.DeepFace = DeepFace
            self.enabled = True
            print(f"[FACE] ✅ DeepFace initialized with model: {model_name}, detector: {detector_backend}")
        except ImportError:
            print("[FACE] ⚠️ DeepFace not installed. Face recognition disabled.")
            print("[FACE] Install with: pip install deepface tf-keras")
            self.DeepFace = None

    def detect_and_analyze_faces(self, image_path: str) -> List[Dict]:
        """
        Detect faces in an image and analyze attributes

        Args:
            image_path: Path to image file

        Returns:
            List of face dictionaries with:
                - bounding_box: {x, y, w, h}
                - confidence: detection confidence
                - age: estimated age
                - gender: 'Man' or 'Woman'
                - emotion: dominant emotion
                - embedding: face embedding vector
        """
        if not self.enabled or not self.DeepFace:
            return []

        try:
            # Analyze faces (includes detection + attributes + embedding)
            # Try with silent parameter first (newer DeepFace versions)
            try:
                results = self.DeepFace.analyze(
                    img_path=str(image_path),
                    actions=['age', 'gender', 'emotion'],
                    detector_backend=self.detector_backend,
                    enforce_detection=False,
                    silent=True
                )
            except TypeError:
                # Fallback for older DeepFace versions without silent parameter
                results = self.DeepFace.analyze(
                    img_path=str(image_path),
                    actions=['age', 'gender', 'emotion'],
                    detector_backend=self.detector_backend,
                    enforce_detection=False
                )

            # Handle single face vs multiple faces
            if not isinstance(results, list):
                results = [results]

            faces = []
            for i, face_data in enumerate(results):
                try:
                    # Extract bounding box (region)
                    region = face_data.get('region', {})
                    bbox = {
                        'x': region.get('x', 0),
                        'y': region.get('y', 0),
                        'w': region.get('w', 0),
                        'h': region.get('h', 0)
                    }

                    # Get embedding for this face
                    embedding = self.get_face_embedding(image_path, target_face=i)

                    face = {
                        'bounding_box': bbox,
                        'confidence': face_data.get('confidence', 1.0),
                        'age': int(face_data.get('age', 0)),
                        'gender': face_data.get('dominant_gender', 'Unknown'),
                        'emotion': face_data.get('dominant_emotion', 'Unknown'),
                        'embedding': embedding
                    }

                    faces.append(face)

                except Exception as e:
                    print(f"[FACE] ⚠️ Error processing face {i}: {e}")
                    continue

            if faces:
                print(f"[FACE] ✅ Detected {len(faces)} face(s) in {Path(image_path).name}")

            return faces

        except ValueError as e:
            # No face detected
            if "Face could not be detected" in str(e):
                return []
            print(f"[FACE] ⚠️ Error analyzing {image_path}: {e}")
            return []
        except Exception as e:
            print(f"[FACE] ⚠️ Error analyzing {image_path}: {e}")
            import traceback
            traceback.print_exc()
            return []

    def get_face_embedding(self, image_path: str, target_face: int = 0) -> Optional[np.ndarray]:
        """
        Generate embedding for a specific face in an image

        Args:
            image_path: Path to image
            target_face: Index of face to embed (for multiple faces)

        Returns:
            numpy array: embedding vector
        """
        if not self.enabled or not self.DeepFace:
            return None

        try:
            # Try with silent parameter first (newer DeepFace versions)
            try:
                embeddings = self.DeepFace.represent(
                    img_path=str(image_path),
                    model_name=self.model_name,
                    detector_backend=self.detector_backend,
                    enforce_detection=False,
                    silent=True
                )
            except TypeError:
                # Fallback for older DeepFace versions without silent parameter
                embeddings = self.DeepFace.represent(
                    img_path=str(image_path),
                    model_name=self.model_name,
                    detector_backend=self.detector_backend,
                    enforce_detection=False
                )

            # Handle single vs multiple faces
            if not isinstance(embeddings, list):
                embeddings = [embeddings]

            if target_face < len(embeddings):
                embedding_data = embeddings[target_face]
                # Extract embedding vector
                if isinstance(embedding_data, dict) and 'embedding' in embedding_data:
                    return np.array(embedding_data['embedding'])
                elif isinstance(embedding_data, list):
                    return np.array(embedding_data)
                else:
                    return np.array(embedding_data)

            return None

        except Exception as e:
            print(f"[FACE] ⚠️ Error generating embedding: {e}")
            return None

    def serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Convert numpy embedding to bytes for database storage"""
        if embedding is None:
            return None
        buffer = io.BytesIO()
        np.save(buffer, embedding)
        return buffer.getvalue()

    def deserialize_embedding(self, embedding_bytes: bytes) -> np.ndarray:
        """Convert bytes back to numpy embedding"""
        if not embedding_bytes:
            return None
        buffer = io.BytesIO(embedding_bytes)
        return np.load(buffer)

    def calculate_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """
        Calculate cosine similarity between two embeddings

        Args:
            embedding1, embedding2: Face embedding vectors

        Returns:
            float: Similarity score (0-1, higher is more similar)
        """
        if embedding1 is None or embedding2 is None:
            return 0.0

        # Normalize vectors
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

        # Convert to 0-1 range
        return (similarity + 1) / 2

    def cluster_faces(self, face_embeddings: List[Tuple[int, np.ndarray]],
                     similarity_threshold: float = 0.6) -> Dict[int, int]:
        """
        Cluster faces into groups using similarity threshold

        Args:
            face_embeddings: List of (face_id, embedding) tuples
            similarity_threshold: Minimum similarity to group faces (0-1)

        Returns:
            Dict mapping face_id -> group_id
        """
        if not face_embeddings:
            return {}

        from sklearn.cluster import DBSCAN
        from sklearn.preprocessing import normalize

        # Extract embeddings
        face_ids = [f[0] for f in face_embeddings]
        embeddings = np.array([f[1] for f in face_embeddings])

        # Normalize embeddings
        embeddings_normalized = normalize(embeddings)

        # Convert similarity threshold to distance threshold
        # Cosine distance = 1 - cosine_similarity
        # For similarity_threshold of 0.6, we want distance <= 0.4
        distance_threshold = 1 - similarity_threshold

        # DBSCAN clustering
        clustering = DBSCAN(
            eps=distance_threshold,
            min_samples=1,  # Allow single-face groups
            metric='cosine'
        )

        labels = clustering.fit_predict(embeddings_normalized)

        # Map face_id to group_id
        face_to_group = {}
        for face_id, label in zip(face_ids, labels):
            # DBSCAN uses -1 for noise, but we want all faces grouped
            group_id = int(label) if label >= 0 else -1
            face_to_group[face_id] = group_id

        print(f"[FACE] 🔗 Clustered {len(face_ids)} faces into {len(set(labels))} groups")
        return face_to_group

    def find_similar_faces(self, query_embedding: np.ndarray,
                          face_embeddings: List[Tuple[int, np.ndarray]],
                          top_k: int = 10,
                          min_similarity: float = 0.5) -> List[Tuple[int, float]]:
        """
        Find most similar faces to a query embedding

        Args:
            query_embedding: Query face embedding
            face_embeddings: List of (face_id, embedding) tuples to search
            top_k: Number of results to return
            min_similarity: Minimum similarity threshold

        Returns:
            List of (face_id, similarity_score) tuples, sorted by similarity
        """
        if not face_embeddings or query_embedding is None:
            return []

        similarities = []
        for face_id, embedding in face_embeddings:
            similarity = self.calculate_similarity(query_embedding, embedding)
            if similarity >= min_similarity:
                similarities.append((face_id, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]