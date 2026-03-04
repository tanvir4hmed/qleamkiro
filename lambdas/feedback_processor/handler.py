"""
Qleam — Feedback Processor Lambda (Redesigned)
Handles parent feedback for cry emotion training:

1. CRY EMOTION FEEDBACK
   - Parent confirms/corrects the detected emotion
   - Feeds into global cry emotion training model (age-stratified)

Legacy "general" feedback is stored for backward compatibility.

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
    MODEL_REGISTRY_TABLE,
    SESSION_TABLE,
    TRAINING_CANDIDATE_TABLE,
)
from cry_analyzer import get_age_bracket
from cry_training_model import store_cry_training_sample, train_cry_model

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)

# Retrain cry model after this many new samples per age bracket
CRY_RETRAIN_THRESHOLD = 20


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

    age_bracket = get_age_bracket(age_days)
    sound_features = session.get("sound_features", {})

    if not sound_features:
        sound_features = session.get("sound_classification", {}).get("features", {})

    # Store training sample
    try:
        store_result = store_cry_training_sample(
            features=sound_features,
            confirmed_emotion=confirmed_emotion,
            age_bracket=age_bracket,
            child_id=child_id,
            session_id=session_id,
            training_candidate_table=training_candidate_table,
        )
        feedback_record["cry_model_update"] = store_result

        # Check if we should retrain the cry model
        _check_and_retrain(age_bracket)

        return {
            "cry_training": store_result.get("status", "unknown"),
            "candidate_id": store_result.get("candidate_id", ""),
        }
    except Exception as e:
        logger.error(f"Cry emotion feedback storage failed: {e}")
        return {"warning": f"Cry feedback storage failed: {e}"}


def _process_general_feedback(body: Dict, feedback_record: Dict) -> Dict:
    """Process general/legacy feedback."""
    feedback_record["response_type"] = body.get("response_type", "")
    feedback_record["effectiveness"] = body.get("effectiveness", "")
    feedback_record["notes"] = body.get("notes", "")
    return {"type": "general"}


def _check_and_retrain(age_bracket: str):
    """Check if enough new samples exist to trigger cry model retraining."""
    try:
        from boto3.dynamodb.conditions import Attr
        response = training_candidate_table.scan(
            FilterExpression=(
                Attr("candidate_type").eq("cry_emotion") &
                Attr("age_bracket").eq(age_bracket)
            ),
            Select="COUNT",
        )
        count = response.get("Count", 0)

        # Retrain if we have enough samples and count is a multiple of threshold
        if count >= CRY_RETRAIN_THRESHOLD and count % CRY_RETRAIN_THRESHOLD == 0:
            logger.info(f"Triggering cry model retrain for {age_bracket} (n={count})")
            train_cry_model(age_bracket, training_candidate_table, model_registry_table)
    except Exception as e:
        logger.warning(f"Retrain check failed: {e}")


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
