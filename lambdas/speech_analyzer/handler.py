"""
Qleam — Speech Analyzer Lambda (Phase 7, Layer 9)

Language development analysis for LINGUISTIC-mode sessions.
Only runs for children in LINGUISTIC developmental mode; early-exits otherwise.

Trigger: Step Function invocation after ConceptDecoder
Input:  { child_id, session_id, cluster_id }
Output: { status, child_id, session_id, speech_analysis }
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    CONCEPT_GRAPH_TABLE,
    MILESTONES_TABLE,
    MILESTONE_TYPES,
    SESSION_TABLE,
)
from language_analysis import (
    classify_pragmatic_type,
    estimate_mlu,
    estimate_vocabulary_diversity,
    score_fluency,
)

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
milestones_table = dynamodb.Table(MILESTONES_TABLE)


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


def _get_session(session_id: str) -> Optional[Dict]:
    resp = session_table.get_item(Key={"session_id": session_id})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def _get_child_profile(child_id: str) -> Optional[Dict]:
    resp = child_profile_table.get_item(Key={"child_id": child_id})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def _get_confirmed_concepts(child_id: str) -> int:
    """Count confirmed concepts (confirmation_count >= 2) for a child."""
    resp = concept_graph_table.query(
        IndexName="child_id-last_updated-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
    )
    return sum(
        1 for item in resp.get("Items", [])
        if int(item.get("confirmation_count", 0)) >= 2
    )


def _milestone_already_logged(child_id: str, milestone_type: str) -> bool:
    resp = milestones_table.query(
        IndexName="child_id-first_date-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
    )
    return any(
        item.get("milestone_type") == milestone_type
        for item in resp.get("Items", [])
    )


def _log_milestone(child_id: str, milestone_type: str, session_id: str, details: Dict) -> None:
    milestone_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    milestones_table.put_item(Item={
        "child_id": child_id,
        "milestone_id": milestone_id,
        "milestone_type": milestone_type,
        "description": MILESTONE_TYPES.get(milestone_type, milestone_type),
        "first_date": now,
        "session_id": session_id,
        "details": _float_to_decimal(details),
    })
    logger.info(f"Milestone logged: {milestone_type} for child {child_id}")


def lambda_handler(event: dict, context) -> dict:
    """
    Speech Analyzer handler — LINGUISTIC mode language development analysis.

    Args:
        event: { "child_id": str, "session_id": str, "cluster_id": str }
    """
    child_id = event.get("child_id", "")
    session_id = event.get("session_id", "")

    if not child_id or not session_id:
        logger.warning("SpeechAnalyzer called with missing child_id or session_id")
        return {"status": "skipped", "reason": "missing_fields"}

    logger.info(f"SpeechAnalyzer: child={child_id} session={session_id}")

    # --- Load session ---
    session = _get_session(session_id)
    if not session:
        logger.warning(f"Session {session_id} not found")
        return {"status": "skipped", "reason": "session_not_found"}

    # --- Early exit for non-LINGUISTIC sessions ---
    developmental_mode = session.get("developmental_mode", "")
    if developmental_mode != "LINGUISTIC":
        logger.info(f"SpeechAnalyzer: skipping non-LINGUISTIC session (mode={developmental_mode})")
        return {"status": "skipped", "reason": "not_linguistic_mode"}

    rich_features = session.get("rich_features", {})
    developmental_stage = session.get("developmental_stage", "")

    # --- Count confirmed concepts ---
    confirmed_concepts = _get_confirmed_concepts(child_id)

    # --- Compute language metrics ---
    mlu = estimate_mlu(rich_features)
    vocab_diversity = estimate_vocabulary_diversity(rich_features, known_concepts=confirmed_concepts)
    pragmatic_type = classify_pragmatic_type(rich_features)
    fluency_score = score_fluency(rich_features)

    # --- Load child profile for MLU EMA ---
    profile = _get_child_profile(child_id) or {}
    old_mlu_ema = float(profile.get("mlu_ema", 1.0))

    # --- MLU EMA update ---
    new_mlu_ema = round(0.25 * mlu + 0.75 * old_mlu_ema, 3)

    # --- Update child profile ---
    try:
        child_profile_table.update_item(
            Key={"child_id": child_id},
            UpdateExpression=(
                "SET mlu_ema = :ema, last_pragmatic_type = :ptype, vocab_size = :vs"
            ),
            ExpressionAttributeValues={
                ":ema": _float_to_decimal(new_mlu_ema),
                ":ptype": pragmatic_type,
                ":vs": confirmed_concepts,
            },
        )
    except Exception as e:
        logger.warning(f"Failed to update child profile MLU EMA: {e}")

    # --- Milestone checks ---
    milestones_this_session: List[str] = []

    if new_mlu_ema >= 2.0 and not _milestone_already_logged(child_id, "FIRST_MLU_2"):
        _log_milestone(child_id, "FIRST_MLU_2", session_id, {"mlu_ema": new_mlu_ema})
        milestones_this_session.append("FIRST_MLU_2")

    if new_mlu_ema >= 3.0 and not _milestone_already_logged(child_id, "FIRST_MLU_3"):
        _log_milestone(child_id, "FIRST_MLU_3", session_id, {"mlu_ema": new_mlu_ema})
        milestones_this_session.append("FIRST_MLU_3")

    if confirmed_concepts >= 20 and not _milestone_already_logged(child_id, "VOCAB_SIZE_20"):
        _log_milestone(child_id, "VOCAB_SIZE_20", session_id, {"vocab_size": confirmed_concepts})
        milestones_this_session.append("VOCAB_SIZE_20")

    if confirmed_concepts >= 50 and not _milestone_already_logged(child_id, "VOCAB_SIZE_50"):
        _log_milestone(child_id, "VOCAB_SIZE_50", session_id, {"vocab_size": confirmed_concepts})
        milestones_this_session.append("VOCAB_SIZE_50")

    # --- Build and store speech_analysis on session ---
    speech_analysis = {
        "estimated_mlu": mlu,
        "mlu_ema": new_mlu_ema,
        "vocabulary_diversity": vocab_diversity,
        "vocabulary_size": confirmed_concepts,
        "pragmatic_type": pragmatic_type,
        "fluency_score": fluency_score,
        "developmental_stage": developmental_stage,
        "milestones_this_session": milestones_this_session,
    }

    try:
        session_table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET speech_analysis = :sa",
            ExpressionAttributeValues={":sa": _float_to_decimal(speech_analysis)},
        )
    except Exception as e:
        logger.warning(f"Failed to store speech_analysis on session: {e}")

    logger.info(
        f"SpeechAnalyzer: mlu={mlu} mlu_ema={new_mlu_ema} "
        f"pragmatic={pragmatic_type} fluency={fluency_score} "
        f"vocab={confirmed_concepts} milestones={milestones_this_session}"
    )
    return {
        "status": "ok",
        "child_id": child_id,
        "session_id": session_id,
        "speech_analysis": speech_analysis,
    }
