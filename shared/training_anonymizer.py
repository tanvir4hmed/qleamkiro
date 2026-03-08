"""
Qleam — Training Data Anonymizer (Phase 3)
Handles quality gates and anonymization for parent-confirmed training data.

When a parent confirms/corrects a cry emotion prediction:
1. Quality gates filter out bad data
2. PII is stripped (session_id, child_id, etc.)
3. Confirmed label is written to the TrainingFeatures record
4. Record becomes part of the permanent anonymized training dataset

The Phase 2 feature_extraction Lambda already stores HuBERT embeddings
in S3 and metadata in DynamoDB (TrainingFeatures table). This module
upgrades those records from "raw session data" to "confirmed training data"
by adding the parent label and removing PII.
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Quality gate thresholds
MIN_SNR_DB = 10.0
MIN_DURATION_S = 3.0
MIN_CONFIDENCE_FOR_CONFIRM = 0.4
DEDUP_WINDOW_MINUTES = 5

# Model weight blending thresholds
BLEND_THRESHOLDS = [
    (0, 29, 1.0, 0.0),     # 0-29 samples: 100% public, 0% ours
    (30, 99, 0.7, 0.3),    # 30-99: 70% public, 30% ours
    (100, 299, 0.4, 0.6),  # 100-299: 40% public, 60% ours
    (300, None, 0.15, 0.85),  # 300+: 15% public, 85% ours
]


def get_blend_weights(confirmed_sample_count: int) -> Dict[str, float]:
    """Get model weight blending ratios based on confirmed sample count."""
    for min_n, max_n, public_w, our_w in BLEND_THRESHOLDS:
        if max_n is None or confirmed_sample_count <= max_n:
            if confirmed_sample_count >= min_n:
                return {"public_weight": public_w, "our_weight": our_w}
    return {"public_weight": 0.15, "our_weight": 0.85}


def apply_quality_gates(
    session: Dict,
    confirmed_emotion: str,
    was_correct: bool,
    training_features_table,
    recent_feature_ids: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Apply quality gates to determine if feedback should enter training data.

    Returns:
        {
            "accepted": bool,
            "rejection_reason": str or None,
            "feature_id": str or None,  # TrainingFeatures record to upgrade
        }
    """
    session_id = session.get("session_id", "")

    # Gate 0: Must have a TrainingFeatures record (HuBERT embeddings exist)
    feature_record = _find_training_feature(session_id, training_features_table)
    if not feature_record:
        return {"accepted": False, "rejection_reason": "no_embeddings",
                "feature_id": None}

    feature_id = feature_record.get("feature_id", "")

    # Gate 1: Feedback quality — must be explicit confirm or correct
    if not confirmed_emotion or confirmed_emotion.lower() in ("skip", "not_sure", "unknown"):
        return {"accepted": False, "rejection_reason": "feedback_skip",
                "feature_id": feature_id}

    # Gate 2: Audio quality
    quality_gate = session.get("quality_gate", {})
    snr = float(quality_gate.get("snr_db", 0) or 0)
    duration = float(session.get("duration_seconds", 0) or 0)
    sound_type = session.get("sound_type", "")

    if snr < MIN_SNR_DB:
        return {"accepted": False, "rejection_reason": f"low_snr:{snr:.1f}",
                "feature_id": feature_id}
    if duration < MIN_DURATION_S:
        return {"accepted": False, "rejection_reason": f"short_duration:{duration:.1f}",
                "feature_id": feature_id}
    if sound_type not in ("cry", "mixed"):
        return {"accepted": False, "rejection_reason": f"wrong_sound_type:{sound_type}",
                "feature_id": feature_id}

    # Gate 3: Confidence check
    classifier_result = session.get("classifier_result") or {}
    model_confidence = float(classifier_result.get("confidence", 0) or 0)

    if was_correct and model_confidence < MIN_CONFIDENCE_FOR_CONFIRM:
        # Parent confirmed a low-confidence prediction — might be lucky guess
        return {"accepted": False,
                "rejection_reason": f"low_confidence_confirm:{model_confidence:.2f}",
                "feature_id": feature_id}
    # Corrections always accepted (the model was wrong — learn from it)

    # Gate 4: Deduplication (same session can't be confirmed twice)
    if feature_record.get("confirmed_emotion"):
        return {"accepted": False, "rejection_reason": "already_confirmed",
                "feature_id": feature_id}

    return {"accepted": True, "rejection_reason": None, "feature_id": feature_id}


def anonymize_and_confirm(
    feature_id: str,
    confirmed_emotion: str,
    was_correct: bool,
    session: Dict,
    training_features_table,
) -> Dict[str, Any]:
    """
    Anonymize and upgrade a TrainingFeatures record to confirmed training data.

    Strips PII (session_id) and adds the parent-confirmed label.
    The HuBERT embeddings in S3 are already anonymous (stored by feature_id).

    Returns:
        {"status": "confirmed", "feature_id": str, "confirmation_source": str}
    """
    now = datetime.now(timezone.utc).isoformat()
    confirmation_source = "parent_confirm" if was_correct else "parent_correct"

    classifier_result = session.get("classifier_result") or {}
    quality_gate = session.get("quality_gate", {})

    # Update the record: add confirmed label, strip session_id
    update_expr = (
        "SET confirmed_emotion = :emotion, "
        "confirmation_source = :source, "
        "confirmed_at = :ts, "
        "model_confidence_at_time = :conf, "
        "audio_quality_snr = :snr, "
        "is_confirmed = :confirmed "
        "REMOVE session_id"
    )
    expr_values = {
        ":emotion": confirmed_emotion,
        ":source": confirmation_source,
        ":ts": now,
        ":conf": _to_decimal(classifier_result.get("confidence", 0)),
        ":snr": _to_decimal(quality_gate.get("snr_db", 0)),
        ":confirmed": True,
    }

    try:
        training_features_table.update_item(
            Key={"feature_id": feature_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_values,
        )
        logger.info(
            f"Training data confirmed: {feature_id} "
            f"emotion={confirmed_emotion} source={confirmation_source}"
        )
        return {
            "status": "confirmed",
            "feature_id": feature_id,
            "confirmation_source": confirmation_source,
        }
    except Exception as e:
        logger.error(f"Failed to confirm training data: {e}")
        return {"status": "error", "feature_id": feature_id, "error": str(e)}


def count_confirmed_samples(training_features_table) -> int:
    """Count total confirmed training samples."""
    try:
        from boto3.dynamodb.conditions import Attr
        response = training_features_table.scan(
            FilterExpression=Attr("is_confirmed").eq(True),
            Select="COUNT",
        )
        return response.get("Count", 0)
    except Exception as e:
        logger.warning(f"Failed to count confirmed samples: {e}")
        return 0


def _find_training_feature(session_id: str, training_features_table) -> Optional[Dict]:
    """Find the TrainingFeatures record for a session (by session_id GSI or scan)."""
    if training_features_table is None:
        return None

    try:
        from boto3.dynamodb.conditions import Attr
        # session_id is stored during Phase 2 embedding extraction
        response = training_features_table.scan(
            FilterExpression=Attr("session_id").eq(session_id),
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            return _decimal_to_float(items[0])
    except Exception as e:
        logger.warning(f"Failed to find training feature for session {session_id}: {e}")
    return None


def _to_decimal(value) -> Decimal:
    """Convert numeric value to Decimal for DynamoDB."""
    import math
    if value is None:
        return Decimal("0")
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return Decimal("0")
        return Decimal(str(round(f, 6)))
    except (TypeError, ValueError):
        return Decimal("0")


def _decimal_to_float(obj):
    """Recursively convert Decimal to float."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj
