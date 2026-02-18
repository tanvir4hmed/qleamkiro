"""
Qleam — Similarity Utilities
Cosine similarity and cluster assignment logic
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Formula: similarity = dot(A, B) / (||A|| * ||B||)
    
    Returns:
        float in [-1, 1], where 1 = identical direction
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector length mismatch: {len(vec_a)} vs {len(vec_b)}")
    
    if not vec_a or not vec_b:
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    
    similarity = dot_product / (norm_a * norm_b)
    # Clamp to [-1, 1] to handle floating point errors
    return max(-1.0, min(1.0, similarity))


def find_best_cluster(
    embedding: List[float],
    clusters: List[Dict],
    threshold: float = 0.85
) -> Tuple[Optional[str], float]:
    """
    Find the best matching cluster for an embedding.
    
    Args:
        embedding: Audio embedding vector
        clusters: List of cluster dicts with 'cluster_id' and 'embedding_vector'
        threshold: Minimum cosine similarity to attach to existing cluster
    
    Returns:
        Tuple of (cluster_id or None, best_similarity_score)
        Returns (None, best_score) if no cluster meets threshold
    """
    if not clusters:
        return None, 0.0
    
    best_cluster_id = None
    best_similarity = -1.0
    
    for cluster in clusters:
        cluster_embedding = cluster.get("embedding_vector", [])
        if not cluster_embedding:
            continue
        
        try:
            sim = cosine_similarity(embedding, cluster_embedding)
            if sim > best_similarity:
                best_similarity = sim
                if sim >= threshold:
                    best_cluster_id = cluster["cluster_id"]
        except ValueError as e:
            logger.warning(f"Skipping cluster {cluster.get('cluster_id')}: {e}")
            continue
    
    return best_cluster_id, best_similarity


def update_centroid(
    current_centroid: List[float],
    new_vector: List[float],
    frequency_count: int
) -> List[float]:
    """
    Update cluster centroid using incremental mean.
    
    Formula: new_centroid = (old_centroid * (n-1) + new_vector) / n
    
    Args:
        current_centroid: Current cluster centroid
        new_vector: New embedding to incorporate
        frequency_count: New frequency count (after increment)
    
    Returns:
        Updated centroid vector
    """
    if len(current_centroid) != len(new_vector):
        logger.warning("Centroid/vector length mismatch, returning new vector")
        return new_vector
    
    if frequency_count <= 1:
        return new_vector
    
    n = frequency_count
    updated = [
        (current_centroid[i] * (n - 1) + new_vector[i]) / n
        for i in range(len(current_centroid))
    ]
    return [round(v, 8) for v in updated]


def euclidean_distance(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Compute Euclidean distance between two vectors.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector length mismatch: {len(vec_a)} vs {len(vec_b)}")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(vec_a, vec_b)))


def l2_normalize(vector: List[float]) -> List[float]:
    """
    L2-normalize a vector to unit length.
    """
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return vector
    return [v / norm for v in vector]
