"""
Image Hashing Utilities for Duplicate Detection

Uses perceptual hashing (pHash) to find duplicate and similar images
even after resize, crop, or compression.

Methods:
- pHash (perceptual): Best for photos, handles resize/crop well
- dHash (difference): Fastest, good for exact duplicates
- aHash (average): Simplest, catches obvious duplicates
"""

import os
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image

try:
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False
    print("Warning: imagehash not installed. Run: pip install imagehash")


def compute_phash(image_path: str, hash_size: int = 16) -> Optional[str]:
    """
    Compute perceptual hash for an image.

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash (default 16 for 256-bit hash)

    Returns:
        Hex string of the hash, or None if failed
    """
    if not IMAGEHASH_AVAILABLE:
        return None

    try:
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Compute perceptual hash
            phash = imagehash.phash(img, hash_size=hash_size)
            return str(phash)
    except Exception as e:
        print(f"Error computing phash for {image_path}: {e}")
        return None


def compute_dhash(image_path: str, hash_size: int = 16) -> Optional[str]:
    """
    Compute difference hash for an image (faster but less robust).

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash

    Returns:
        Hex string of the hash, or None if failed
    """
    if not IMAGEHASH_AVAILABLE:
        return None

    try:
        with Image.open(image_path) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            dhash = imagehash.dhash(img, hash_size=hash_size)
            return str(dhash)
    except Exception as e:
        print(f"Error computing dhash for {image_path}: {e}")
        return None


def compute_ahash(image_path: str, hash_size: int = 16) -> Optional[str]:
    """
    Compute average hash for an image (simplest, least robust).

    Args:
        image_path: Path to the image file
        hash_size: Size of the hash

    Returns:
        Hex string of the hash, or None if failed
    """
    if not IMAGEHASH_AVAILABLE:
        return None

    try:
        with Image.open(image_path) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            ahash = imagehash.average_hash(img, hash_size=hash_size)
            return str(ahash)
    except Exception as e:
        print(f"Error computing ahash for {image_path}: {e}")
        return None


def compute_all_hashes(image_path: str) -> dict:
    """
    Compute all hash types for an image.

    Returns:
        Dictionary with 'phash', 'dhash', 'ahash' keys
    """
    return {
        'phash': compute_phash(image_path),
        'dhash': compute_dhash(image_path),
        'ahash': compute_ahash(image_path)
    }


def hamming_distance(hash1: str, hash2: str) -> int:
    """
    Calculate hamming distance between two hashes.

    Args:
        hash1: First hash as hex string
        hash2: Second hash as hex string

    Returns:
        Number of different bits (lower = more similar)
    """
    if not hash1 or not hash2:
        return -1

    if len(hash1) != len(hash2):
        return -1

    # Convert hex strings to integers and XOR
    try:
        h1 = int(hash1, 16)
        h2 = int(hash2, 16)
        xor = h1 ^ h2
        # Count the number of 1 bits
        return bin(xor).count('1')
    except ValueError:
        return -1


def is_duplicate(hash1: str, hash2: str, threshold: int = 0) -> bool:
    """
    Check if two hashes indicate duplicate images.

    Args:
        hash1: First hash
        hash2: Second hash
        threshold: Maximum hamming distance to consider as duplicate (0 = exact)

    Returns:
        True if images are duplicates
    """
    distance = hamming_distance(hash1, hash2)
    return distance >= 0 and distance <= threshold


def is_similar(hash1: str, hash2: str, threshold: int = 10) -> Tuple[bool, int]:
    """
    Check if two hashes indicate similar images.

    Args:
        hash1: First hash
        hash2: Second hash
        threshold: Maximum hamming distance to consider as similar

    Returns:
        Tuple of (is_similar, distance)
    """
    distance = hamming_distance(hash1, hash2)
    return (distance >= 0 and distance <= threshold, distance)


def find_duplicates_in_list(hashes: List[Tuple[int, str]], threshold: int = 0) -> List[List[int]]:
    """
    Find duplicate groups in a list of (id, hash) tuples.

    Args:
        hashes: List of (image_id, hash_string) tuples
        threshold: Maximum hamming distance for duplicates

    Returns:
        List of duplicate groups, each group is a list of image IDs
    """
    if not hashes:
        return []

    # Group by exact hash first for efficiency
    hash_groups = {}
    for img_id, hash_str in hashes:
        if hash_str:
            if hash_str not in hash_groups:
                hash_groups[hash_str] = []
            hash_groups[hash_str].append(img_id)

    # Find exact duplicates
    duplicates = []
    for hash_str, ids in hash_groups.items():
        if len(ids) > 1:
            duplicates.append(ids)

    # If threshold > 0, also find near-duplicates
    if threshold > 0:
        unique_hashes = list(hash_groups.keys())
        near_duplicates = []

        for i, h1 in enumerate(unique_hashes):
            for h2 in unique_hashes[i+1:]:
                distance = hamming_distance(h1, h2)
                if 0 < distance <= threshold:
                    # Merge groups
                    ids1 = hash_groups[h1]
                    ids2 = hash_groups[h2]
                    near_duplicates.append(ids1 + ids2)

        duplicates.extend(near_duplicates)

    return duplicates


def compute_phash_from_bytes(image_bytes: bytes, hash_size: int = 16) -> Optional[str]:
    """
    Compute perceptual hash from image bytes (for upload checking).

    Args:
        image_bytes: Raw image bytes
        hash_size: Size of the hash

    Returns:
        Hex string of the hash, or None if failed
    """
    if not IMAGEHASH_AVAILABLE:
        return None

    try:
        from io import BytesIO
        with Image.open(BytesIO(image_bytes)) as img:
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            phash = imagehash.phash(img, hash_size=hash_size)
            return str(phash)
    except Exception as e:
        print(f"Error computing phash from bytes: {e}")
        return None


# Thresholds for different use cases
THRESHOLDS = {
    'exact': 0,           # Exact duplicates only
    'near_duplicate': 5,  # Very similar (resize, minor crop)
    'similar': 10,        # Similar images
    'loose': 15,          # Loosely related
}
