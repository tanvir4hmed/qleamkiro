"""
Qleam — Reinforcement Engine Lambda
Updates reinforcement weights and semantic bridges based on parent feedback.

Trigger: POST /session/{id}/feedback → feedback_processor → this
Input:  { child_id, session_id, cluster_id, response_type, effectiveness }
Output: { status: "reinforcement_updated" }
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    REINFORCEMENT_DECAY_INEFFECTIVE,
    REINFORCEMENT_DECAY_NEUTRAL,
    REINFORCEMENT_LEARNING_RATE,
    REINFORCEMENT_MAX,
    REINFORCEMENT_MIN,
    SEMANTIC_BRIDGE_TABLE,
    SEMANTIC_CONFIDENCE_INCREMENT,
    SEMANTIC_CONFIDENCE_MAX,
    SOUND_CLUSTER_TABLE,
)
from normalization import clamp, normalize_probability_distribution

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)


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
        return Decimal("1") if obj else Decimal("0")
    
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


def get_cluster(cluster_id: str) -> Optional[Dict]:
    response = sound_cluster_table.get_item(Key={"cluster_id": cluster_id})
    if "Item" not in response:
        return None
    return _decimal_to_float(response["Item"])


def update_reinforcement_weight(current_weight: float, effectiveness: str) -> float:
    """
    Update reinforcement weight based on feedback effectiveness.
    
    helpful    → weight += 0.1 (cap at 1.0)
    neutral    → weight -= 0.02 (floor at 0.0)
    ineffective → weight -= 0.05 (floor at 0.0)
    """
    if effectiveness == "helpful":
        new_weight = current_weight + REINFORCEMENT_LEARNING_RATE
    elif effectiveness == "neutral":
        new_weight = current_weight - REINFORCEMENT_DECAY_NEUTRAL
    elif effectiveness == "ineffective":
        new_weight = current_weight - REINFORCEMENT_DECAY_INEFFECTIVE
    else:
        new_weight = current_weight  # Unknown effectiveness — no change
    
    return clamp(new_weight, REINFORCEMENT_MIN, REINFORCEMENT_MAX)


def update_probable_intents(
    probable_intents: Dict[str, float],
    response_type: str,
    effectiveness: str
) -> Dict[str, float]:
    """
    Update probable intent distribution based on feedback.
    
    If helpful: increase weight for the response_type intent.
    If ineffective: decrease weight for the response_type intent.
    Then normalize distribution.
    """
    if not response_type:
        return probable_intents
    
    intents = dict(probable_intents)
    
    # Map response_type to intent key
    intent_key = response_type.lower().replace(" ", "_")
    
    if effectiveness == "helpful":
        current = intents.get(intent_key, 0.1)
        intents[intent_key] = min(current + REINFORCEMENT_LEARNING_RATE, 1.0)
    elif effectiveness == "ineffective":
        current = intents.get(intent_key, 0.1)
        intents[intent_key] = max(current - REINFORCEMENT_DECAY_INEFFECTIVE, 0.0)
    
    # Ensure all values are non-negative
    intents = {k: max(0.0, v) for k, v in intents.items()}
    
    # Normalize distribution
    if sum(intents.values()) > 0:
        return normalize_probability_distribution(intents)
    
    return intents


def update_cluster(cluster_id: str, new_weight: float, new_intents: Dict):
    """Update cluster reinforcement weight and probable intents."""
    now = datetime.now(timezone.utc).isoformat()
    
    sound_cluster_table.update_item(
        Key={"cluster_id": cluster_id},
        UpdateExpression=(
            "SET reinforcement_weight = :rw, "
            "probable_intents = :pi, "
            "last_updated = :lu"
        ),
        ExpressionAttributeValues={
            ":rw": Decimal(str(new_weight)),
            ":pi": _float_to_decimal(new_intents),
            ":lu": now,
        }
    )


def update_semantic_bridge(
    child_id: str,
    cluster_id: str,
    word_token: Optional[str],
):
    """
    Update or create semantic bridge record.
    Triggered when a word is detected or parent confirms meaning.
    """
    if not word_token:
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if bridge exists for this cluster + word
    response = semantic_bridge_table.query(
        IndexName="cluster_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("cluster_id").eq(cluster_id)
    )
    
    existing_bridges = response.get("Items", [])
    existing_bridge = next(
        (b for b in existing_bridges if b.get("word_token") == word_token),
        None
    )
    
    if existing_bridge:
        bridge_id = existing_bridge["bridge_id"]
        current_confidence = float(existing_bridge.get("semantic_confidence_score", 0.0))
        current_count = int(existing_bridge.get("co_occurrence_count", 0))
        
        new_confidence = min(current_confidence + SEMANTIC_CONFIDENCE_INCREMENT, SEMANTIC_CONFIDENCE_MAX)
        
        semantic_bridge_table.update_item(
            Key={"bridge_id": bridge_id},
            UpdateExpression=(
                "SET co_occurrence_count = :cc, "
                "semantic_confidence_score = :scs, "
                "last_updated = :lu"
            ),
            ExpressionAttributeValues={
                ":cc": current_count + 1,
                ":scs": Decimal(str(new_confidence)),
                ":lu": now,
            }
        )
        logger.info(f"Updated semantic bridge {bridge_id}: confidence={new_confidence:.3f}")
        
        # Update cluster semantic alignment score
        sound_cluster_table.update_item(
            Key={"cluster_id": cluster_id},
            UpdateExpression="SET semantic_alignment_score = :sas, last_updated = :lu",
            ExpressionAttributeValues={
                ":sas": Decimal(str(new_confidence)),
                ":lu": now,
            }
        )
    else:
        # Create new bridge
        bridge_id = str(uuid.uuid4())
        new_bridge = {
            "bridge_id": bridge_id,
            "child_id": child_id,
            "cluster_id": cluster_id,
            "word_token": word_token,
            "co_occurrence_count": 1,
            "semantic_confidence_score": SEMANTIC_CONFIDENCE_INCREMENT,
            "last_updated": now,
            "created_at": now,
        }
        semantic_bridge_table.put_item(Item=_float_to_decimal(new_bridge))
        logger.info(f"Created new semantic bridge {bridge_id} for word '{word_token}'")


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Reinforcement Engine Lambda handler.
    
    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "cluster_id": str,
            "response_type": str,       # e.g. "feeding", "connection"
            "effectiveness": str,        # "helpful" | "neutral" | "ineffective"
            "word_token": str (optional) # detected/confirmed word
        }
    """
    logger.info(f"Reinforcement engine started: {json.dumps(event)}")
    
    child_id = event["child_id"]
    session_id = event["session_id"]
    cluster_id = event["cluster_id"]
    response_type = event.get("response_type", "")
    effectiveness = event.get("effectiveness", "neutral")
    word_token = event.get("word_token")
    
    # 1. Fetch cluster
    cluster = get_cluster(cluster_id)
    if not cluster:
        logger.error(f"Cluster {cluster_id} not found")
        return {"status": "error", "message": f"Cluster {cluster_id} not found"}
    
    current_weight = cluster.get("reinforcement_weight", 0.5)
    probable_intents = cluster.get("probable_intents", {})
    
    # 2. Update reinforcement weight
    new_weight = update_reinforcement_weight(current_weight, effectiveness)
    logger.info(f"Reinforcement weight: {current_weight:.3f} -> {new_weight:.3f} ({effectiveness})")
    
    # 3. Update probable intents
    new_intents = update_probable_intents(probable_intents, response_type, effectiveness)
    
    # 4. Update cluster
    update_cluster(cluster_id, new_weight, new_intents)
    
    # 5. Update semantic bridge (if word detected)
    if word_token:
        update_semantic_bridge(child_id, cluster_id, word_token)
    
    logger.info(f"Reinforcement update complete for cluster {cluster_id}")
    
    return {
        "status": "reinforcement_updated",
        "cluster_id": cluster_id,
        "session_id": session_id,
        "new_reinforcement_weight": round(new_weight, 4),
        "probable_intents": new_intents,
        "semantic_bridge_updated": word_token is not None,
    }
