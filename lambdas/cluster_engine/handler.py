"""
Qleam — Cluster Engine Lambda
Assigns audio embedding to existing cluster or creates new cluster.

Trigger: Step Function second state
Input:  { child_id, session_id, embedding_vector }
Output: { status, cluster_id, action: "attached"|"created" }
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CLUSTER_SIMILARITY_THRESHOLD,
    REINFORCEMENT_NEUTRAL_START,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
)
from similarity import find_best_cluster, update_centroid

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)


def _float_to_decimal(obj: Any) -> Any:
    """Convert floats to Decimal for DynamoDB. Handles numpy floats and edge cases."""
    import math
    
    # Handle None
    if obj is None:
        return None
    
    # Handle Decimal (already converted)
    if isinstance(obj, Decimal):
        return obj
    
    # Handle numpy numeric types without requiring numpy import
    if hasattr(obj, 'item'):
        try:
            obj = obj.item()
        except (AttributeError, TypeError):
            pass
    
    # Handle Python int (safe to convert directly)
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
    
    # Handle Python float
    if isinstance(obj, float):
        # Check for NaN, inf, -inf which Decimal can't handle
        if math.isnan(obj):
            return Decimal("0")
        if math.isinf(obj):
            return Decimal("0") if obj < 0 else Decimal("1")
        return Decimal(str(obj))
    
    # Handle boolean
    if isinstance(obj, bool):
        return obj
    
    # Handle string - try to convert if it looks like a number
    if isinstance(obj, str):
        try:
            return Decimal(obj)
        except:
            return obj  # Return as-is if not a valid number string
    
    # Handle dict recursively
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    
    # Handle list recursively
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    
    # Return everything else as-is (strings, booleans, etc.)
    return obj


def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def get_child_clusters(child_id: str) -> List[Dict]:
    """Fetch all clusters for a child."""
    response = sound_cluster_table.query(
        IndexName="child_id-last_updated-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id)
    )
    clusters = response.get("Items", [])
    return [_decimal_to_float(c) for c in clusters]


def attach_to_cluster(cluster_id: str, embedding_vector: List[float], session_id: str):
    """Attach session to existing cluster, update centroid and frequency."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Get current cluster
    response = sound_cluster_table.get_item(Key={"cluster_id": cluster_id})
    cluster = _decimal_to_float(response["Item"])
    
    current_centroid = cluster.get("embedding_vector", embedding_vector)
    current_count = cluster.get("frequency_count", 1)
    new_count = current_count + 1
    
    # Update centroid using incremental mean
    new_centroid = update_centroid(current_centroid, embedding_vector, new_count)
    
    sound_cluster_table.update_item(
        Key={"cluster_id": cluster_id},
        UpdateExpression=(
            "SET frequency_count = :fc, "
            "embedding_vector = :ev, "
            "last_updated = :lu"
        ),
        ExpressionAttributeValues=_float_to_decimal({
            ":fc": new_count,
            ":ev": new_centroid,
            ":lu": now,
        })
    )
    
    logger.info(f"Attached session {session_id} to cluster {cluster_id} (count: {new_count})")


def create_new_cluster(child_id: str, embedding_vector: List[float], session_id: str) -> str:
    """Create a new sound cluster."""
    now = datetime.now(timezone.utc).isoformat()
    cluster_id = str(uuid.uuid4())
    
    new_cluster = {
        "cluster_id": cluster_id,
        "child_id": child_id,
        "embedding_vector": embedding_vector,
        "frequency_count": 1,
        "reinforcement_weight": REINFORCEMENT_NEUTRAL_START,
        "probable_intents": {},
        "semantic_alignment_score": 0.0,
        "last_updated": now,
        "created_at": now,
    }
    
    sound_cluster_table.put_item(Item=_float_to_decimal(new_cluster))
    logger.info(f"Created new cluster {cluster_id} for child {child_id}")
    return cluster_id


def link_session_to_cluster(session_id: str, cluster_id: str):
    """Update session record with cluster_id."""
    session_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET cluster_id = :cid",
        ExpressionAttributeValues={":cid": cluster_id}
    )


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Cluster Engine Lambda handler.
    
    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "embedding_vector": List[float]
        }
    
    Returns:
        {
            "status": "cluster_updated",
            "cluster_id": str,
            "action": "attached" | "created",
            "similarity_score": float
        }
    """
    logger.info(f"Cluster engine started for session {event.get('session_id')}")
    
    child_id = event["child_id"]
    session_id = event["session_id"]
    embedding_vector = event["embedding_vector"]

    # Fail-safe: non-admitted sessions should not enter clustering.
    try:
        session_resp = session_table.get_item(Key={"session_id": session_id})
        session_item = _decimal_to_float(session_resp.get("Item", {}))
        admission_status = str(
            (session_item.get("admission_gate") or {}).get("status", "")
        ).upper().strip()
        if admission_status and admission_status != "BABY_PASS":
            logger.warning(
                f"Skipping clustering for non-admitted session {session_id}: "
                f"admission_status={admission_status}"
            )
            return {
                "status": "skipped_not_admitted",
                "cluster_id": "",
                "action": "skipped",
                "similarity_score": 0.0,
                "session_id": session_id,
                "child_id": child_id,
                "admission_status": admission_status,
            }
    except Exception as e:
        logger.warning(f"Admission fail-safe check failed (continuing): {e}")
    
    threshold = float(os.environ.get("CLUSTER_SIMILARITY_THRESHOLD", str(CLUSTER_SIMILARITY_THRESHOLD)))
    
    # 1. Fetch all existing clusters for this child
    clusters = get_child_clusters(child_id)
    logger.info(f"Found {len(clusters)} existing clusters for child {child_id}")
    
    # 2. Find best matching cluster
    best_cluster_id, best_similarity = find_best_cluster(embedding_vector, clusters, threshold)
    
    # 3. Attach or create
    if best_cluster_id:
        attach_to_cluster(best_cluster_id, embedding_vector, session_id)
        cluster_id = best_cluster_id
        action = "attached"
        logger.info(f"Attached to cluster {cluster_id} (similarity: {best_similarity:.4f})")
    else:
        cluster_id = create_new_cluster(child_id, embedding_vector, session_id)
        action = "created"
        logger.info(f"Created new cluster {cluster_id} (best similarity was: {best_similarity:.4f})")
    
    # 4. Link session to cluster
    link_session_to_cluster(session_id, cluster_id)
    
    return {
        "status": "cluster_updated",
        "cluster_id": cluster_id,
        "action": action,
        "similarity_score": round(best_similarity, 4),
        "session_id": session_id,
        "child_id": child_id,
    }
