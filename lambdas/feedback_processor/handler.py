"""
Qleam — Feedback Processor Lambda
Stores parent feedback and triggers reinforcement engine.

Trigger: POST /session/{id}/feedback
Input:  API Gateway event with feedback body
Output: { status: "feedback_processed" }
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3

sys.path.insert(0, "/opt/python")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))

from constants import FEEDBACK_TABLE, SESSION_TABLE, SOUND_CLUSTER_TABLE

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
lambda_client = boto3.client("lambda")


def _float_to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
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


def get_session(session_id: str) -> Dict:
    response = session_table.get_item(Key={"session_id": session_id})
    if "Item" not in response:
        raise ValueError(f"Session {session_id} not found")
    return _decimal_to_float(response["Item"])


def save_feedback(
    feedback_id: str,
    session_id: str,
    child_id: str,
    cluster_id: str,
    response_type: str,
    effectiveness: str,
    word_token: str,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    feedback_item = {
        "feedback_id": feedback_id,
        "session_id": session_id,
        "child_id": child_id,
        "cluster_id": cluster_id,
        "response_type": response_type,
        "effectiveness": effectiveness,
        "word_token": word_token,
        "created_at": now,
    }
    feedback_table.put_item(Item=feedback_item)
    logger.info(f"Saved feedback {feedback_id}")


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

    # Validate effectiveness
    valid_effectiveness = {"helpful", "neutral", "ineffective"}
    if effectiveness not in valid_effectiveness:
        effectiveness = "neutral"

    # 1. Get session to find child_id and cluster_id
    session = get_session(session_id)
    child_id = session["child_id"]
    cluster_id = session.get("cluster_id")

    if not cluster_id:
        logger.warning(f"Session {session_id} has no cluster_id yet — feedback stored but reinforcement skipped")

    # 2. Save feedback record
    feedback_id = str(uuid.uuid4())
    save_feedback(
        feedback_id=feedback_id,
        session_id=session_id,
        child_id=child_id,
        cluster_id=cluster_id or "",
        response_type=response_type,
        effectiveness=effectiveness,
        word_token=word_token,
    )

    # 3. Trigger reinforcement engine (async) if cluster exists
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

    return {
        "status": "feedback_processed",
        "feedback_id": feedback_id,
        "session_id": session_id,
        "reinforcement_triggered": cluster_id is not None,
    }
