"""
Qleam — API Handler Lambda
Routes all API Gateway requests to appropriate business logic.

Endpoints:
  POST   /child                          → create child profile
  DELETE /child/{child_id}               → delete child + all data
  GET    /child/{child_id}/sessions      → list sessions
  POST   /session/upload                 → get presigned URL + start pipeline
  GET    /session/{session_id}/insight   → get session insight
  POST   /session/{session_id}/feedback  → submit feedback
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

sys.path.insert(0, "/opt/python")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))

from constants import (
    CHILD_PROFILE_TABLE,
    FEEDBACK_TABLE,
    S3_BUCKET_NAME,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    STEP_FUNCTION_ARN,
)

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# Get allowed CORS origins from environment variable
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
sfn_client = boto3.client("stepfunctions")
lambda_client = boto3.client("lambda")

child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)
feedback_table = dynamodb.Table(FEEDBACK_TABLE)


def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _float_to_decimal(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


def get_allowed_origin(event: Dict) -> str:
    """Get the allowed origin from request headers if trusted, otherwise return '*'."""
    if not ALLOWED_ORIGINS:
        return "*"  # If no allowed origins configured, allow all (backward compatibility)
    
    origin = event.get("headers", {}).get("Origin") or event.get("headers", {}).get("origin", "")
    if origin and origin in ALLOWED_ORIGINS:
        return origin
    # Return '*' as fallback for untrusted origins (allows localhost and other dev origins)
    return "*"


def response(status_code: int, body: Any, event: Optional[Dict] = None) -> Dict:
    """Create API Gateway response with CORS headers."""
    origin = get_allowed_origin(event) if event else "*"
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    }
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, default=str),
    }


def get_user_id(event: Dict) -> str:
    """Extract Cognito user ID from JWT claims."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    return claims.get("sub", claims.get("cognito:username", "anonymous"))


# =============================================================================
# POST /child — Create child profile
# =============================================================================
def create_child(event: Dict) -> Dict:
    user_id = get_user_id(event)
    body = json.loads(event.get("body") or "{}")
    child_name = body.get("name", "")

    child_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    profile = {
        "child_id": child_id,
        "parent_id": user_id,
        "name": child_name,
        "baseline_features": {},
        "readiness_score": 0.5,
        "language_maturity_level": "pre-linguistic",
        "session_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    child_profile_table.put_item(Item=_float_to_decimal(profile))
    logger.info(f"Created child profile {child_id} for user {user_id}")

    return response(201, {"child_id": child_id, "message": "Child profile created"}, event)


# =============================================================================
# DELETE /child/{child_id} — Delete child and all associated data
# =============================================================================
def delete_child(event: Dict) -> Dict:
    user_id = get_user_id(event)
    child_id = event["pathParameters"]["child_id"]

    # Verify ownership
    profile_resp = child_profile_table.get_item(Key={"child_id": child_id})
    if "Item" not in profile_resp:
        return response(404, {"error": "Child not found"}, event)

    profile = profile_resp["Item"]
    if profile.get("parent_id") != user_id:
        return response(403, {"error": "Not authorized to delete this child profile"}, event)

    # Delete sessions
    sessions_resp = session_table.query(
        IndexName="child_id-timestamp-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id)
    )
    for session in sessions_resp.get("Items", []):
        session_table.delete_item(Key={"session_id": session["session_id"]})

    # Delete clusters
    clusters_resp = sound_cluster_table.query(
        IndexName="child_id-last_updated-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id)
    )
    for cluster in clusters_resp.get("Items", []):
        sound_cluster_table.delete_item(Key={"cluster_id": cluster["cluster_id"]})

    # Delete semantic bridges
    bridges_resp = semantic_bridge_table.query(
        IndexName="child_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id)
    )
    for bridge in bridges_resp.get("Items", []):
        semantic_bridge_table.delete_item(Key={"bridge_id": bridge["bridge_id"]})

    # Delete child profile
    child_profile_table.delete_item(Key={"child_id": child_id})

    logger.info(f"Deleted all data for child {child_id}")
    return response(200, {"message": "Child profile and all associated data deleted"}, event)


# =============================================================================
# GET /child/{child_id}/sessions — List sessions
# =============================================================================
def list_sessions(event: Dict) -> Dict:
    child_id = event["pathParameters"]["child_id"]

    sessions_resp = session_table.query(
        IndexName="child_id-timestamp-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("child_id").eq(child_id),
        ScanIndexForward=False,  # Most recent first
        Limit=50,
    )

    sessions = [_decimal_to_float(s) for s in sessions_resp.get("Items", [])]

    # Return summary (no embedding vectors)
    summaries = []
    for s in sessions:
        summaries.append({
            "session_id": s["session_id"],
            "timestamp": s.get("timestamp"),
            "deviation_level": s.get("deviation_level", "none"),
            "feature_scores": s.get("feature_scores", {}),
            "cluster_id": s.get("cluster_id"),
            "insight_summary": {
                "probable_intent": s.get("insight", {}).get("probable_intent"),
                "suggested_response": s.get("insight", {}).get("suggested_response"),
            } if s.get("insight") else None,
        })

    return response(200, {"sessions": summaries, "count": len(summaries)}, event)


# =============================================================================
# POST /session/upload — Get presigned URL and create session record
# =============================================================================
def upload_session(event: Dict) -> Dict:
    user_id = get_user_id(event)
    body = json.loads(event.get("body") or "{}")
    child_id = body.get("child_id")

    if not child_id:
        return response(400, {"error": "child_id is required"}, event)

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    s3_key = f"{child_id}/{session_id}/audio.wav"

    # Generate presigned URL for direct upload
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ContentType": "audio/wav",
        },
        ExpiresIn=300,  # 5 minutes
    )

    # Create pending session record
    session_item = {
        "session_id": session_id,
        "child_id": child_id,
        "parent_id": user_id,
        "s3_audio_path": s3_key,
        "processed": False,
        "timestamp": now,
    }
    session_table.put_item(Item=session_item)

    logger.info(f"Created upload session {session_id} for child {child_id}")

    return response(200, {
        "session_id": session_id,
        "upload_url": presigned_url,
        "s3_key": s3_key,
        "expires_in": 300,
        "instructions": "PUT audio/wav file to upload_url, then call start_processing",
    }, event)


# =============================================================================
# POST /session/{session_id}/start — Start processing pipeline
# =============================================================================
def start_processing(event: Dict) -> Dict:
    session_id = event["pathParameters"]["session_id"]
    body = json.loads(event.get("body") or "{}")

    session_resp = session_table.get_item(Key={"session_id": session_id})
    if "Item" not in session_resp:
        return response(404, {"error": "Session not found"}, event)

    session = _decimal_to_float(session_resp["Item"])
    child_id = session["child_id"]
    s3_audio_path = session["s3_audio_path"]

    sfn_arn = os.environ.get("STEP_FUNCTION_ARN", STEP_FUNCTION_ARN)
    if not sfn_arn:
        return response(500, {"error": "Step Function ARN not configured"}, event)

    sfn_input = {
        "child_id": child_id,
        "session_id": session_id,
        "s3_audio_path": s3_audio_path,
    }

    sfn_client.start_execution(
        stateMachineArn=sfn_arn,
        name=f"session-{session_id}",
        input=json.dumps(sfn_input),
    )

    logger.info(f"Started processing pipeline for session {session_id}")
    return response(202, {
        "message": "Processing started",
        "session_id": session_id,
        "status": "processing",
    }, event)


# =============================================================================
# GET /session/{session_id}/insight — Get session insight
# =============================================================================
def get_insight(event: Dict) -> Dict:
    session_id = event["pathParameters"]["session_id"]

    session_resp = session_table.get_item(Key={"session_id": session_id})
    if "Item" not in session_resp:
        return response(404, {"error": "Session not found"}, event)

    session = _decimal_to_float(session_resp["Item"])

    if not session.get("processed"):
        return response(202, {"status": "processing", "message": "Session is still being processed"}, event)

    insight = session.get("insight")
    if not insight:
        return response(404, {"error": "Insight not yet generated"}, event)

    return response(200, {
        "session_id": session_id,
        "insight": insight,
        "timestamp": session.get("timestamp"),
    }, event)


# =============================================================================
# POST /session/{session_id}/feedback — Submit feedback
# =============================================================================
def submit_feedback(event: Dict) -> Dict:
    session_id = event["pathParameters"]["session_id"]
    body = json.loads(event.get("body") or "{}")

    feedback_payload = {
        "session_id": session_id,
        "response_type": body.get("response_type", ""),
        "effectiveness": body.get("effectiveness", "neutral"),
        "word_token": body.get("word_token", ""),
    }

    # Invoke feedback processor Lambda
    feedback_fn = os.environ.get(
        "FEEDBACK_PROCESSOR_LAMBDA",
        f"qleam-{os.environ.get('ENVIRONMENT', 'dev')}-feedback-processor"
    )

    try:
        result = lambda_client.invoke(
            FunctionName=feedback_fn,
            InvocationType="RequestResponse",
            Payload=json.dumps(feedback_payload).encode(),
        )
        result_payload = json.loads(result["Payload"].read())
        return response(200, result_payload, event)
    except Exception as e:
        logger.error(f"Feedback processor failed: {e}")
        return response(500, {"error": "Failed to process feedback"}, event)


# =============================================================================
# Router
# =============================================================================
ROUTES = {
    ("POST", "/child"): create_child,
    ("DELETE", "/child/{child_id}"): delete_child,
    ("GET", "/child/{child_id}/sessions"): list_sessions,
    ("POST", "/session/upload"): upload_session,
    ("POST", "/session/{session_id}/start"): start_processing,
    ("GET", "/session/{session_id}/insight"): get_insight,
    ("POST", "/session/{session_id}/feedback"): submit_feedback,
}


def lambda_handler(event: Dict, context: Any) -> Dict:
    method = event.get("httpMethod", "")
    path = event.get("resource", event.get("path", ""))

    logger.info(f"API request: {method} {path}")

    if method == "OPTIONS":
        return response(200, {}, event)

    for (route_method, route_path), handler in ROUTES.items():
        if method == route_method and _path_matches(path, route_path):
            try:
                return handler(event)
            except Exception as e:
                logger.error(f"Handler error: {e}", exc_info=True)
                return response(500, {"error": "Internal server error"}, event)

    return response(404, {"error": f"Route not found: {method} {path}"}, event)


def _path_matches(actual: str, template: str) -> bool:
    """Simple path template matching."""
    actual_parts = actual.strip("/").split("/")
    template_parts = template.strip("/").split("/")
    if len(actual_parts) != len(template_parts):
        return False
    for a, t in zip(actual_parts, template_parts):
        if not t.startswith("{") and a != t:
            return False
    return True
