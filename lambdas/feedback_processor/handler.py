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
    FEEDBACK_TABLE,
    MODEL_REGISTRY_TABLE,
    SESSION_TABLE,
    TRAINING_CANDIDATE_TABLE,
)
from cry_analyzer import get_age_bracket
from private_language_model import store_language_feedback, match_private_language
from cry_training_model import store_cry_training_sample, train_cry_model
from trust_scoring import (
    compute_agreement_signal,
    detect_fraud_signal,
    update_frs,
    update_crs,
    compute_delta_score,
)

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
        elif feedback_type == "speaker_verification":
            result.update(
                _process_speaker_verification_feedback(body, feedback_record)
            )
        else:
            # General feedback (backward compatibility)
            result.update(
                _process_general_feedback(body, feedback_record)
            )

        # --- Trust Scoring (Phase 11) ---
        trust_result = _process_trust_scoring(
            session=session,
            profile=profile,
            child_id=child_id,
            feedback_record=feedback_record,
            body=body,
        )
        if trust_result:
            feedback_record["trust_scoring"] = trust_result
            result["trust_updated"] = True

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
    # Accept both confirmed_emotion (string) and confirmed_emotions (array from FeedbackForm)
    confirmed_emotion = str(body.get("confirmed_emotion", "") or "").strip()
    if not confirmed_emotion:
        emotions_list = body.get("confirmed_emotions") or []
        confirmed_emotion = emotions_list[0] if emotions_list else ""
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


def _process_speaker_verification_feedback(body: Dict, feedback_record: Dict) -> Dict:
    """Process speaker verification feedback (adult/baby/both/older-child)."""
    speaker_answer = str(body.get("speaker_answer", "") or "").strip()
    if not speaker_answer:
        return {"warning": "No speaker answer provided"}
    feedback_record["speaker_answer"] = speaker_answer
    if body.get("notes"):
        feedback_record["notes"] = str(body["notes"])[:500]
    return {"speaker_verification": speaker_answer}


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
# Trust Scoring (Phase 11)
# ---------------------------------------------------------------------------

def _process_trust_scoring(
    session: Dict,
    profile: Dict,
    child_id: str,
    feedback_record: Dict,
    body: Dict,
) -> Optional[Dict]:
    """
    Process trust scoring for this feedback event.

    Flow:
      1. Read evidence fingerprint (EFP) from session
      2. Read FRS/CRS from child profile
      3. Compute agreement signal (feedback vs EFP)
      4. Detect fraud signals (timing, patterns)
      5. Update FRS (asymmetric EMA)
      6. Update CRS (context validation)
      7. Compute delta score (training gate)
      8. Store updated FRS/CRS on child profile
      9. Return metadata for feedback record
    """
    try:
        # 1. Read EFP from session
        efp = session.get("evidence_fingerprint")
        if not efp:
            logger.debug("No EFP on session — skipping trust scoring")
            return None

        # 2. Read current trust scores from profile
        current_frs = float(profile.get("parent_trust_score", 0.5) or 0.5)
        current_crs = float(profile.get("context_reliability", 0.8) or 0.8)
        recent_responses = profile.get("recent_response_types", [])
        if not isinstance(recent_responses, list):
            recent_responses = []

        # Determine feedback intent from the body
        feedback_intent = (
            body.get("confirmed_emotion")
            or body.get("response_type")
            or ""
        ).strip()

        if not feedback_intent:
            return None

        # 3. Compute agreement signal
        agreement_level, agreement_score = compute_agreement_signal(
            feedback_intent=feedback_intent,
            acoustic_top=efp.get("acoustic_top", ""),
            research_top=efp.get("research_top", ""),
            blended_top=efp.get("blended_top", ""),
            confidences={
                "acoustic": float(efp.get("acoustic_confidence", 0.5) or 0.5),
                "blended": float(efp.get("blended_confidence", 0.5) or 0.5),
            },
        )

        # 4. Detect fraud signals
        fraud = detect_fraud_signal(
            feedback_timestamp=feedback_record.get("created_at"),
            insight_generated_at=session.get("insight_generated_at"),
            recent_responses=recent_responses,
            current_frs=current_frs,
        )

        # 5. Update FRS
        new_frs, frs_meta = update_frs(current_frs, agreement_score, fraud)

        # 6. Update CRS
        # Context is "matched" if feedback agrees with blended top
        context_matched = feedback_intent.lower() == efp.get("blended_top", "").lower()
        new_crs, crs_meta = update_crs(current_crs, context_matched, fraud)

        # 7. Compute delta score
        acoustic_scores = session.get("insight", {}).get("evidence", {}).get("acoustic", {})
        delta_score = compute_delta_score(acoustic_scores, feedback_intent)

        # 8. Update sliding window of recent responses
        recent_responses.append(feedback_intent)
        recent_responses = recent_responses[-10:]  # Keep last 10

        # 9. Store updated scores on child profile
        try:
            child_profile_table.update_item(
                Key={"child_id": child_id},
                UpdateExpression=(
                    "SET parent_trust_score = :frs, "
                    "context_reliability = :crs, "
                    "recent_response_types = :rrt"
                ),
                ExpressionAttributeValues={
                    ":frs": _float_to_decimal(new_frs),
                    ":crs": _float_to_decimal(new_crs),
                    ":rrt": recent_responses,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to update trust scores on profile: {e}")

        return {
            "agreement_level": agreement_level,
            "agreement_score": round(agreement_score, 4),
            "fraud_signal": fraud.get("signal", "NONE"),
            "frs": frs_meta,
            "crs": crs_meta,
            "delta_score": round(delta_score, 4),
        }

    except Exception as e:
        logger.warning(f"Trust scoring failed (non-fatal): {e}")
        return None


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
