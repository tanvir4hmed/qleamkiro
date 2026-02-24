"""
Qleam — Feedback Processor Lambda
Stores parent feedback and triggers reinforcement engine.

Trigger: POST /session/{id}/feedback
Input:  API Gateway event with feedback body
Output: { status: "feedback_processed" }
"""
import json
import logging
import math
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import CHILD_PROFILE_TABLE, FEEDBACK_TABLE, SESSION_TABLE, SOUND_CLUSTER_TABLE

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
lambda_client = boto3.client("lambda")

# All intent keys — must match evidence_model.py
_ALL_INTENTS = ["hunger", "discomfort", "connection", "fatigue", "overstimulation", "exploration"]


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


def get_session(session_id: str) -> Dict:
    response = session_table.get_item(Key={"session_id": session_id})
    if "Item" not in response:
        raise ValueError(f"Session {session_id} not found")
    return _decimal_to_float(response["Item"])


def compute_delta_score(efp: Dict[str, float], response_type: str) -> Dict[str, float]:
    """
    Compute how well the model's prediction (EFP) aligned with the parent's response.

    EFP  = Expected Feedback Profile — the blended intent distribution generated
           by the evidence model before the parent responded.
    actual = one-hot distribution derived from parent's response_type.

    Returns a dict with:
        alignment_score  — composite score in [0, 1] (higher = model was more correct)
        delta_score      — same as alignment_score (explicit Phase 4 name)
        rms_score        — 1 - RMS deviation (higher = closer match)
        eps_score        — entropy profile similarity (higher = model was appropriately confident)
        efp_top_intent   — which intent the model predicted most strongly
    """
    n = len(_ALL_INTENTS)
    actual = {intent: (1.0 if intent == response_type else 0.0) for intent in _ALL_INTENTS}

    # --- RMS score: 1 - RMS deviation (higher = more aligned) ---
    rms_dev = math.sqrt(
        sum((efp.get(i, 0.0) - actual[i]) ** 2 for i in _ALL_INTENTS) / n
    )
    rms_score = max(0.0, 1.0 - rms_dev)

    # --- EPS: entropy profile similarity ---
    # Shannon entropy of EFP vs actual (one-hot has 0 entropy)
    efp_entropy = -sum(
        (efp.get(i, 0.0)) * math.log(efp.get(i, 0.0) + 1e-12)
        for i in _ALL_INTENTS
        if efp.get(i, 0.0) > 0
    )
    max_ent = math.log(n) if n > 1 else 1.0
    eps_score = max(0.0, 1.0 - efp_entropy / max_ent)

    delta_score = 0.60 * rms_score + 0.40 * eps_score
    efp_top = max(efp, key=efp.get) if efp else ""

    return {
        "alignment_score": round(delta_score, 4),
        "delta_score": round(delta_score, 4),
        "rms_score": round(rms_score, 4),
        "eps_score": round(eps_score, 4),
        "efp_top_intent": efp_top,
    }


def update_parent_trust_score(child_id: str, alignment_score: float) -> Tuple[float, float]:
    """
    Update the parent's Feedback Reliability Score (FRS) using EMA (α=0.15).

    FRS(t) = 0.15 × alignment_score + 0.85 × FRS(t-1)

    Returns: (old_frs, new_frs)
    """
    response = child_profile_table.get_item(Key={"child_id": child_id})
    profile = _decimal_to_float(response.get("Item", {}))
    old_frs = float(profile.get("parent_trust_score") or 0.5)

    new_frs = round(max(0.1, min(1.0, 0.15 * alignment_score + 0.85 * old_frs)), 4)

    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression="SET parent_trust_score = :frs",
        ExpressionAttributeValues={":frs": _float_to_decimal(new_frs)},
    )
    logger.info(f"FRS updated child={child_id}: {old_frs:.4f} → {new_frs:.4f}")
    return old_frs, new_frs


def save_feedback(
    feedback_id: str,
    session_id: str,
    child_id: str,
    cluster_id: str,
    response_type: str,
    effectiveness: str,
    word_token: str,
    notes: str = "",
    alignment_score: Optional[float] = None,
    delta_score: Optional[float] = None,
    frs_before: Optional[float] = None,
    frs_after: Optional[float] = None,
    developmental_stage: str = "",
    stage_version: int = 0,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    feedback_item: Dict[str, Any] = {
        "feedback_id": feedback_id,
        "session_id": session_id,
        "child_id": child_id,
        "cluster_id": cluster_id,
        "response_type": response_type,
        "effectiveness": effectiveness,
        "word_token": word_token,
        "created_at": now,
    }
    if notes:
        feedback_item["notes"] = notes
    if alignment_score is not None:
        feedback_item["alignment_score"] = _float_to_decimal(alignment_score)
    if delta_score is not None:
        feedback_item["delta_score"] = _float_to_decimal(delta_score)
    if frs_before is not None:
        feedback_item["frs_before"] = _float_to_decimal(frs_before)
    if frs_after is not None:
        feedback_item["frs_after"] = _float_to_decimal(frs_after)
    if developmental_stage:
        feedback_item["developmental_stage"] = developmental_stage
    if stage_version:
        feedback_item["stage_version"] = stage_version

    feedback_table.put_item(Item=feedback_item)
    logger.info(f"Saved feedback {feedback_id} alignment={alignment_score} frs={frs_before}→{frs_after}")


def update_context_reliability(child_id: str, alignment_score: float) -> None:
    """
    Update context reliability score (CRS) using EMA (α=0.10).
    Only called when the session actually had parent-provided context data.

    CRS tracks how well the parent's context inputs (feeding time, health state, etc.)
    have correlated with correct predictions over time.  Lower CRS → context adjustments
    are scaled down in compute_research_priors, preventing wrong context from skewing results.

    CRS(t) = 0.10 × alignment_score + 0.90 × CRS(t-1)
    """
    response = child_profile_table.get_item(Key={"child_id": child_id})
    profile = _decimal_to_float(response.get("Item", {}))
    old_crs = float(profile.get("context_reliability") or 0.8)

    new_crs = round(max(0.2, min(1.0, 0.10 * alignment_score + 0.90 * old_crs)), 4)

    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression="SET context_reliability = :crs",
        ExpressionAttributeValues={":crs": _float_to_decimal(new_crs)},
    )
    logger.info(f"Context reliability updated child={child_id}: {old_crs:.4f} → {new_crs:.4f}")


def invoke_reinforcement_engine(payload: Dict) -> None:
    """Asynchronously invoke the reinforcement engine Lambda."""
    reinforcement_fn = os.environ.get(
        "REINFORCEMENT_LAMBDA_NAME",
        f"qleam-{os.environ.get('ENVIRONMENT', 'dev')}-reinforcement-engine"
    )
    try:
        lambda_client.invoke(
            FunctionName=reinforcement_fn,
            InvocationType="Event",  # Async
            Payload=json.dumps(payload).encode(),
        )
        logger.info(f"Invoked reinforcement engine for cluster {payload.get('cluster_id')}")
    except Exception as e:
        logger.error(f"Failed to invoke reinforcement engine: {e}")
        # Don't fail the feedback save — reinforcement is best-effort


def invoke_nlp_processor(child_id: str, cluster_id: str, notes: str, session_id: str) -> None:
    """Asynchronously invoke the NLP processor Lambda to extract concepts from notes."""
    nlp_fn = os.environ.get(
        "NLP_PROCESSOR_LAMBDA_NAME",
        f"qleam-{os.environ.get('ENVIRONMENT', 'dev')}-nlp-processor"
    )
    try:
        lambda_client.invoke(
            FunctionName=nlp_fn,
            InvocationType="Event",  # Async — fire and forget
            Payload=json.dumps({
                "child_id": child_id,
                "cluster_id": cluster_id,
                "notes": notes,
                "session_id": session_id,
            }).encode(),
        )
        logger.info(f"Invoked NLP processor for child {child_id} (notes_len={len(notes)})")
    except Exception as e:
        logger.error(f"Failed to invoke NLP processor: {e}")
        # Don't fail feedback save — NLP is best-effort


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Feedback Processor Lambda handler.

    Args:
        event: {
            "session_id": str,
            "response_type": str,       # "feeding" | "connection" | "comfort" | etc.
            "effectiveness": str,        # "helpful" | "neutral" | "ineffective"
            "word_token": str (optional) # word parent confirmed
        }
    """
    logger.info(f"Feedback processor started for session {event.get('session_id')}")

    session_id = event["session_id"]
    response_type = event.get("response_type", "")
    effectiveness = event.get("effectiveness", "neutral")
    word_token = event.get("word_token", "")
    notes = str(event.get("notes", "") or "").strip()[:500]  # cap at 500 chars
    developmental_stage = str(event.get("developmental_stage", "") or "")
    stage_version = int(event.get("stage_version", 0) or 0)

    # Validate effectiveness
    valid_effectiveness = {"helpful", "neutral", "ineffective"}
    if effectiveness not in valid_effectiveness:
        effectiveness = "neutral"

    # 1. Get session to find child_id, cluster_id, and EFP
    session = get_session(session_id)
    child_id = session["child_id"]
    cluster_id = session.get("cluster_id")

    if not cluster_id:
        logger.warning(f"Session {session_id} has no cluster_id yet — feedback stored but reinforcement skipped")

    # 2. Phase 4: compute delta score + update parent trust score (FRS) if EFP exists
    alignment_score: Optional[float] = None
    delta_score: Optional[float] = None
    frs_before: Optional[float] = None
    frs_after: Optional[float] = None

    efp = session.get("efp")
    if efp and response_type and response_type in _ALL_INTENTS:
        try:
            scores = compute_delta_score(efp, response_type)
            alignment_score = scores["alignment_score"]
            delta_score = scores["delta_score"]
            frs_before, frs_after = update_parent_trust_score(child_id, alignment_score)
            logger.info(
                f"Delta scoring: session={session_id} response={response_type} "
                f"efp_top={scores['efp_top_intent']} alignment={alignment_score:.3f} "
                f"delta={delta_score:.3f}"
            )
        except Exception as e:
            logger.warning(f"Delta scoring failed (non-fatal): {e}")

    # Also update context reliability if this session had parent-provided context data
    if alignment_score is not None:
        session_context = session.get("session_context") or {}
        had_context = bool(
            session_context.get("feeding_minutes_ago") is not None
            or session_context.get("health_state")
            or session_context.get("environment")
        )
        if had_context:
            try:
                update_context_reliability(child_id, alignment_score)
            except Exception as e:
                logger.warning(f"Context reliability update failed (non-fatal): {e}")

    # 3. Save feedback record (with scoring data if available)
    feedback_id = str(uuid.uuid4())
    save_feedback(
        feedback_id=feedback_id,
        session_id=session_id,
        child_id=child_id,
        cluster_id=cluster_id or "",
        response_type=response_type,
        effectiveness=effectiveness,
        word_token=word_token,
        notes=notes,
        alignment_score=alignment_score,
        delta_score=delta_score,
        frs_before=frs_before,
        frs_after=frs_after,
        developmental_stage=developmental_stage,
        stage_version=stage_version,
    )

    # 4. Trigger reinforcement engine (async) if cluster exists
    if cluster_id:
        reinforcement_payload = {
            "child_id": child_id,
            "session_id": session_id,
            "cluster_id": cluster_id,
            "response_type": response_type,
            "effectiveness": effectiveness,
            "word_token": word_token if word_token else None,
        }
        invoke_reinforcement_engine(reinforcement_payload)

    # 5. Trigger NLP processor (async) if notes are non-empty and cluster exists
    if notes and cluster_id:
        invoke_nlp_processor(
            child_id=child_id,
            cluster_id=cluster_id,
            notes=notes,
            session_id=session_id,
        )

    return {
        "status": "feedback_processed",
        "feedback_id": feedback_id,
        "session_id": session_id,
        "reinforcement_triggered": cluster_id is not None,
        "delta_score": delta_score,
        "frs_updated": frs_after is not None,
    }
