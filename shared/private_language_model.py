"""
Qleam — Private Baby Language Model
Per-child language learning model that tracks unique baby sounds
and their meanings as labeled by parents.

Every baby develops their own "private language" — unique sound patterns
that consistently map to specific meanings. These are not human language
words but rather the baby's own vocal expressions.

This module:
1. Stores acoustic embeddings of baby sounds per child
2. Matches new sounds against stored patterns
3. Learns from parent feedback ("what were they saying?")
4. Grows with the baby over time

The model is PRIVATE per child — each child has their own pattern store.
However, aggregate statistics across all children help improve matching
(global baby language model — anonymous patterns only).

Storage: DynamoDB ConceptGraph table (category="baby_language")
"""
import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MATCH_SIMILARITY_THRESHOLD = 0.75  # Cosine similarity to consider a match
MIN_OBSERVATIONS = 2               # Minimum times heard before suggesting
CONFIDENCE_PER_OBSERVATION = 0.08  # Confidence increment per matching observation
MAX_CONFIDENCE = 0.90
EMBEDDING_DIM = 13                 # MFCC embedding dimension


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    a_arr = np.array(a, dtype=np.float64)
    b_arr = np.array(b, dtype=np.float64)
    dot = float(np.dot(a_arr, b_arr))
    norm_a = float(np.linalg.norm(a_arr))
    norm_b = float(np.linalg.norm(b_arr))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


def _decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _float_to_decimal(obj):
    import math as _math
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return obj
    if hasattr(obj, 'item'):
        try:
            obj = obj.item()
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return Decimal("0")
        return Decimal(str(obj))
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


def match_private_language(
    embedding: List[float],
    child_id: str,
    concept_graph_table,
) -> Dict[str, Any]:
    """
    Match an audio embedding against the child's private language patterns.

    Args:
        embedding: MFCC-based embedding vector of the current audio
        child_id: Child's unique ID
        concept_graph_table: DynamoDB Table resource for ConceptGraph

    Returns:
        {
            "matched": bool,
            "pattern_id": str or None,
            "parent_label": str or None,  # What parent said it means
            "similarity": float,
            "observation_count": int,
            "confidence": float,
            "all_matches": [...]  # All patterns above threshold
        }
    """
    if not embedding or len(embedding) < 3:
        return {"matched": False, "pattern_id": None, "parent_label": None,
                "similarity": 0.0, "observation_count": 0, "confidence": 0.0,
                "all_matches": []}

    try:
        # Query all baby_language concepts for this child
        from boto3.dynamodb.conditions import Key, Attr
        response = concept_graph_table.query(
            KeyConditionExpression=Key("child_id").eq(child_id),
            FilterExpression=Attr("category").eq("baby_language"),
        )
        patterns = _decimal_to_float(response.get("Items", []))
    except Exception as e:
        logger.warning(f"Failed to query private language patterns: {e}")
        return {"matched": False, "pattern_id": None, "parent_label": None,
                "similarity": 0.0, "observation_count": 0, "confidence": 0.0,
                "all_matches": []}

    if not patterns:
        return {"matched": False, "pattern_id": None, "parent_label": None,
                "similarity": 0.0, "observation_count": 0, "confidence": 0.0,
                "all_matches": []}

    # Compare against all stored patterns
    matches = []
    for pattern in patterns:
        stored_embedding = pattern.get("embedding_vector", [])
        if not stored_embedding:
            continue

        sim = _cosine_similarity(embedding, stored_embedding)
        if sim >= MATCH_SIMILARITY_THRESHOLD:
            obs_count = int(pattern.get("observation_count", 0))
            conf = min(MAX_CONFIDENCE, obs_count * CONFIDENCE_PER_OBSERVATION)
            matches.append({
                "pattern_id": pattern.get("concept_id", ""),
                "parent_label": pattern.get("label", ""),
                "parent_description": pattern.get("parent_description", ""),
                "similarity": round(sim, 3),
                "observation_count": obs_count,
                "confidence": round(conf, 3),
            })

    matches.sort(key=lambda x: x["similarity"], reverse=True)

    if matches:
        best = matches[0]
        return {
            "matched": True,
            "pattern_id": best["pattern_id"],
            "parent_label": best["parent_label"],
            "parent_description": best.get("parent_description", ""),
            "similarity": best["similarity"],
            "observation_count": best["observation_count"],
            "confidence": best["confidence"],
            "all_matches": matches[:3],
        }

    return {"matched": False, "pattern_id": None, "parent_label": None,
            "similarity": 0.0, "observation_count": 0, "confidence": 0.0,
            "all_matches": []}


def store_language_feedback(
    child_id: str,
    embedding: List[float],
    parent_label: str,
    parent_description: str,
    session_id: str,
    concept_graph_table,
    existing_pattern_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Store parent's language feedback as a private language pattern.

    If a matching pattern exists (existing_pattern_id), update it.
    Otherwise, create a new pattern.

    Args:
        child_id: Child's unique ID
        embedding: MFCC embedding of the sound
        parent_label: What parent says baby was saying (e.g., "want milk")
        parent_description: How parent describes the sound (e.g., "ba ba ba")
        session_id: Session this feedback came from
        concept_graph_table: DynamoDB Table resource
        existing_pattern_id: If updating an existing pattern

    Returns:
        {"status": "created" | "updated", "concept_id": str}
    """
    now = datetime.now(timezone.utc).isoformat()

    try:
        if existing_pattern_id:
            # Update existing pattern: increment count, update centroid
            response = concept_graph_table.get_item(
                Key={"child_id": child_id, "concept_id": existing_pattern_id}
            )
            item = _decimal_to_float(response.get("Item", {}))

            old_embedding = item.get("embedding_vector", [])
            old_count = int(item.get("observation_count", 0))
            new_count = old_count + 1

            # Incremental centroid update
            if old_embedding and len(old_embedding) == len(embedding):
                new_embedding = [
                    (old * old_count + new) / new_count
                    for old, new in zip(old_embedding, embedding)
                ]
            else:
                new_embedding = embedding

            concept_graph_table.update_item(
                Key={"child_id": child_id, "concept_id": existing_pattern_id},
                UpdateExpression=(
                    "SET embedding_vector = :ev, "
                    "observation_count = :oc, "
                    "label = :lb, "
                    "parent_description = :pd, "
                    "last_session_id = :sid, "
                    "last_updated = :lu"
                ),
                ExpressionAttributeValues=_float_to_decimal({
                    ":ev": new_embedding,
                    ":oc": new_count,
                    ":lb": parent_label,
                    ":pd": parent_description,
                    ":sid": session_id,
                    ":lu": now,
                }),
            )
            return {"status": "updated", "concept_id": existing_pattern_id}
        else:
            # Create new pattern
            concept_id = f"bl_{uuid.uuid4().hex[:8]}"
            item = {
                "child_id": child_id,
                "concept_id": concept_id,
                "category": "baby_language",
                "label": parent_label,
                "parent_description": parent_description,
                "embedding_vector": embedding,
                "observation_count": 1,
                "confidence": CONFIDENCE_PER_OBSERVATION,
                "first_session_id": session_id,
                "last_session_id": session_id,
                "first_appeared": now,
                "last_updated": now,
            }
            concept_graph_table.put_item(Item=_float_to_decimal(item))
            return {"status": "created", "concept_id": concept_id}

    except Exception as e:
        logger.error(f"Failed to store language feedback: {e}")
        return {"status": "error", "error": str(e)}


def get_child_vocabulary(
    child_id: str,
    concept_graph_table,
    min_observations: int = 2,
) -> List[Dict]:
    """
    Get all established private language patterns for a child.

    Returns list of patterns sorted by observation count descending.
    """
    try:
        from boto3.dynamodb.conditions import Key, Attr
        response = concept_graph_table.query(
            KeyConditionExpression=Key("child_id").eq(child_id),
            FilterExpression=Attr("category").eq("baby_language"),
        )
        patterns = _decimal_to_float(response.get("Items", []))

        # Filter by minimum observations
        established = [
            {
                "concept_id": p.get("concept_id", ""),
                "label": p.get("label", ""),
                "parent_description": p.get("parent_description", ""),
                "observation_count": int(p.get("observation_count", 0)),
                "confidence": float(p.get("confidence", 0)),
                "first_appeared": p.get("first_appeared", ""),
                "last_updated": p.get("last_updated", ""),
            }
            for p in patterns
            if int(p.get("observation_count", 0)) >= min_observations
        ]

        established.sort(key=lambda x: x["observation_count"], reverse=True)
        return established

    except Exception as e:
        logger.warning(f"Failed to get child vocabulary: {e}")
        return []
