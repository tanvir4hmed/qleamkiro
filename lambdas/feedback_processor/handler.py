"""
Qleam — Feedback Processor Lambda
Handles parent feedback for cry emotion training:

1. CRY EMOTION FEEDBACK
   - Parent confirms/corrects the detected emotion
   - Feeds into Phase 3 ML training pipeline (HuBERT embeddings)

2. GENERAL FEEDBACK
   - Free-form notes stored for backward compatibility

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
from typing import Any, Dict, Optional

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    FEEDBACK_TABLE,
    SESSION_TABLE,
    TRAINING_FEATURES_TABLE,
)
from training_anonymizer import apply_quality_gates, anonymize_and_confirm

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
training_features_table = dynamodb.Table(TRAINING_FEATURES_TABLE) if TRAINING_FEATURES_TABLE else None


def _float_to_decimal(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return obj
    if hasattr(obj, 'item'):
        try:
            obj = obj.item()
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return Decimal("0")
        return Decimal(str(obj))
    if isinstance(obj, bool):
        return Decimal("1") if obj else Decimal("0")
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Feedback Processor — handles cry emotion feedback.

    Expected body:
    {
        "session_id": str,
        "feedback_type": "cry_emotion" | "general",

        // For cry emotion feedback:
        "confirmed_emotion": str, // Parent confirms/corrects emotion
        "was_correct": bool,      // Was our detection correct?

        // General:
        "notes": str,             // Additional notes (optional)
    }
    """
    try:
        # Parse body
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body") or event

        session_id = body.get("session_id")
        feedback_type = str(body.get("feedback_type", "cry_emotion")).strip().lower()

        if not session_id:
            return _error_response(400, "session_id is required")

        # Get session data
        session = _get_session(session_id)
        if not session:
            return _error_response(404, f"Session {session_id} not found")

        child_id = session.get("child_id")
        if not child_id:
            return _error_response(400, "Session has no child_id")

        # Get child profile for age
        profile = _get_child_profile(child_id)
        age_days = _compute_age_days(profile.get("birth_date"))

        # Store feedback record
        feedback_id = f"fb_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        feedback_record = {
            "feedback_id": feedback_id,
            "session_id": session_id,
            "child_id": child_id,
            "feedback_type": feedback_type,
            "created_at": now,
        }

        result = {"feedback_id": feedback_id}

        # --- Route by feedback type ---
        if feedback_type == "cry_emotion":
            result.update(
                _process_cry_emotion_feedback(
                    body, session, child_id, session_id, age_days, feedback_record
                )
            )
        elif feedback_type == "general":
            # General feedback (backward compatibility)
            result.update(
                _process_general_feedback(body, feedback_record)
            )
        else:
            return _error_response(400, f"Unsupported feedback_type: {feedback_type}")

        # Save feedback record
        feedback_table.put_item(Item=_float_to_decimal(feedback_record))
        logger.info(f"Feedback processed: {feedback_id} type={feedback_type}")

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"status": "feedback_processed", **result}),
        }

    except Exception as e:
        logger.error(f"Feedback processing error: {e}", exc_info=True)
        return _error_response(500, str(e))


def _process_cry_emotion_feedback(
    body: Dict,
    session: Dict,
    child_id: str,
    session_id: str,
    age_days: Optional[int],
    feedback_record: Dict,
) -> Dict:
    """
    Process cry emotion feedback.
    Parent confirms or corrects the detected emotion.
    """
    confirmed_emotion = str(body.get("confirmed_emotion", "") or "").strip()
    if not confirmed_emotion:
        confirmed_emotions = body.get("confirmed_emotions") or []
        if isinstance(confirmed_emotions, list) and confirmed_emotions:
            confirmed_emotion = str(confirmed_emotions[0] or "").strip()
    was_correct = body.get("was_correct", True)

    if not confirmed_emotion:
        return {"warning": "No emotion feedback provided"}

    feedback_record["confirmed_emotion"] = confirmed_emotion
    feedback_record["was_correct"] = was_correct

    # Phase 3: Anonymized HuBERT training data
    result = {}
    try:
        if training_features_table is not None:
            gate_result = apply_quality_gates(
                session=session,
                confirmed_emotion=confirmed_emotion,
                was_correct=was_correct,
                training_features_table=training_features_table,
            )

            if gate_result["accepted"]:
                anon_result = anonymize_and_confirm(
                    feature_id=gate_result["feature_id"],
                    confirmed_emotion=confirmed_emotion,
                    was_correct=was_correct,
                    session=session,
                    training_features_table=training_features_table,
                )
                result["ml_training"] = anon_result.get("status", "unknown")
                result["ml_feature_id"] = anon_result.get("feature_id", "")
                feedback_record["ml_training_result"] = anon_result
                logger.info(
                    f"ML training data confirmed: {anon_result.get('feature_id')} "
                    f"emotion={confirmed_emotion}"
                )
            else:
                reason = gate_result.get("rejection_reason", "unknown")
                result["ml_training"] = "rejected"
                result["ml_rejection_reason"] = reason
                logger.info(f"ML training data rejected: {reason}")
    except Exception as e:
        logger.warning(f"ML training anonymization failed (non-fatal): {e}")

    return result


def _process_general_feedback(body: Dict, feedback_record: Dict) -> Dict:
    """Process general/legacy feedback."""
    feedback_record["response_type"] = body.get("response_type", "")
    feedback_record["effectiveness"] = body.get("effectiveness", "")
    feedback_record["notes"] = body.get("notes", "")
    return {"type": "general"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_session(session_id: str) -> Optional[Dict]:
    try:
        response = session_table.get_item(Key={"session_id": session_id})
        if "Item" in response:
            return _decimal_to_float(response["Item"])
    except Exception as e:
        logger.warning(f"Failed to get session: {e}")
    return None


def _get_child_profile(child_id: str) -> Dict:
    try:
        response = child_profile_table.get_item(Key={"child_id": child_id})
        if "Item" in response:
            return _decimal_to_float(response["Item"])
    except Exception as e:
        logger.warning(f"Failed to get child profile: {e}")
    return {}


def _compute_age_days(birth_date_str: Optional[str]) -> Optional[int]:
    if not birth_date_str:
        return None
    try:
        from datetime import date
        birth = date.fromisoformat(birth_date_str)
        today = datetime.now(timezone.utc).date()
        return max(0, (today - birth).days)
    except (ValueError, TypeError):
        return None


def _error_response(status_code: int, message: str) -> Dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
        "body": json.dumps({"error": message}),
    }
