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
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

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

# ---------------------------------------------------------------------------
# Fraud-detection thresholds
# ---------------------------------------------------------------------------
_MISCLICK_THRESHOLD_MS = 3000        # < 3 s since insight displayed → likely misclick
_UNIFORM_PATTERN_WINDOW = 10         # sliding window of last N response_type submissions
_UNIFORM_PATTERN_THRESHOLD = 0.80    # ≥80 % same response type across window → suspicious
_ADVERSARIAL_FRS_THRESHOLD = 0.30    # FRS already this low → fast re-assessment mode
_ADVERSARIAL_CRS_THRESHOLD = 0.30    # CRS already this low → fast re-assessment mode

# Dynamic EMA α values — FRS
_ALPHA_FRS_NORMAL = 0.15        # Standard EMA update
_ALPHA_FRS_MISCLICK = 0.00      # Discard — likely accidental tap
_ALPHA_FRS_UNIFORM = 0.05       # Slow update — suspicious repetition pattern
_ALPHA_FRS_ADVERSARIAL = 0.45   # Fast re-assessment — trust critically low

# Dynamic EMA α values — CRS
_ALPHA_CRS_NORMAL = 0.10
_ALPHA_CRS_MISCLICK = 0.00
_ALPHA_CRS_ADVERSARIAL = 0.40


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


def _detect_frs_fraud(
    session: Dict,
    profile: Dict,
    response_type: str,
    submitted_at: datetime,
) -> Tuple[float, str, List[str]]:
    """
    Evaluate fraud signals for an FRS update.

    Signal hierarchy (first match wins):
        MISCLICK_SUSPECTED  — feedback submitted < 3 s after insight was displayed
        UNIFORM_PATTERN     — ≥80 % of last 10 responses are the same response_type
        ADVERSARIAL         — current FRS already below 0.30 (trust critically low)
        NONE                — normal submission

    Returns: (alpha, fraud_signal, updated_recent_response_types)
    """
    recent: List[str] = list(profile.get("recent_response_types") or [])

    # --- MISCLICK check ---
    insight_ts_str = session.get("insight_generated_at")
    if insight_ts_str:
        try:
            insight_ts = datetime.fromisoformat(insight_ts_str.replace("Z", "+00:00"))
            elapsed_ms = (submitted_at - insight_ts).total_seconds() * 1000
            if elapsed_ms < _MISCLICK_THRESHOLD_MS:
                logger.debug(f"FRS fraud: MISCLICK_SUSPECTED (elapsed={elapsed_ms:.0f}ms)")
                # Do NOT append to window — discard this tick entirely
                return _ALPHA_FRS_MISCLICK, "MISCLICK_SUSPECTED", recent
        except Exception:
            pass

    # --- Update sliding window (only for non-misclick submissions) ---
    if response_type:
        recent.append(response_type)
        if len(recent) > _UNIFORM_PATTERN_WINDOW:
            recent = recent[-_UNIFORM_PATTERN_WINDOW:]

    # --- UNIFORM_PATTERN check ---
    if len(recent) >= _UNIFORM_PATTERN_WINDOW:
        counts = Counter(recent)
        top_ratio = counts.most_common(1)[0][1] / len(recent)
        if top_ratio >= _UNIFORM_PATTERN_THRESHOLD:
            logger.debug(f"FRS fraud: UNIFORM_PATTERN (top_ratio={top_ratio:.2f})")
            return _ALPHA_FRS_UNIFORM, "UNIFORM_PATTERN", recent

    # --- ADVERSARIAL check ---
    current_frs = float(profile.get("parent_trust_score") or 0.5)
    if current_frs < _ADVERSARIAL_FRS_THRESHOLD:
        logger.debug(f"FRS fraud: ADVERSARIAL (frs={current_frs:.4f})")
        return _ALPHA_FRS_ADVERSARIAL, "ADVERSARIAL", recent

    return _ALPHA_FRS_NORMAL, "NONE", recent


def _detect_crs_fraud(
    session: Dict,
    profile: Dict,
    submitted_at: datetime,
) -> Tuple[float, str]:
    """
    Evaluate fraud signals for a CRS update.

    Signals:
        MISCLICK_SUSPECTED  — context submitted < 3 s after insight displayed
        ADVERSARIAL         — current CRS below 0.30 (context consistently unhelpful)
        NONE                — normal

    Returns: (alpha, fraud_signal)
    """
    # --- MISCLICK check ---
    insight_ts_str = session.get("insight_generated_at")
    if insight_ts_str:
        try:
            insight_ts = datetime.fromisoformat(insight_ts_str.replace("Z", "+00:00"))
            elapsed_ms = (submitted_at - insight_ts).total_seconds() * 1000
            if elapsed_ms < _MISCLICK_THRESHOLD_MS:
                return _ALPHA_CRS_MISCLICK, "MISCLICK_SUSPECTED"
        except Exception:
            pass

    # --- ADVERSARIAL check ---
    current_crs = float(profile.get("context_reliability") or 0.8)
    if current_crs < _ADVERSARIAL_CRS_THRESHOLD:
        return _ALPHA_CRS_ADVERSARIAL, "ADVERSARIAL"

    return _ALPHA_CRS_NORMAL, "NONE"


def update_parent_trust_score(
    child_id: str,
    alignment_score: float,
    session: Dict,
    response_type: str,
) -> Tuple[float, float, str]:
    """
    Update FRS using a dynamic EMA α selected by fraud signal detection.

    FRS(t) = α × alignment_score + (1 - α) × FRS(t-1)

    α is chosen as:
        MISCLICK_SUSPECTED  → 0.00  (discard — accidental tap, no update)
        UNIFORM_PATTERN     → 0.05  (slow decay — suspicious repetition)
        ADVERSARIAL         → 0.45  (fast re-assessment — critically low trust)
        NONE                → 0.15  (standard EMA)

    Also maintains a sliding `recent_response_types` window on the child profile
    for pattern detection across sessions.

    Returns: (old_frs, new_frs, fraud_signal)
    """
    now = datetime.now(timezone.utc)
    resp = child_profile_table.get_item(Key={"child_id": child_id})
    profile = _decimal_to_float(resp.get("Item", {}))
    old_frs = float(profile.get("parent_trust_score") or 0.5)

    alpha, fraud_signal, updated_recent = _detect_frs_fraud(session, profile, response_type, now)

    new_frs = round(max(0.1, min(1.0, alpha * alignment_score + (1.0 - alpha) * old_frs)), 4)

    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression="SET parent_trust_score = :frs, recent_response_types = :rrt",
        ExpressionAttributeValues={
            ":frs": _float_to_decimal(new_frs),
            ":rrt": updated_recent,
        },
    )
    logger.info(
        f"FRS updated child={child_id}: {old_frs:.4f} → {new_frs:.4f} "
        f"α={alpha} signal={fraud_signal}"
    )
    return old_frs, new_frs, fraud_signal


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
    fraud_signals: Optional[Dict] = None,
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
    if fraud_signals:
        feedback_item["fraud_signals"] = fraud_signals

    feedback_table.put_item(Item=feedback_item)
    logger.info(f"Saved feedback {feedback_id} alignment={alignment_score} frs={frs_before}→{frs_after}")


def update_context_reliability(child_id: str, alignment_score: float, session: Dict) -> str:
    """
    Update CRS using a dynamic EMA α selected by fraud signal detection.
    Only called when the session had parent-provided context data.

    CRS tracks how well context inputs (feeding time, health state, etc.)
    have correlated with correct predictions.  Lower CRS → context weight is
    scaled down in compute_research_priors.

    CRS(t) = α × alignment_score + (1 - α) × CRS(t-1)

    α is chosen as:
        MISCLICK_SUSPECTED  → 0.00  (discard)
        ADVERSARIAL         → 0.40  (fast re-assessment — context consistently wrong)
        NONE                → 0.10  (standard EMA)

    Returns the fraud_signal detected.
    """
    now = datetime.now(timezone.utc)
    resp = child_profile_table.get_item(Key={"child_id": child_id})
    profile = _decimal_to_float(resp.get("Item", {}))
    old_crs = float(profile.get("context_reliability") or 0.8)

    alpha, fraud_signal = _detect_crs_fraud(session, profile, now)

    new_crs = round(max(0.2, min(1.0, alpha * alignment_score + (1.0 - alpha) * old_crs)), 4)

    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression="SET context_reliability = :crs",
        ExpressionAttributeValues={":crs": _float_to_decimal(new_crs)},
    )
    logger.info(
        f"CRS updated child={child_id}: {old_crs:.4f} → {new_crs:.4f} "
        f"α={alpha} signal={fraud_signal}"
    )
    return fraud_signal


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

    # 2. Phase 4: compute delta score + update FRS/CRS if EFP exists
    alignment_score: Optional[float] = None
    delta_score: Optional[float] = None
    frs_before: Optional[float] = None
    frs_after: Optional[float] = None
    fraud_signal_frs: str = "NONE"
    fraud_signal_crs: str = "NONE"

    efp = session.get("efp")
    if efp and response_type and response_type in _ALL_INTENTS:
        try:
            scores = compute_delta_score(efp, response_type)
            alignment_score = scores["alignment_score"]
            delta_score = scores["delta_score"]
            frs_before, frs_after, fraud_signal_frs = update_parent_trust_score(
                child_id, alignment_score, session, response_type
            )
            logger.info(
                f"Delta scoring: session={session_id} response={response_type} "
                f"efp_top={scores['efp_top_intent']} alignment={alignment_score:.3f} "
                f"delta={delta_score:.3f} frs_signal={fraud_signal_frs}"
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
                fraud_signal_crs = update_context_reliability(child_id, alignment_score, session)
            except Exception as e:
                logger.warning(f"Context reliability update failed (non-fatal): {e}")

    # Build fraud_signals summary (only persisted when a signal was detected)
    detected_signals: Dict = {}
    if fraud_signal_frs != "NONE":
        detected_signals["frs"] = fraud_signal_frs
    if fraud_signal_crs != "NONE":
        detected_signals["crs"] = fraud_signal_crs

    # 3. Save feedback record (with scoring data and fraud signals if present)
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
        fraud_signals=detected_signals if detected_signals else None,
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
        "fraud_signals": detected_signals if detected_signals else None,
    }
