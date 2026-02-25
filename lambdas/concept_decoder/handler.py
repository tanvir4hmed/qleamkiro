"""
Qleam — Concept Decoder Lambda (Phase 6, Layer 8)

Per-session concept graph lookup, proto-word crystallization check,
and unknown cluster detection.

Trigger: Step Function invocation after DevelopmentalTracker
Input:  { child_id, session_id, cluster_id }
Output: { status, concept_decode }
"""
import logging
import os
import sys
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from concept_graph import get_concepts
from constants import (
    CONCEPT_GRAPH_TABLE,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
)
from proto_word import check_proto_word_criteria

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _decimal_to_float(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_decimal_to_float(i) for i in val]
    return val


def _float_to_decimal(val: Any) -> Any:
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, dict):
        return {k: _float_to_decimal(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_float_to_decimal(i) for i in val]
    return val


def _get_cluster(cluster_id: str) -> Optional[Dict]:
    resp = cluster_table.get_item(Key={"cluster_id": cluster_id})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def _get_dominant_word_token(cluster_id: str) -> Optional[str]:
    """
    Resolve dominant baby-sound label from semantic bridges for this cluster.

    Priority:
      1) highest semantic_confidence_score
      2) highest co_occurrence_count
    """
    if not cluster_id:
        return None
    try:
        resp = semantic_bridge_table.query(
            IndexName="cluster_id-index",
            KeyConditionExpression=Key("cluster_id").eq(cluster_id),
        )
        items = [_decimal_to_float(i) for i in resp.get("Items", [])]
        if not items:
            return None
        items.sort(
            key=lambda b: (
                -float(b.get("semantic_confidence_score", 0.0)),
                -int(b.get("co_occurrence_count", 0)),
            )
        )
        token = str(items[0].get("word_token", "") or "").strip().lower()
        return token or None
    except Exception as e:
        logger.warning(f"Failed to resolve dominant word token for cluster {cluster_id}: {e}")
        return None


def lambda_handler(event: dict, context) -> dict:
    """
    Concept Decoder handler.

    Args:
        event: { "child_id": str, "session_id": str, "cluster_id": str }
    """
    child_id = event.get("child_id", "")
    session_id = event.get("session_id", "")
    cluster_id = event.get("cluster_id", "")

    if not child_id or not session_id:
        logger.warning("ConceptDecoder called with missing child_id or session_id")
        return {"status": "skipped", "reason": "missing_fields"}

    logger.info(f"ConceptDecoder: child={child_id} session={session_id} cluster={cluster_id}")

    # --- Load cluster ---
    cluster = _get_cluster(cluster_id) if cluster_id else None
    if not cluster:
        logger.warning(f"Cluster {cluster_id} not found — skipping proto-word check")
        proto_word_result = {"criteria": {}, "met_count": 0, "proto_word_status": "NONE"}
    else:
        proto_word_result = check_proto_word_criteria(cluster)

    # --- Load concept graph ---
    concepts = get_concepts(child_id, concept_graph_table, limit=50)

    # --- Filter concepts linked to this cluster_id ---
    cluster_concepts = [
        c for c in concepts
        if cluster_id and cluster_id in c.get("acoustic_clusters", [])
    ]

    # --- Unknown cluster detection ---
    freq = int(cluster.get("frequency_count", 0)) if cluster else 0
    is_unknown_cluster = freq < 5 and len(cluster_concepts) == 0

    # --- Compute concept confidence scores ---
    # Only include concepts that a parent has confirmed at least once (confirmation_count > 0).
    # Universal pre-populated concepts start at confirmation_count=0 and confidence=0.5,
    # which would give every new child identical fake 25% scores for all categories.
    reinforcement_weight = float(cluster.get("reinforcement_weight", 0.5)) if cluster else 0.5

    scored: List[Dict] = []
    for c in concepts:
        confirmation_count = int(c.get("confirmation_count", 0))
        if confirmation_count == 0:
            continue  # Skip universal concepts with no parent evidence yet
        base_confidence = float(c.get("confidence", 0.5))
        score = round(base_confidence * reinforcement_weight, 4)
        scored.append({
            "label": c.get("label", ""),
            "confidence": score,
            "evidence_count": confirmation_count,
            "category": c.get("category", "personal"),
        })

    # Sort by confidence descending, take top 5
    scored.sort(key=lambda x: x["confidence"], reverse=True)
    top_concepts = scored[:5]

    # --- Build concept_decode ---
    unknown_flag_message = None
    if is_unknown_cluster:
        unknown_flag_message = "This sound pattern is new — keep noting what you observe to help me learn"

    concept_decode = {
        "top_concepts": top_concepts,
        "is_unknown_cluster": is_unknown_cluster,
        "proto_word_status": proto_word_result["proto_word_status"],
        "proto_word_criteria_met": proto_word_result["met_count"],
        "unknown_flag_message": unknown_flag_message,
    }

    # --- Persist signal metadata to cluster (for LanguagePage/API consumers) ---
    # This keeps cluster-level status in sync with per-session concept_decode.
    dominant_word_token = _get_dominant_word_token(cluster_id)
    fallback_label = top_concepts[0]["label"] if top_concepts else None
    try:
        update_expr = (
            "SET proto_word_status = :pws, "
            "proto_word_criteria_met = :pwm"
        )
        expr_vals: Dict[str, Any] = {
            ":pws": proto_word_result["proto_word_status"],
            ":pwm": _float_to_decimal(proto_word_result["met_count"]),
        }

        if dominant_word_token:
            update_expr += ", dominant_word_token = :dwt"
            expr_vals[":dwt"] = dominant_word_token
        elif fallback_label:
            # Non-breaking fallback when no explicit word_token exists yet.
            update_expr += ", label = :lbl"
            expr_vals[":lbl"] = fallback_label

        cluster_table.update_item(
            Key={"cluster_id": cluster_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals,
        )
    except Exception as e:
        logger.warning(f"Failed to persist concept decode metadata to cluster {cluster_id}: {e}")

    # --- Store on session ---
    try:
        session_table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET concept_decode = :cd",
            ExpressionAttributeValues={":cd": _float_to_decimal(concept_decode)},
        )
    except Exception as e:
        logger.warning(f"Failed to store concept_decode on session: {e}")

    logger.info(
        f"ConceptDecoder: proto_word={proto_word_result['proto_word_status']} "
        f"top_concepts={len(top_concepts)} unknown={is_unknown_cluster}"
    )
    return {
        "status": "ok",
        "child_id": child_id,
        "session_id": session_id,
        "concept_decode": concept_decode,
    }
