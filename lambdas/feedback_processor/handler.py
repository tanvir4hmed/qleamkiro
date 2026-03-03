"""
Qleam — Feedback Processor Lambda (Redesigned)
Handles two types of parent feedback:

1. BABY LANGUAGE FEEDBACK
   - Parent labels what baby was saying ("want milk", "play")
   - Parent describes the sound they heard ("ba ba ba")
   - Feeds into per-child private language model

2. CRY EMOTION FEEDBACK
   - Parent confirms/corrects the detected emotion
   - Feeds into global cry emotion training model (age-stratified)

Both feedback types are stored and used to improve detection accuracy.

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
    CONCEPT_GRAPH_TABLE,
    ENVIRONMENT_TO_LOCATION,
    ENVIRONMENT_TO_NOISE,
    FEEDBACK_TABLE,
    HEALTH_STATE_ENCODING,
    MODEL_REGISTRY_TABLE,
    SESSION_TABLE,
    TRAINING_CANDIDATE_TABLE,
    FEEDING_STATUS_MUCH_EARLY,
    FEEDING_STATUS_EARLY,
    FEEDING_STATUS_NORMAL,
    FEEDING_STATUS_LATE,
    FEEDING_STATUS_MUCH_LATE,
    FEEDING_STATUS_UNKNOWN,
    SLEEP_STATUS_JUST_WOKE,
    SLEEP_STATUS_RESTED,
    SLEEP_STATUS_PROBABLY_TIRED,
    SLEEP_STATUS_OVERTIRED,
    SLEEP_STATUS_UNKNOWN,
    BEHAVIORAL_FLAG_UNKNOWN,
    TRIGGER_UNKNOWN,
)
from cry_analyzer import get_age_bracket
from private_language_model import store_language_feedback, match_private_language
from cry_training_model import store_cry_training_sample, train_cry_model

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)

# Retrain cry model after this many new samples per age bracket
CRY_RETRAIN_THRESHOLD = 10


# ---------------------------------------------------------------------------
# Context feature encoding helpers
# ---------------------------------------------------------------------------

def _encode_feeding(minutes_ago) -> int:
    """Convert feeding_minutes_ago (int or None) to feeding_status code."""
    if minutes_ago is None:
        return FEEDING_STATUS_UNKNOWN
    try:
        m = int(minutes_ago)
    except (TypeError, ValueError):
        return FEEDING_STATUS_UNKNOWN
    if m < -90:
        return FEEDING_STATUS_MUCH_EARLY
    if m < -30:
        return FEEDING_STATUS_EARLY
    if m <= 30:
        return FEEDING_STATUS_NORMAL
    if m <= 90:
        return FEEDING_STATUS_LATE
    return FEEDING_STATUS_MUCH_LATE


def _encode_sleep(sleep_status_raw) -> int:
    """Convert sleep_status (int or None) to sleep_status code.
    Passes through if already an int in valid range; defaults to unknown."""
    if sleep_status_raw is None:
        return SLEEP_STATUS_UNKNOWN
    try:
        v = int(sleep_status_raw)
        if 0 <= v <= 3:
            return v
    except (TypeError, ValueError):
        pass
    return SLEEP_STATUS_UNKNOWN


def _encode_behavioral_flag(raw) -> int:
    """Pass through binary behavioral flag (0/1) or return -1 for unknown."""
    if raw is None:
        return BEHAVIORAL_FLAG_UNKNOWN
    try:
        v = int(raw)
        if v in (0, 1):
            return v
    except (TypeError, ValueError):
        pass
    return BEHAVIORAL_FLAG_UNKNOWN


def _encode_trigger(raw) -> int:
    """Pass through trigger code (0-8) or return -1 for unknown."""
    if raw is None:
        return TRIGGER_UNKNOWN
    try:
        v = int(raw)
        if 0 <= v <= 8:
            return v
    except (TypeError, ValueError):
        pass
    return TRIGGER_UNKNOWN


def _build_context_features(session_context: dict) -> dict:
    """
    Build numerically-encoded context feature dict from session_context.
    All fields default to -1 (unknown) if not present or unrecognisable.
    """
    env = session_context.get("environment", "unknown")
    return {
        "feeding_status":     _encode_feeding(session_context.get("feeding_minutes_ago")),
        "sleep_status":       _encode_sleep(session_context.get("sleep_status")),
        "health_flag":        HEALTH_STATE_ENCODING.get(
                                  session_context.get("health_state", "unknown"), -1),
        "rooting_flag":       _encode_behavioral_flag(session_context.get("rooting_flag")),
        "hand_to_mouth_flag": _encode_behavioral_flag(session_context.get("hand_to_mouth_flag")),
        "eye_rub_flag":       _encode_behavioral_flag(session_context.get("eye_rub_flag")),
        "tantrum_body_flag":  _encode_behavioral_flag(session_context.get("tantrum_body_flag")),
        "location_code":      ENVIRONMENT_TO_LOCATION.get(env, -1),
        "noise_level":        ENVIRONMENT_TO_NOISE.get(env, -1),
        "trigger_code":       _encode_trigger(session_context.get("trigger_code")),
    }


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
    Feedback Processor — handles language and cry emotion feedback.

    Expected body:
    {
        "session_id": str,
        "feedback_type": "language" | "cry_emotion" | "general",

        // For language feedback:
        "baby_sound": str,        // What sound did baby make? (e.g., "ba ba ba")
        "parent_meaning": str,    // What do you think they meant? (e.g., "want milk")

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
        feedback_type = body.get("feedback_type", "general")

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
        if feedback_type == "language":
            result.update(
                _process_language_feedback(
                    body, session, child_id, session_id, age_days, feedback_record
                )
            )
        elif feedback_type == "cry_emotion":
            result.update(
                _process_cry_emotion_feedback(
                    body, session, child_id, session_id, age_days, feedback_record
                )
            )
        else:
            # General feedback (backward compatibility)
            result.update(
                _process_general_feedback(body, feedback_record)
            )

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


def _process_language_feedback(
    body: Dict,
    session: Dict,
    child_id: str,
    session_id: str,
    age_days: Optional[int],
    feedback_record: Dict,
) -> Dict:
    """
    Process baby language feedback.
    Parent tells us what baby was saying and what sound they made.
    """
    baby_sound = body.get("baby_sound", "").strip()
    parent_meaning = body.get("parent_meaning", "").strip()

    if not baby_sound and not parent_meaning:
        return {"warning": "No language feedback provided"}

    feedback_record["baby_sound"] = baby_sound
    feedback_record["parent_meaning"] = parent_meaning

    # Get embedding from session for pattern matching
    embedding = session.get("embedding_vector", [])

    # Check if this matches an existing private language pattern
    existing_match = None
    if embedding:
        try:
            existing_match = match_private_language(
                embedding, child_id, concept_graph_table
            )
        except Exception as e:
            logger.warning(f"Private language match check failed: {e}")

    # Store/update private language pattern
    existing_id = None
    if existing_match and existing_match.get("matched"):
        existing_id = existing_match.get("pattern_id")

    label = parent_meaning or baby_sound
    description = baby_sound if parent_meaning else ""

    try:
        store_result = store_language_feedback(
            child_id=child_id,
            embedding=embedding,
            parent_label=label,
            parent_description=description,
            session_id=session_id,
            concept_graph_table=concept_graph_table,
            existing_pattern_id=existing_id,
        )
        feedback_record["language_model_update"] = store_result
        return {
            "language_update": store_result.get("status", "unknown"),
            "pattern_id": store_result.get("concept_id", ""),
        }
    except Exception as e:
        logger.error(f"Language feedback storage failed: {e}")
        return {"warning": f"Language feedback storage failed: {e}"}


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
    confirmed_emotion = body.get("confirmed_emotion", "").strip()
    was_correct = body.get("was_correct", True)

    if not confirmed_emotion:
        return {"warning": "No emotion feedback provided"}

    feedback_record["confirmed_emotion"] = confirmed_emotion
    feedback_record["was_correct"] = was_correct

    age_bracket = get_age_bracket(age_days)
    sound_features = session.get("sound_features", {})

    if not sound_features:
        sound_features = session.get("sound_classification", {}).get("features", {})

    # Build context features from session context if available
    session_context = session.get("session_context") or {}
    context_features = _build_context_features(session_context) if session_context else None

    # Store training sample (v2 multimodal if context available, v1 acoustic-only otherwise)
    try:
        store_result = store_cry_training_sample(
            features=sound_features,
            confirmed_emotion=confirmed_emotion,
            age_bracket=age_bracket,
            child_id=child_id,
            session_id=session_id,
            training_candidate_table=training_candidate_table,
            context_features=context_features,
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
