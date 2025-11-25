"""
CLIP Embeddings and Semantic Search Utilities
Natural language image search using OpenAI's CLIP model
"""

import os
import numpy as np
from PIL import Image

# Try to import transformers and torch
try:
    from transformers import CLIPProcessor, CLIPModel
    import torch
    HAS_CLIP = True
except ImportError:
    HAS_CLIP = False
    print("Warning: transformers/torch not installed. Semantic search will be disabled.")
    print("Install with: pip install transformers torch")


class CLIPEmbeddingsGenerator:
    """Singleton class for managing CLIP model and generating embeddings"""

    _instance = None
    _model = None
    _processor = None
    _device = None
    _model_name = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize CLIP model (lazy loading)"""
        if not HAS_CLIP:
            self.available = False
            return

        self.available = True

        # Only load model once
        if self._model is None:
            self._load_model()
    
    @property
    def model_name(self):
        """Get the current model name"""
        return self._model_name or "openai/clip-vit-large-patch14-336"

    def _load_model(self):
        """Load CLIP model and processor"""
        try:
            print("Loading CLIP model (this may take a while on first run)...")

            # Use CPU or GPU
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Using device: {self._device}")

            # Модел може да се конфигурира чрез environment variable
            # Тъй като имаш RTX 4090, слагаме 'huge' по подразбиране!
            model_type = os.environ.get('CLIP_MODEL', 'huge').lower()
            
            model_configs = {
                'base32': 'openai/clip-vit-base-patch32',       # Стандартен (512 dim)
                'base16': 'openai/clip-vit-base-patch16',       # По-детайлен (512 dim)
                'large': 'openai/clip-vit-large-patch14',       # Голям (768 dim)
                'huge': 'openai/clip-vit-large-patch14-336',    # НАЙ-МОЩНИЯТ за твоята карта (768 dim, висока резолюция)
                'multilingual': 'laion/CLIP-ViT-B-32-xlm-roberta-base-laion5B-s13B-b90k'
            }
            
            model_name = model_configs.get(model_type, model_configs['huge'])
            
            print(f"Loading High-Performance CLIP model: {model_name}")
            
            self._model = CLIPModel.from_pretrained(model_name).to(self._device)
            self._processor = CLIPProcessor.from_pretrained(model_name)
            self._model_name = model_name

            print(f"✅ CLIP model '{model_name}' loaded successfully")

        except Exception as e:
            print(f"❌ Error loading CLIP model: {e}")
            self.available = False
            self._model = None
            self._processor = None

    def generate_image_embedding(self, image_path):
        """
        Generate CLIP embedding for an image
        """
        if not self.available or self._model is None:
            return None

        try:
            # Load and preprocess image
            image = Image.open(image_path).convert('RGB')
            inputs = self._processor(images=image, return_tensors="pt").to(self._device)

            # Generate embedding
            with torch.no_grad():
                image_features = self._model.get_image_features(**inputs)

            # Normalize embedding (for cosine similarity)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)

            # Convert to numpy array
            embedding = image_features.cpu().numpy().flatten()

            return embedding

        except Exception as e:
            print(f"Error generating embedding for {image_path}: {e}")
            return None

    def generate_text_embedding(self, text_query):
        """
        Generate CLIP embedding for a text query
        """
        if not self.available or self._model is None:
            return None

        try:
            # Preprocess text
            inputs = self._processor(text=[text_query], return_tensors="pt", padding=True).to(self._device)

            # Generate embedding
            with torch.no_grad():
                text_features = self._model.get_text_features(**inputs)

            # Normalize embedding (for cosine similarity)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)

            # Convert to numpy array
            embedding = text_features.cpu().numpy().flatten()

            return embedding

        except Exception as e:
            print(f"Error generating text embedding for '{text_query}': {e}")
            return None

    def compute_similarity(self, embedding1, embedding2):
        """
        Compute cosine similarity between two embeddings
        """
        if embedding1 is None or embedding2 is None:
            return 0.0

        try:
            # Check dimensions match (Critical when switching models!)
            if embedding1.shape != embedding2.shape:
                # Ако размерите не съвпадат, значи сравняваме вектори от различни модели
                return 0.0

            # Cosine similarity (embeddings are already normalized)
            similarity = np.dot(embedding1, embedding2)
            return float(similarity)

        except Exception as e:
            print(f"Error computing similarity: {e}")
            return 0.0

    def unload_model(self):
        """
        Unload CLIP model from memory to free GPU/RAM.
        Useful when memory is needed for other operations.
        Model will be reloaded automatically on next use.
        """
        if self._model is not None:
            print("🧹 Unloading CLIP model from memory...")
            del self._model
            self._model = None

        if self._processor is not None:
            del self._processor
            self._processor = None

        # Clear CUDA cache if using GPU
        if HAS_CLIP and self._device == "cuda":
            try:
                torch.cuda.empty_cache()
                print("✅ CUDA cache cleared")
            except Exception as e:
                print(f"⚠️ Could not clear CUDA cache: {e}")

        self.available = False
        print("✅ CLIP model unloaded successfully")

    def get_memory_usage(self) -> dict:
        """
        Get current memory usage of the CLIP model.
        Returns dict with RAM and VRAM usage in MB.
        """
        result = {
            'model_loaded': self._model is not None,
            'device': self._device,
            'model_name': self._model_name
        }

        if HAS_CLIP and self._device == "cuda":
            try:
                # GPU memory
                allocated = torch.cuda.memory_allocated() / (1024 * 1024)
                reserved = torch.cuda.memory_reserved() / (1024 * 1024)
                result['gpu_allocated_mb'] = round(allocated, 2)
                result['gpu_reserved_mb'] = round(reserved, 2)
            except Exception:
                pass

        return result


# Global instance
_clip_generator = None


def get_clip_generator():
    """Get or create the global CLIP generator instance"""
    global _clip_generator
    if _clip_generator is None:
        _clip_generator = CLIPEmbeddingsGenerator()
    return _clip_generator


def unload_clip_model():
    """Unload CLIP model to free memory"""
    global _clip_generator
    if _clip_generator is not None:
        _clip_generator.unload_model()
        _clip_generator = None
        print("✅ Global CLIP generator released")


def get_clip_memory_usage() -> dict:
    """Get memory usage of the CLIP model"""
    global _clip_generator
    if _clip_generator is None:
        return {'model_loaded': False}
    return _clip_generator.get_memory_usage()


def is_clip_available():
    """Check if CLIP model is available"""
    if not HAS_CLIP:
        return False

    generator = get_clip_generator()
    return generator.available


def get_clip_model_version():
    """Get the current CLIP model version/name"""
    if not HAS_CLIP:
        return None
    generator = get_clip_generator()
    if not generator.available:
        return None
    return generator.model_name


def generate_embedding_for_image(image_path):
    """
    Generate CLIP embedding for an image
    """
    generator = get_clip_generator()

    if not generator.available:
        return None

    embedding = generator.generate_image_embedding(image_path)

    if embedding is not None:
        return embedding.tolist()

    return None


def search_by_text_query(text_query, image_embeddings):
    """
    Search images by natural language query
    """
    generator = get_clip_generator()

    if not generator.available:
        return None

    # Generate text embedding
    text_embedding = generator.generate_text_embedding(text_query)

    if text_embedding is None:
        return None

    # Compute similarities
    results = []

    for item in image_embeddings:
        image_id = item['id']
        image_embedding = np.array(item['embedding'])

        similarity = generator.compute_similarity(text_embedding, image_embedding)

        results.append({
            'image_id': image_id,
            'similarity': similarity
        })

    # Sort by similarity (descending)
    results.sort(key=lambda x: x['similarity'], reverse=True)

    return results


def find_similar_images(query_embedding, all_embeddings, top_k=10, exclude_id=None):
    """
    Find most similar images to a query embedding
    """
    generator = get_clip_generator()

    if not generator.available:
        return []

    query_emb = np.array(query_embedding)

    results = []

    for item in all_embeddings:
        image_id = item['id']

        # Skip excluded image
        if exclude_id is not None and image_id == exclude_id:
            continue

        image_embedding = np.array(item['embedding'])

        similarity = generator.compute_similarity(query_emb, image_embedding)

        results.append({
            'image_id': image_id,
            'similarity': similarity
        })

    # Sort by similarity (descending)
    results.sort(key=lambda x: x['similarity'], reverse=True)

    # Return top K
    return results[:top_k]


def embedding_to_blob(embedding):
    """
    Convert embedding numpy array to binary blob for database storage
    """
    if embedding is None:
        return None

    if isinstance(embedding, list):
        embedding = np.array(embedding, dtype=np.float32)

    return embedding.tobytes()


def blob_to_embedding(blob):
    """
    Convert binary blob from database back to numpy array
    """
    if blob is None:
        return None

    return np.frombuffer(blob, dtype=np.float32)