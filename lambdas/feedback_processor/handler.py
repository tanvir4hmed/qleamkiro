"""
Qleam — Feedback Processor Lambda
Stores parent feedback and triggers reinforcement engine.

Trigger: POST /session/{id}/feedback
Input:  API Gateway event with feedback body
Output: { status: "feedback_processed" }
"""
import json
import hashlib
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
from boto3.dynamodb.conditions import Key

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    FEEDBACK_TABLE,
    FL_DELTA_QUALITY_GATE,
    FL_FRS_QUALITY_GATE,
    FL_MIN_PARTICIPANTS,
    FL_RESEARCH_FLOOR,
    POPULATION_MODEL_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    MODEL_REGISTRY_TABLE,
    TRAINING_ACCEPT_ACOUSTIC_RELIABILITY_MIN,
    TRAINING_ACCEPT_DELTA_MIN,
    TRAINING_ACCEPT_FRS_MIN,
    TRAINING_ACCEPT_SCORE_MIN,
    TRAINING_ACCEPT_TOP_MARGIN_MIN,
    TRAINING_DATASET_MIN_SAMPLES,
    TRAINING_CANDIDATE_TABLE,
    TRAINING_MODEL_MAX_CANDIDATES_PER_STAGE,
    TRAINING_MODEL_MIN_ACCURACY,
    TRAINING_MODEL_MIN_LABEL_SUPPORT,
    TRAINING_MODEL_MIN_TRAIN_SAMPLES,
    TRAINING_MODEL_MIN_VAL_SAMPLES,
    TRAINING_MODEL_PROMOTION_MARGIN,
    TRAINING_MODEL_RETRAIN_EVERY_N,
)
from intent_taxonomy import canonical_intent_key, canonical_intent_keys, normalize_intent_distribution
from training_model import train_prototype_model

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
population_model_table = dynamodb.Table(POPULATION_MODEL_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)
lambda_client = boto3.client("lambda")

# All intent keys — must match evidence_model.py
_ALL_INTENTS = list(canonical_intent_keys(include_technical=False))

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
    canonical_intent: str = "",
    training_eligible: Optional[bool] = None,
    training_stage: str = "",
    training_weight: Optional[float] = None,
    training_acceptance_score: Optional[float] = None,
    training_candidate_eligible: Optional[bool] = None,
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
    if canonical_intent:
        feedback_item["canonical_intent"] = canonical_intent
    if training_eligible is not None:
        feedback_item["training_eligible"] = bool(training_eligible)
    if training_stage:
        feedback_item["training_stage"] = training_stage
    if training_weight is not None:
        feedback_item["training_weight"] = _float_to_decimal(training_weight)
    if training_acceptance_score is not None:
        feedback_item["training_acceptance_score"] = _float_to_decimal(training_acceptance_score)
    if training_candidate_eligible is not None:
        feedback_item["training_candidate_eligible"] = bool(training_candidate_eligible)

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


def _clamp01(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def compute_training_acceptance(
    session: Dict,
    training_stage: str,
    response_type: str,
    effectiveness: str,
    training_eligible: bool,
    delta_score: Optional[float],
    frs_after: Optional[float],
    fraud_signal_frs: str,
    efp_top_intent: str = "",
) -> Dict[str, Any]:
    """
    Strict acceptance gate for model-training candidates.

    This gate is intentionally stricter than FL population-prior eligibility.
    Parent feedback alone is never sufficient; model/session quality signals
    must also pass.
    """
    insight = session.get("insight") or {}
    probable = insight.get("probable_intent") or {}
    evidence = probable.get("evidence") or {}
    quality_gate = session.get("quality_gate") or {}
    speaker_gate = session.get("speaker_gate") or {}

    model_intent = str(probable.get("key") or efp_top_intent or "").strip().lower()
    quality_passed = bool(quality_gate.get("passed", True))
    speaker_status = str(speaker_gate.get("status") or "").upper().strip()
    speaker_pass = speaker_status == "BABY_PASS"
    agreement = bool(evidence.get("agreement", False))
    label_matches_model = bool(model_intent and response_type == model_intent)

    acoustic_reliability = _clamp01(
        insight.get("acoustic_reliability", evidence.get("acoustic_reliability", 0.0))
    )
    top_margin = max(0.0, float(evidence.get("top_margin", 0.0) or 0.0))
    margin_norm = _clamp01(top_margin / 0.20)
    delta_norm = _clamp01(delta_score if delta_score is not None else 0.0)
    frs_norm = _clamp01(frs_after if frs_after is not None else 0.0)
    agreement_norm = 1.0 if agreement else 0.0
    label_match_norm = 1.0 if label_matches_model else 0.0

    # Composite score used for candidate ranking/selection quality.
    acceptance_score = round(
        0.34 * delta_norm
        + 0.28 * frs_norm
        + 0.20 * acoustic_reliability
        + 0.10 * margin_norm
        + 0.05 * agreement_norm
        + 0.03 * label_match_norm,
        4,
    )

    hard_gates_pass = bool(
        training_eligible
        and response_type in _ALL_INTENTS
        and effectiveness == "helpful"
        and fraud_signal_frs == "NONE"
        and bool(training_stage)
        and delta_score is not None
        and frs_after is not None
        and float(delta_score) >= TRAINING_ACCEPT_DELTA_MIN
        and float(frs_after) >= TRAINING_ACCEPT_FRS_MIN
        and acoustic_reliability >= TRAINING_ACCEPT_ACOUSTIC_RELIABILITY_MIN
        and top_margin >= TRAINING_ACCEPT_TOP_MARGIN_MIN
        and agreement
        and label_matches_model
        and quality_passed
        and speaker_pass
    )
    candidate_eligible = hard_gates_pass and acceptance_score >= TRAINING_ACCEPT_SCORE_MIN

    return {
        "score": acceptance_score,
        "eligible": candidate_eligible,
        "signals": {
            "training_stage": training_stage,
            "response_type": response_type,
            "model_intent": model_intent,
            "label_matches_model": label_matches_model,
            "quality_passed": quality_passed,
            "speaker_status": speaker_status,
            "delta_score": round(float(delta_score or 0.0), 4),
            "frs_after": round(float(frs_after or 0.0), 4),
            "acoustic_reliability": round(acoustic_reliability, 4),
            "top_margin": round(top_margin, 4),
            "agreement": agreement,
            "hard_gates_pass": hard_gates_pass,
        },
    }


def save_training_candidate(
    session: Dict,
    training_stage: str,
    response_type: str,
    effectiveness: str,
    training_weight: Optional[float],
    acceptance: Dict[str, Any],
) -> Optional[str]:
    """
    Persist a de-identified training candidate from accepted feedback/session.

    Stored record intentionally excludes child/session IDs and raw audio paths.
    """
    if not acceptance.get("eligible"):
        return None

    feature_scores = session.get("feature_scores") or {}
    rich_features = session.get("rich_features") or {}
    if not feature_scores and not rich_features:
        return None

    now = datetime.now(timezone.utc).isoformat()
    candidate_id = str(uuid.uuid4())
    sample_weight = float(training_weight if training_weight is not None else acceptance.get("score", 0.0))
    sample_weight = round(max(0.05, min(1.0, sample_weight)), 4)

    signature_payload = json.dumps(
        {
            "stage": training_stage,
            "label": response_type,
            "feature_scores": feature_scores,
            "rich_features": rich_features,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    feature_signature = hashlib.sha256(signature_payload.encode("utf-8")).hexdigest()
    split_bucket = int(feature_signature[:8], 16) % 100
    if split_bucket < 80:
        split = "train"
    elif split_bucket < 90:
        split = "val"
    else:
        split = "test"

    item = {
        "candidate_id": candidate_id,
        "accepted_at": now,
        "developmental_stage": training_stage,
        "developmental_mode": str(session.get("developmental_mode") or ""),
        "accepted_label": response_type,
        "effectiveness": effectiveness,
        "sample_weight": sample_weight,
        "acceptance_score": float(acceptance.get("score", 0.0) or 0.0),
        "acceptance_signals": acceptance.get("signals") or {},
        "feature_scores": feature_scores,
        "rich_features": rich_features,
        "feature_signature": feature_signature,
        "dataset_split": split,
        "schema_version": 1,
        "source": "feedback_acceptance_v1",
    }

    training_candidate_table.put_item(Item=_float_to_decimal(item))
    logger.info(
        f"Saved training candidate {candidate_id} stage={training_stage} "
        f"label={response_type} score={acceptance.get('score', 0.0):.4f}"
    )
    return candidate_id


def _blend_with_research_floor(distribution: Dict[str, float]) -> Dict[str, float]:
    """Apply the research floor so online learning cannot fully override priors."""
    uniform = 1.0 / max(len(_ALL_INTENTS), 1)
    blended = {
        k: FL_RESEARCH_FLOOR * uniform + (1.0 - FL_RESEARCH_FLOOR) * float(distribution.get(k, uniform))
        for k in _ALL_INTENTS
    }
    return normalize_intent_distribution(blended, include_technical=False, fill_missing=True)


def _online_update_population_prior(stage: str, intent_key: str, sample_weight: float) -> None:
    """
    Incrementally update PopulationModel priors from high-trust feedback samples.
    """
    if not stage or not intent_key:
        return

    stage_key = stage.upper().strip()
    if sample_weight <= 0:
        return

    try:
        current = _decimal_to_float(
            population_model_table.get_item(Key={"stage": stage_key}).get("Item", {})
        )
        counts_raw = current.get("intent_counts") or {}
        counts = {k: float(counts_raw.get(k, 0.0) or 0.0) for k in _ALL_INTENTS}
        counts[intent_key] = counts.get(intent_key, 0.0) + float(sample_weight)

        total = sum(counts.values())
        if total <= 0:
            return

        raw_prior = {k: counts[k] / total for k in _ALL_INTENTS}
        population_prior = _blend_with_research_floor(raw_prior)
        n_participants = int(current.get("n_participants", 0) or 0) + 1
        is_reliable = n_participants >= FL_MIN_PARTICIPANTS
        now = datetime.now(timezone.utc).isoformat()

        record = dict(current) if isinstance(current, dict) else {}
        record.update(
            {
                "stage": stage_key,
                "intent_counts": counts,
                "population_prior": population_prior,
                "n_participants": n_participants,
                "is_reliable": is_reliable,
                "aggregated_at": now,
                "updated_by": "feedback_online_v1",
            }
        )
        population_model_table.put_item(Item=_float_to_decimal(record))
        logger.info(
            f"Online population prior updated: stage={stage_key} n={n_participants} "
            f"intent={intent_key} w={sample_weight:.3f}"
        )
    except Exception as e:
        logger.warning(f"Online population prior update skipped for stage={stage_key}: {e}")


def _online_update_training_dataset_profile(stage: str, intent_key: str, sample_weight: float) -> Dict[str, Any]:
    """
    Update stage-level accepted training-dataset profile in PopulationModel table.

    This profile is built only from strict training candidates (Phase 1 gate).
    It is later consumed by insight blending as a safe, bounded prior refinement.
    """
    if not stage or not intent_key:
        return {"dataset_n": 0, "dataset_is_reliable": False, "updated": False}
    stage_key = stage.upper().strip()
    if sample_weight <= 0:
        return {"dataset_n": 0, "dataset_is_reliable": False, "updated": False}

    try:
        current = _decimal_to_float(
            population_model_table.get_item(Key={"stage": stage_key}).get("Item", {})
        )
        counts_raw = current.get("dataset_intent_counts") or {}
        counts = {k: float(counts_raw.get(k, 0.0) or 0.0) for k in _ALL_INTENTS}
        counts[intent_key] = counts.get(intent_key, 0.0) + float(sample_weight)
        total = sum(counts.values())
        if total <= 0:
            return {"dataset_n": int(current.get("dataset_n", 0) or 0), "dataset_is_reliable": False, "updated": False}

        dataset_prior_raw = {k: counts[k] / total for k in _ALL_INTENTS}
        dataset_prior = normalize_intent_distribution(
            dataset_prior_raw, include_technical=False, fill_missing=True
        )

        dataset_n = int(current.get("dataset_n", 0) or 0) + 1
        dataset_is_reliable = dataset_n >= TRAINING_DATASET_MIN_SAMPLES
        now = datetime.now(timezone.utc).isoformat()

        record = dict(current) if isinstance(current, dict) else {}
        record.update(
            {
                "stage": stage_key,
                "dataset_intent_counts": counts,
                "dataset_prior": dataset_prior,
                "dataset_n": dataset_n,
                "dataset_is_reliable": dataset_is_reliable,
                "dataset_updated_at": now,
                "dataset_updated_by": "feedback_acceptance_v1",
            }
        )
        population_model_table.put_item(Item=_float_to_decimal(record))
        logger.info(
            f"Training dataset profile updated: stage={stage_key} n={dataset_n} "
            f"intent={intent_key} w={sample_weight:.3f}"
        )
        return {"dataset_n": dataset_n, "dataset_is_reliable": dataset_is_reliable, "updated": True}
    except Exception as e:
        logger.warning(f"Training dataset profile update skipped for stage={stage_key}: {e}")
        return {"dataset_n": 0, "dataset_is_reliable": False, "updated": False}


def _query_stage_training_candidates(stage_key: str, limit: int) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    kwargs: Dict[str, Any] = {
        "IndexName": "developmental_stage-accepted_at-index",
        "KeyConditionExpression": Key("developmental_stage").eq(stage_key),
    }
    response = training_candidate_table.query(**kwargs)
    items.extend(response.get("Items", []))
    while "LastEvaluatedKey" in response and len(items) < limit:
        response = training_candidate_table.query(
            ExclusiveStartKey=response["LastEvaluatedKey"],
            **kwargs,
        )
        items.extend(response.get("Items", []))
    return _decimal_to_float(items[:limit])


def _should_retrain_stage_model(current: Dict[str, Any], dataset_n: int) -> bool:
    if dataset_n < TRAINING_MODEL_MIN_TRAIN_SAMPLES:
        return False
    last_n = int(current.get("model_last_trained_n", 0) or 0)
    if int(current.get("model_version", 0) or 0) <= 0:
        return True
    return (dataset_n - last_n) >= max(1, TRAINING_MODEL_RETRAIN_EVERY_N)


def _retrain_and_promote_stage_model(stage: str, dataset_n: int) -> Dict[str, Any]:
    """
    Automatic retrain+promotion loop from accepted training candidates.
    No manual review/dashboard required.
    """
    stage_key = (stage or "").upper().strip()
    if not stage_key or dataset_n <= 0:
        return {"retrained": False, "promoted": False, "reason": "invalid_stage_or_dataset"}

    current = _decimal_to_float(
        population_model_table.get_item(Key={"stage": stage_key}).get("Item", {})
    )
    if not isinstance(current, dict):
        current = {"stage": stage_key}

    if not _should_retrain_stage_model(current, dataset_n):
        return {"retrained": False, "promoted": False, "reason": "retrain_threshold_not_met"}

    candidates = _query_stage_training_candidates(
        stage_key, max(TRAINING_MODEL_MIN_TRAIN_SAMPLES, TRAINING_MODEL_MAX_CANDIDATES_PER_STAGE)
    )
    if len(candidates) < TRAINING_MODEL_MIN_TRAIN_SAMPLES:
        return {"retrained": False, "promoted": False, "reason": "insufficient_candidates"}

    trained = train_prototype_model(
        candidates=candidates,
        min_train_samples=TRAINING_MODEL_MIN_TRAIN_SAMPLES,
        min_val_samples=TRAINING_MODEL_MIN_VAL_SAMPLES,
        min_label_support=TRAINING_MODEL_MIN_LABEL_SUPPORT,
        min_accuracy=TRAINING_MODEL_MIN_ACCURACY,
    )
    if not trained.get("ok"):
        current["model_last_train_status"] = f"failed:{trained.get('reason', 'unknown')}"
        current["model_last_trained_at"] = datetime.now(timezone.utc).isoformat()
        population_model_table.put_item(Item=_float_to_decimal(current))
        return {"retrained": False, "promoted": False, "reason": trained.get("reason", "train_failed")}

    model = trained.get("model") or {}
    reliability = float(model.get("reliability", 0.0) or 0.0)
    is_reliable = bool(trained.get("is_reliable", False))
    now = datetime.now(timezone.utc).isoformat()
    model_version = int(current.get("model_last_trained_version", 0) or 0) + 1
    model_id = str(uuid.uuid4())

    active_model_id = str(current.get("active_model_id") or "")
    active_reliability = float(current.get("active_model_reliability", 0.0) or 0.0)
    promote = bool(
        is_reliable
        and (
            not active_model_id
            or reliability >= (active_reliability + TRAINING_MODEL_PROMOTION_MARGIN)
        )
    )

    model_item = {
        "model_id": model_id,
        "developmental_stage": stage_key,
        "created_at": now,
        "model_version": model_version,
        "status": "ACTIVE" if promote else "CANDIDATE",
        "provider": "qleam_online_supervised_v1",
        "model_type": model.get("model_type", "prototype_v1"),
        "reliability": reliability,
        "training_samples": int(model.get("training_samples", 0) or 0),
        "validation_samples": int(model.get("validation_samples", 0) or 0),
        "test_samples": int(model.get("test_samples", 0) or 0),
        "metrics": model.get("metrics") or {},
        "artifact": model,
    }
    model_registry_table.put_item(Item=_float_to_decimal(model_item))

    record = dict(current)
    record["stage"] = stage_key
    record["model_last_trained_at"] = now
    record["model_last_trained_n"] = int(dataset_n)
    record["model_last_trained_version"] = int(model_version)
    record["model_last_train_status"] = "ok"
    record["model_last_reliability"] = reliability
    record["model_last_metrics"] = model.get("metrics") or {}

    if promote:
        if active_model_id:
            try:
                model_registry_table.update_item(
                    Key={"model_id": active_model_id},
                    UpdateExpression="SET #st = :retired, retired_at = :ts",
                    ExpressionAttributeNames={"#st": "status"},
                    ExpressionAttributeValues={":retired": "RETIRED", ":ts": now},
                )
            except Exception as e:
                logger.warning(f"Failed retiring active model {active_model_id}: {e}")

        record["model_version"] = int(model_version)
        record["active_model_id"] = model_id
        record["active_model_reliability"] = reliability
        record["active_model_metrics"] = model.get("metrics") or {}
        record["active_model_provider"] = "qleam_online_supervised_v1"
        record["active_model_updated_at"] = now
        record["active_model_training_samples"] = int(model.get("training_samples", 0) or 0)

    population_model_table.put_item(Item=_float_to_decimal(record))
    logger.info(
        f"Stage model retrained stage={stage_key} version={model_version} "
        f"reliability={reliability:.4f} promoted={promote}"
    )
    return {
        "retrained": True,
        "promoted": promote,
        "model_id": model_id,
        "model_version": model_version,
        "reliability": reliability,
    }


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
    raw_response_type = str(event.get("response_type", "") or "").strip()
    canonical_response_type = canonical_intent_key(raw_response_type, allow_technical=False)
    response_type = canonical_response_type or raw_response_type.lower().replace(" ", "_")
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
    efp_top_intent: str = ""

    raw_efp = session.get("efp")
    efp = (
        normalize_intent_distribution(raw_efp or {}, include_technical=False, fill_missing=True)
        if isinstance(raw_efp, dict) and raw_efp
        else {}
    )
    if efp and response_type and response_type in _ALL_INTENTS:
        try:
            scores = compute_delta_score(efp, response_type)
            alignment_score = scores["alignment_score"]
            delta_score = scores["delta_score"]
            efp_top_intent = str(scores.get("efp_top_intent") or "").strip().lower()
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

    training_stage = (developmental_stage or session.get("developmental_stage") or "").upper().strip()
    training_eligible = bool(
        response_type in _ALL_INTENTS
        and effectiveness == "helpful"
        and delta_score is not None
        and frs_after is not None
        and delta_score >= FL_DELTA_QUALITY_GATE
        and frs_after >= FL_FRS_QUALITY_GATE
        and fraud_signal_frs == "NONE"
    )
    training_weight: Optional[float] = None
    if training_eligible:
        training_weight = round(
            max(0.05, min(1.0, 0.65 * float(delta_score) + 0.35 * float(frs_after))),
            4,
        )
        _online_update_population_prior(training_stage, response_type, training_weight)

    acceptance = compute_training_acceptance(
        session=session,
        training_stage=training_stage,
        response_type=response_type,
        effectiveness=effectiveness,
        training_eligible=training_eligible,
        delta_score=delta_score,
        frs_after=frs_after,
        fraud_signal_frs=fraud_signal_frs,
        efp_top_intent=efp_top_intent,
    )
    training_acceptance_score = float(acceptance.get("score", 0.0) or 0.0)
    training_candidate_eligible = bool(acceptance.get("eligible"))
    training_candidate_id = None
    training_model_result: Dict[str, Any] = {
        "retrained": False,
        "promoted": False,
        "reason": "not_attempted",
    }
    if training_candidate_eligible:
        try:
            training_candidate_id = save_training_candidate(
                session=session,
                training_stage=training_stage,
                response_type=response_type,
                effectiveness=effectiveness,
                training_weight=training_weight,
                acceptance=acceptance,
            )
            training_candidate_eligible = training_candidate_id is not None
            if training_candidate_eligible:
                dataset_profile = _online_update_training_dataset_profile(
                    training_stage, response_type, training_weight or training_acceptance_score
                )
                try:
                    training_model_result = _retrain_and_promote_stage_model(
                        training_stage, int(dataset_profile.get("dataset_n", 0) or 0)
                    )
                except Exception as e:
                    logger.warning(f"Training model loop failed (non-fatal): {e}")
                    training_model_result = {
                        "retrained": False,
                        "promoted": False,
                        "reason": "model_loop_failed",
                    }
        except Exception as e:
            logger.warning(f"Training candidate save failed (non-fatal): {e}")
            training_candidate_eligible = False
            training_model_result = {
                "retrained": False,
                "promoted": False,
                "reason": "candidate_save_failed",
            }

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
        canonical_intent=response_type if response_type in _ALL_INTENTS else "",
        training_eligible=training_eligible,
        training_stage=training_stage,
        training_weight=training_weight,
        training_acceptance_score=training_acceptance_score,
        training_candidate_eligible=training_candidate_eligible,
    )

    # 4. Trigger reinforcement engine (async) if cluster exists
    if cluster_id:
        reinforcement_payload = {
            "child_id": child_id,
            "session_id": session_id,
            "cluster_id": cluster_id,
            "response_type": response_type if response_type in _ALL_INTENTS else raw_response_type,
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
        "training_eligible": training_eligible,
        "training_stage": training_stage or None,
        "training_acceptance_score": training_acceptance_score,
        "training_candidate_eligible": training_candidate_eligible,
        "training_candidate_written": training_candidate_id is not None,
        "training_model_retrained": bool(training_model_result.get("retrained", False)),
        "training_model_promoted": bool(training_model_result.get("promoted", False)),
        "training_model_reliability": training_model_result.get("reliability"),
        "training_model_reason": training_model_result.get("reason"),
        "fraud_signals": detected_signals if detected_signals else None,
    }
