"""
Qleam — Insight Generator Lambda
Translates system state into structured, non-diagnostic parent guidance.

Trigger: Step Function third state
Input:  { child_id, session_id, cluster_id }
Output: Structured insight JSON stored in Session table
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    BEDROCK_MODEL_ID,
    CHILD_PROFILE_TABLE,
    DISCLAIMER,
    INTENT_LABELS,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    SUGGESTED_RESPONSES,
    USE_BEDROCK,
)

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)


def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


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


def get_session(session_id: str) -> Optional[Dict]:
    response = session_table.get_item(Key={"session_id": session_id})
    return _decimal_to_float(response.get("Item"))


def get_child_profile(child_id: str) -> Optional[Dict]:
    response = child_profile_table.get_item(Key={"child_id": child_id})
    return _decimal_to_float(response.get("Item"))


def get_cluster(cluster_id: str) -> Optional[Dict]:
    response = sound_cluster_table.get_item(Key={"cluster_id": cluster_id})
    return _decimal_to_float(response.get("Item"))


def get_semantic_bridge(cluster_id: str) -> Optional[Dict]:
    """Get the highest-confidence semantic bridge for a cluster."""
    response = semantic_bridge_table.query(
        IndexName="cluster_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("cluster_id").eq(cluster_id)
    )
    bridges = response.get("Items", [])
    if not bridges:
        return None
    # Return highest confidence bridge
    return _decimal_to_float(max(bridges, key=lambda b: float(b.get("semantic_confidence_score", 0))))


def determine_probable_intent(cluster: Dict) -> Dict:
    """
    Determine the most probable intent from cluster data.
    
    Returns:
        {
            "label": str,
            "key": str,
            "confidence": float
        }
    """
    probable_intents = cluster.get("probable_intents", {})
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    frequency_count = cluster.get("frequency_count", 1)
    semantic_alignment = cluster.get("semantic_alignment_score", 0.0)
    
    if not probable_intents:
        # No intents yet — return unknown
        confidence = min(reinforcement_weight * 0.3, 0.4)
        return {
            "label": INTENT_LABELS["unknown"],
            "key": "unknown",
            "confidence": round(confidence, 3),
        }
    
    # Find highest weighted intent
    best_intent_key = max(probable_intents, key=probable_intents.get)
    intent_weight = probable_intents[best_intent_key]
    
    # Confidence = intent_weight * reinforcement_weight * frequency_factor * semantic_factor
    frequency_factor = min(frequency_count / 10.0, 1.0)  # Caps at 10 sessions
    semantic_factor = 1.0 + (semantic_alignment * 0.2)   # Semantic alignment boosts confidence
    
    confidence = intent_weight * reinforcement_weight * frequency_factor * semantic_factor
    confidence = min(confidence, 0.95)  # Never claim 100% certainty
    
    label = INTENT_LABELS.get(best_intent_key, best_intent_key.replace("_", " ").title())
    
    return {
        "label": label,
        "key": best_intent_key,
        "confidence": round(confidence, 3),
    }


def determine_cluster_stability(cluster: Dict) -> str:
    """Determine cluster stability label."""
    frequency_count = cluster.get("frequency_count", 1)
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    
    if frequency_count >= 10 and reinforcement_weight >= 0.7:
        return "stable"
    elif frequency_count >= 5 or reinforcement_weight >= 0.5:
        return "emerging"
    else:
        return "forming"


def get_suggested_response(intent_key: str) -> str:
    """Get rule-based suggested response for intent."""
    return SUGGESTED_RESPONSES.get(intent_key, SUGGESTED_RESPONSES["unknown"])


def generate_insight_with_bedrock(
    session: Dict,
    profile: Dict,
    cluster: Dict,
    probable_intent: Dict,
    semantic_bridge: Optional[Dict],
) -> str:
    """
    Generate natural language insight using Amazon Bedrock.
    Falls back to rule-based if Bedrock fails.
    """
    try:
        bedrock = boto3.client("bedrock-runtime")
        model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)
        
        prompt = f"""You are a gentle, supportive assistant helping parents understand their baby's communication patterns.

Based on the following observations, provide a warm, clear, 2-3 sentence explanation for the parent.
Use simple, non-clinical language. Never make medical claims. Always express uncertainty appropriately.

Observations:
- Emotional intensity: {session.get('feature_scores', {}).get('emotional_intensity', 0):.2f} (0=calm, 1=intense)
- Deviation from baseline: {session.get('deviation_level', 'none')}
- Pattern stability: {determine_cluster_stability(cluster)}
- Most likely need: {probable_intent['label']} (confidence: {probable_intent['confidence']:.0%})
- Reinforcement weight: {cluster.get('reinforcement_weight', 0.5):.2f}

Write a supportive, 2-3 sentence observation for the parent. End with the disclaimer: "This is a behavioral observation, not medical advice."
"""
        
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        })
        
        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    
    except Exception as e:
        logger.warning(f"Bedrock failed, using rule-based: {e}")
        return get_suggested_response(probable_intent.get("key", "unknown"))


def build_insight(
    session: Dict,
    profile: Dict,
    cluster: Dict,
    semantic_bridge: Optional[Dict],
) -> Dict:
    """Build the structured insight output."""
    
    feature_scores = session.get("feature_scores", {})
    deviation_level = session.get("deviation_level", "none")
    deviation_score = session.get("deviation_score", 0.0)
    
    # Determine probable intent
    probable_intent = determine_probable_intent(cluster)
    cluster_stability = determine_cluster_stability(cluster)
    
    # Suggested response
    use_bedrock = os.environ.get("USE_BEDROCK", "false").lower() == "true"
    if use_bedrock:
        suggested_response = generate_insight_with_bedrock(
            session, profile, cluster, probable_intent, semantic_bridge
        )
    else:
        suggested_response = get_suggested_response(probable_intent["key"])
    
    # Semantic alignment section
    semantic_alignment = None
    if semantic_bridge:
        semantic_alignment = {
            "word_detected": semantic_bridge.get("word_token"),
            "alignment_confidence": round(float(semantic_bridge.get("semantic_confidence_score", 0)), 3),
            "co_occurrence_count": semantic_bridge.get("co_occurrence_count", 0),
        }
    
    insight = {
        "observed_pattern": {
            "emotional_intensity": round(feature_scores.get("emotional_intensity", 0), 3),
            "rhythm": round(feature_scores.get("rhythm", 0), 3),
            "repetition": round(feature_scores.get("repetition", 0), 3),
            "expressive_flow": round(feature_scores.get("expressive_flow", 0), 3),
            "deviation": deviation_level,
            "deviation_score": round(deviation_score, 3),
            "cluster_stability": cluster_stability,
            "cluster_frequency": cluster.get("frequency_count", 1),
        },
        "probable_intent": probable_intent,
        "semantic_alignment": semantic_alignment,
        "suggested_response": suggested_response,
        "readiness_score": round(profile.get("readiness_score", 0.5), 3),
        "language_maturity_level": profile.get("language_maturity_level", "pre-linguistic"),
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    
    return insight


def save_insight_to_session(session_id: str, insight: Dict):
    """Save generated insight to session record."""
    session_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET insight = :ins, insight_generated_at = :iga",
        ExpressionAttributeValues={
            ":ins": _float_to_decimal(insight),
            ":iga": datetime.now(timezone.utc).isoformat(),
        }
    )


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Insight Generator Lambda handler.
    
    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "cluster_id": str
        }
    """
    logger.info(f"Insight generator started for session {event.get('session_id')}")
    
    child_id = event["child_id"]
    session_id = event["session_id"]
    cluster_id = event["cluster_id"]
    
    # 1. Fetch all required data
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")
    
    profile = get_child_profile(child_id)
    if not profile:
        raise ValueError(f"Child profile {child_id} not found")
    
    cluster = get_cluster(cluster_id)
    if not cluster:
        raise ValueError(f"Cluster {cluster_id} not found")
    
    semantic_bridge = get_semantic_bridge(cluster_id)
    
    # 2. Build insight
    insight = build_insight(session, profile, cluster, semantic_bridge)
    
    # 3. Save insight to session
    save_insight_to_session(session_id, insight)
    
    logger.info(f"Insight generated for session {session_id}: intent={insight['probable_intent']['label']}")
    
    return {
        "status": "insight_generated",
        "session_id": session_id,
        "insight": insight,
    }
