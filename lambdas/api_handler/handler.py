"""
Qleam — API Handler Lambda
Routes all API Gateway requests to appropriate business logic.

Endpoints:
  POST   /child                          → create child profile
  DELETE /child/{child_id}               → delete child + all data
  DELETE /account                        → delete all parent-owned child data
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
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    CONCEPT_GRAPH_TABLE,
    FEEDBACK_TABLE,
    MILESTONES_TABLE,
    S3_BUCKET_NAME,
    SAGEMAKER_HUBERT_ENDPOINT,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    TRAINING_CANDIDATE_TABLE,
    TRAINING_FEATURES_TABLE,
    USE_SAGEMAKER_INTENT_ENDPOINT,
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
MAX_SUPPORTED_CHILD_AGE_DAYS = 730  # 24 months

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
sfn_client = boto3.client("stepfunctions")
lambda_client = boto3.client("lambda")
ssm_client = boto3.client("ssm")

# Step Function ARN from environment variable (set by Terraform)
def get_step_function_arn() -> str:
    """Get Step Function ARN from environment variable."""
    arn = os.environ.get("STEP_FUNCTION_ARN", "")
    if not arn:
        raise RuntimeError("STEP_FUNCTION_ARN environment variable not set")
    return arn

child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
milestones_table = dynamodb.Table(MILESTONES_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE) if TRAINING_CANDIDATE_TABLE else None
training_features_table = dynamodb.Table(TRAINING_FEATURES_TABLE) if TRAINING_FEATURES_TABLE else None


def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


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


def get_allowed_origin(event: Dict) -> str:
    """Get the allowed origin from request headers if trusted.
    
    Returns the specific origin if it's in the allowed list, otherwise returns
    the first allowed origin as fallback. This is required because when
    Access-Control-Allow-Credentials is true, Access-Control-Allow-Origin
    cannot be '*' - it must be a specific origin.
    """
    # Check both Origin and origin header keys (API Gateway can use either)
    headers = event.get("headers", {})
    origin = headers.get("Origin") or headers.get("origin") or ""
    
    # Also check multi-value headers
    multi_value_headers = event.get("multiValueHeaders", {})
    if not origin and "Origin" in multi_value_headers:
        origin = multi_value_headers["Origin"][0] if multi_value_headers["Origin"] else ""
    
    # Normalize origin for comparison (remove trailing slash)
    origin = origin.rstrip("/")
    
    # Log for debugging
    logger.debug(f"Request origin: {origin}, Allowed origins: {ALLOWED_ORIGINS}")
    
    # Check if origin matches any allowed origin (with or without trailing slash)
    for allowed in ALLOWED_ORIGINS:
        if origin == allowed.rstrip("/"):
            logger.debug(f"Origin {origin} matched allowed origin {allowed}")
            return origin
    
    # For development: allow localhost origins
    if "localhost" in origin or "127.0.0.1" in origin:
        logger.debug(f"Allowing localhost origin: {origin}")
        return origin
    
    # If no match but we have allowed origins configured, return the first one
    # This handles cases where the origin header might be missing or different
    if ALLOWED_ORIGINS:
        logger.warning(f"Origin {origin} not in allowed list, using first allowed: {ALLOWED_ORIGINS[0]}")
        return ALLOWED_ORIGINS[0].rstrip("/")
    
    # Last resort fallback (should not happen in production)
    logger.warning("No allowed origins configured, returning request origin")
    return origin if origin else "*"


def response(status_code: int, body: Any, event: Optional[Dict] = None) -> Dict:
    """Create API Gateway response with CORS headers."""
    origin = get_allowed_origin(event) if event else "*"
    headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        "Access-Control-Allow-Credentials": "true",
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
# GET /child — List all children for the authenticated parent
# =============================================================================
def list_children(event: Dict) -> Dict:
    user_id = get_user_id(event)

    result = child_profile_table.query(
        IndexName="parent_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("parent_id").eq(user_id),
    )

    children = [
        {
            "child_id": item["child_id"],
            "name": item.get("name", ""),
            "birth_date": item.get("birth_date", ""),
            "session_count": _decimal_to_float(item.get("session_count", 0)),
            "created_at": item.get("created_at"),
        }
        for item in result.get("Items", [])
    ]

    return response(200, {"children": children, "count": len(children)}, event)


# =============================================================================
# POST /child — Create child profile
# =============================================================================
def create_child(event: Dict) -> Dict:
    user_id = get_user_id(event)
    body = json.loads(event.get("body") or "{}")
    child_name = body.get("name", "").strip()
    birth_date = body.get("birth_date", "").strip()  # Expected: "YYYY-MM-DD"
    gender = body.get("gender", "").strip().lower()  # "boy", "girl", "other", or "" (optional)

    if not child_name:
        return response(400, {"error": "name is required"}, event)

    # birth_date is mandatory — drives age calculation for cry analysis
    if not birth_date:
        return response(400, {"error": "birth_date is required (YYYY-MM-DD)"}, event)
    try:
        birth = date.fromisoformat(birth_date)
    except ValueError:
        return response(400, {"error": "birth_date must be a valid date in YYYY-MM-DD format"}, event)
    today = datetime.now(timezone.utc).date()
    age_days = (today - birth).days
    if age_days < 0:
        return response(400, {"error": "birth_date cannot be in the future"}, event)
    if age_days > MAX_SUPPORTED_CHILD_AGE_DAYS:
        return response(
            400,
            {"error": "Only children aged 0-24 months are supported. Please provide a birth_date within the last 24 months."},
            event,
        )

    child_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    profile = {
        "child_id": child_id,
        "parent_id": user_id,
        "name": child_name,
        "birth_date": birth_date,
        "gender": gender if gender in ("boy", "girl", "other") else "",
        "baseline_features": {},
        "readiness_score": 0.5,
        "session_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    child_profile_table.put_item(Item=_float_to_decimal(profile))
    logger.info(f"Created child profile {child_id} for user {user_id} (birth_date={'set' if birth_date else 'not set'})")

    return response(201, {"child_id": child_id, "message": "Child profile created"}, event)


# =============================================================================
# DELETE /child/{child_id} — Delete child and all associated data
# =============================================================================
def _delete_child_direct_data(child_id: str) -> Dict[str, int]:
    """
    Delete all direct personal data rows for a child.
    Includes S3 audio files (biometric PII) and training candidates (PII-linked).
    Intentionally does NOT touch de-identified training_features or trained models.
    """
    _key = boto3.dynamodb.conditions.Key
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    deleted_sessions = 0
    deleted_feedback = 0
    deleted_clusters = 0
    deleted_bridges = 0
    deleted_concepts = 0
    deleted_milestones = 0
    deleted_s3_objects = 0
    deleted_training_candidates = 0

    # Delete sessions + their feedback records + S3 audio
    sessions_resp = session_table.query(
        IndexName="child_id-timestamp-index",
        KeyConditionExpression=_key("child_id").eq(child_id)
    )
    for sess in sessions_resp.get("Items", []):
        sid = sess["session_id"]

        # Delete feedback records for this session
        fb_resp = feedback_table.query(
            IndexName="session_id-created_at-index",
            KeyConditionExpression=_key("session_id").eq(sid)
        )
        for fb in fb_resp.get("Items", []):
            feedback_table.delete_item(Key={"feedback_id": fb["feedback_id"]})
            deleted_feedback += 1

        # Delete S3 audio files for this session (child_id/session_id/*)
        try:
            s3_prefix = f"{child_id}/{sid}/"
            s3_resp = s3_client.list_objects_v2(Bucket=bucket, Prefix=s3_prefix)
            for obj in s3_resp.get("Contents", []):
                s3_client.delete_object(Bucket=bucket, Key=obj["Key"])
                deleted_s3_objects += 1
        except Exception as e:
            logger.warning(f"S3 cleanup for session {sid}: {e}")

        # Delete training candidates linked to this session (PII-linked)
        if training_candidate_table is not None:
            try:
                from boto3.dynamodb.conditions import Attr
                tc_resp = training_candidate_table.scan(
                    FilterExpression=Attr("session_id").eq(sid),
                    ProjectionExpression="candidate_id",
                )
                for tc in tc_resp.get("Items", []):
                    training_candidate_table.delete_item(
                        Key={"candidate_id": tc["candidate_id"]}
                    )
                    deleted_training_candidates += 1
            except Exception as e:
                logger.warning(f"TrainingCandidate cleanup for session {sid}: {e}")

        session_table.delete_item(Key={"session_id": sid})
        deleted_sessions += 1

    # Delete sound clusters
    clusters_resp = sound_cluster_table.query(
        IndexName="child_id-last_updated-index",
        KeyConditionExpression=_key("child_id").eq(child_id)
    )
    for cluster in clusters_resp.get("Items", []):
        sound_cluster_table.delete_item(Key={"cluster_id": cluster["cluster_id"]})
        deleted_clusters += 1

    # Delete semantic bridges
    bridges_resp = semantic_bridge_table.query(
        IndexName="child_id-index",
        KeyConditionExpression=_key("child_id").eq(child_id)
    )
    for bridge in bridges_resp.get("Items", []):
        semantic_bridge_table.delete_item(Key={"bridge_id": bridge["bridge_id"]})
        deleted_bridges += 1

    # Delete personal concept graph (child_id is PK)
    concepts_resp = concept_graph_table.query(
        KeyConditionExpression=_key("child_id").eq(child_id)
    )
    for concept in concepts_resp.get("Items", []):
        concept_graph_table.delete_item(
            Key={"child_id": child_id, "concept_id": concept["concept_id"]}
        )
        deleted_concepts += 1

    # Delete milestones (child_id is PK)
    milestones_resp = milestones_table.query(
        KeyConditionExpression=_key("child_id").eq(child_id)
    )
    for milestone in milestones_resp.get("Items", []):
        milestones_table.delete_item(
            Key={"child_id": child_id, "milestone_id": milestone["milestone_id"]}
        )
        deleted_milestones += 1

    # Delete child profile last
    child_profile_table.delete_item(Key={"child_id": child_id})

    return {
        "deleted_sessions": deleted_sessions,
        "deleted_feedback": deleted_feedback,
        "deleted_s3_objects": deleted_s3_objects,
        "deleted_training_candidates": deleted_training_candidates,
        "deleted_clusters": deleted_clusters,
        "deleted_bridges": deleted_bridges,
        "deleted_concepts": deleted_concepts,
        "deleted_milestones": deleted_milestones,
    }


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

    deleted = _delete_child_direct_data(child_id)

    # Audit log (no PII — child_id is a UUID, no name/birth_date logged)
    logger.info(
        "AUDIT_CHILD_DELETE child_id=%s user_id=%s sessions=%d feedback=%d "
        "s3_objects=%d training_candidates=%d clusters=%d bridges=%d "
        "concepts=%d milestones=%d",
        child_id, user_id,
        deleted.get("deleted_sessions", 0),
        deleted.get("deleted_feedback", 0),
        deleted.get("deleted_s3_objects", 0),
        deleted.get("deleted_training_candidates", 0),
        deleted.get("deleted_clusters", 0),
        deleted.get("deleted_bridges", 0),
        deleted.get("deleted_concepts", 0),
        deleted.get("deleted_milestones", 0),
    )
    return response(
        200,
        {
            "message": "Child profile and all personal data deleted",
            "deleted": deleted,
        },
        event,
    )


# =============================================================================
# DELETE /account — Delete all parent-owned child data
# =============================================================================
def delete_account(event: Dict) -> Dict:
    user_id = get_user_id(event)
    _key = boto3.dynamodb.conditions.Key

    children: List[Dict[str, Any]] = []
    query_kwargs: Dict[str, Any] = {
        "IndexName": "parent_id-index",
        "KeyConditionExpression": _key("parent_id").eq(user_id),
    }
    result = child_profile_table.query(**query_kwargs)
    children.extend(result.get("Items", []))
    while "LastEvaluatedKey" in result:
        result = child_profile_table.query(
            ExclusiveStartKey=result["LastEvaluatedKey"],
            **query_kwargs,
        )
        children.extend(result.get("Items", []))

    total_deleted_children = 0
    aggregate = {
        "deleted_sessions": 0,
        "deleted_feedback": 0,
        "deleted_s3_objects": 0,
        "deleted_training_candidates": 0,
        "deleted_clusters": 0,
        "deleted_bridges": 0,
        "deleted_concepts": 0,
        "deleted_milestones": 0,
    }
    for child in children:
        child_id = str(child.get("child_id") or "").strip()
        if not child_id:
            continue
        deleted = _delete_child_direct_data(child_id)
        total_deleted_children += 1
        for k in aggregate:
            aggregate[k] += int(deleted.get(k, 0) or 0)

    # Audit log (no PII — user_id is a Cognito sub, no names logged)
    logger.info(
        "AUDIT_ACCOUNT_DELETE user_id=%s children=%d sessions=%d "
        "s3_objects=%d training_candidates=%d",
        user_id, total_deleted_children,
        aggregate.get("deleted_sessions", 0),
        aggregate.get("deleted_s3_objects", 0),
        aggregate.get("deleted_training_candidates", 0),
    )
    return response(
        200,
        {
            "message": "Account-linked child data deleted",
            "deleted_children": total_deleted_children,
            "deleted": aggregate,
        },
        event,
    )


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
        insight_obj = s.get("insight", {}) if isinstance(s.get("insight"), dict) else {}
        emotion_confidence = insight_obj.get("emotion_confidence")
        if emotion_confidence is None:
            emotion_confidence = (insight_obj.get("probable_intent") or {}).get("confidence")

        summaries.append({
            "session_id": s["session_id"],
            "timestamp": s.get("timestamp"),
            "deviation_level": s.get("deviation_level", "none"),
            "feature_scores": s.get("feature_scores", {}),
            "cluster_id": s.get("cluster_id"),
            "insight_summary": {
                "display_type": insight_obj.get("display_type"),
                "headline": insight_obj.get("headline"),
                "headline_icon": insight_obj.get("headline_icon"),
                "is_adult": bool(insight_obj.get("is_adult", False)),
                "emotion": insight_obj.get("emotion"),
                "emotion_confidence": emotion_confidence,
                # Backward compat for old sessions
                "probable_intent": insight_obj.get("probable_intent"),
                "suggested_response": insight_obj.get("suggested_response"),
            } if insight_obj else None,
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

    # Enforce ownership + age boundary check (0-24 months) before creating upload session
    profile_resp = child_profile_table.get_item(Key={"child_id": child_id})
    if "Item" not in profile_resp:
        return response(404, {"error": "Child not found"}, event)
    profile = _decimal_to_float(profile_resp["Item"])
    if profile.get("parent_id") != user_id:
        return response(403, {"error": "Not authorized for this child profile"}, event)
    birth_date = str(profile.get("birth_date") or "").strip()
    if not birth_date:
        return response(400, {"error": "Child birth_date is missing. Please update the profile first."}, event)
    try:
        birth = date.fromisoformat(birth_date)
    except ValueError:
        return response(400, {"error": "Child birth_date is invalid. Please update the profile."}, event)
    today = datetime.now(timezone.utc).date()
    age_days = (today - birth).days
    if age_days < 0:
        return response(400, {"error": "Child birth_date cannot be in the future"}, event)
    if age_days > MAX_SUPPORTED_CHILD_AGE_DAYS:
        return response(
            400,
            {"error": "This system supports only children aged 0-24 months. Recording rejected."},
            event,
        )

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    s3_key = f"{child_id}/{session_id}/audio.webm"  # Browser MediaRecorder outputs WebM

    # Generate presigned URL for direct upload
    # Content-Type must match what frontend sends (audio/webm from MediaRecorder)
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": s3_key,
            "ContentType": "audio/webm",
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
        "instructions": "PUT audio/webm file to upload_url, then call start_processing",
    }, event)


# =============================================================================
# POST /session/{session_id}/start — Start processing pipeline
# =============================================================================
def start_processing(event: Dict) -> Dict:
    user_id = get_user_id(event)
    session_id = event["pathParameters"]["session_id"]
    body = json.loads(event.get("body") or "{}")

    session_resp = session_table.get_item(Key={"session_id": session_id})
    if "Item" not in session_resp:
        return response(404, {"error": "Session not found"}, event)

    session = _decimal_to_float(session_resp["Item"])
    if session.get("parent_id") != user_id:
        return response(403, {"error": "Not authorized for this session"}, event)
    child_id = session["child_id"]
    s3_audio_path = session["s3_audio_path"]

    # Enforce ownership + age boundary check (0-24 months) at pipeline start
    profile_resp = child_profile_table.get_item(Key={"child_id": child_id})
    if "Item" not in profile_resp:
        return response(404, {"error": "Child not found"}, event)
    profile = _decimal_to_float(profile_resp["Item"])
    if profile.get("parent_id") != user_id:
        return response(403, {"error": "Not authorized for this child profile"}, event)
    birth_date = str(profile.get("birth_date") or "").strip()
    if not birth_date:
        return response(400, {"error": "Child birth_date is missing. Please update the profile first."}, event)
    try:
        birth = date.fromisoformat(birth_date)
    except ValueError:
        return response(400, {"error": "Child birth_date is invalid. Please update the profile."}, event)
    today = datetime.now(timezone.utc).date()
    age_days = (today - birth).days
    if age_days < 0:
        return response(400, {"error": "Child birth_date cannot be in the future"}, event)
    if age_days > MAX_SUPPORTED_CHILD_AGE_DAYS:
        return response(
            400,
            {"error": "This system supports only children aged 0-24 months. Recording rejected."},
            event,
        )

    # Get Step Function ARN from SSM Parameter Store (resolves circular dependency)
    try:
        sfn_arn = get_step_function_arn()
    except RuntimeError as e:
        logger.error(str(e))
        return response(500, {"error": str(e)}, event)

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
def _build_raw_debug_from_session(session: Dict, insight: Dict) -> Dict[str, Any]:
    """Build raw debug payload from stored session fields (supports older sessions)."""
    return {
        "recording": {
            "sound_type": session.get("sound_type"),
            "is_adult": session.get("is_adult", False),
            "age_days": session.get("age_days_at_recording"),
            "duration_seconds": session.get("duration_seconds"),
            "fast_reject": session.get("fast_reject", False),
            "fast_reject_reasons": session.get("fast_reject_reasons", []),
        },
        "quality_gate": session.get("quality_gate", {}),
        "routing": session.get("routing", {}),
        "sound_classification": session.get("sound_classification", {}),
        "sound_summary": session.get("sound_summary", {}),
        "sound_features": session.get("sound_features", {}),
        "diarization": session.get("diarization", {}),
        "biological": session.get("biological", {}),
        "age_classification": session.get("age_classification", {}),
        "analysis_output": {
            "display_type": insight.get("display_type"),
            "headline": insight.get("headline"),
            "emotion": insight.get("emotion"),
            "emotion_confidence": insight.get("emotion_confidence"),
            "top_emotions": insight.get("top_emotions", []),
            "dunstan_sound": insight.get("dunstan_sound"),
            "dunstan_ambiguous": insight.get("dunstan_ambiguous", False),
            "also_possible": insight.get("also_possible", []),
        },
        "cry_model_debug": insight.get("debug_payload", {}),
    }


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
        return response(202, {"status": "processing", "message": "Session is still being processed"}, event)
    if not isinstance(insight, dict):
        insight = {}
    else:
        insight = dict(insight)

    # Ensure raw debug is available for both new and older sessions.
    if not isinstance(insight.get("raw_debug"), dict):
        insight["raw_debug"] = _build_raw_debug_from_session(session, insight)

    # Fetch child name for personalization
    child_id = session.get("child_id", "")
    child_name = ""
    if child_id:
        try:
            profile_resp = child_profile_table.get_item(
                Key={"child_id": child_id},
                ProjectionExpression="#n",
                ExpressionAttributeNames={"#n": "name"},
            )
            child_name = profile_resp.get("Item", {}).get("name", "")
        except Exception:
            pass

    return response(200, {
        "session_id": session_id,
        "child_id": child_id,
        "child_name": child_name,
        "insight": insight,
        "timestamp": session.get("timestamp"),
        # Phase 1: Biological validation summary
        "biological": {
            k: v for k, v in (session.get("biological") or {}).items()
            if k in ("vtl_cm", "f0_hz", "is_infant", "vtl_zone", "bio_confidence")
        },
    }, event)


# =============================================================================
# POST /session/{session_id}/feedback — Submit feedback
# =============================================================================
def submit_feedback(event: Dict) -> Dict:
    session_id = event["pathParameters"]["session_id"]
    body = json.loads(event.get("body") or "{}")

    feedback_type = str(body.get("feedback_type") or "cry_emotion").strip().lower()
    if feedback_type != "cry_emotion":
        return response(400, {"error": "Only cry emotion feedback is supported"}, event)

    confirmed_emotion = str(body.get("confirmed_emotion", "") or "").strip()
    if not confirmed_emotion:
        confirmed_emotions = body.get("confirmed_emotions") or []
        if isinstance(confirmed_emotions, list) and confirmed_emotions:
            confirmed_emotion = str(confirmed_emotions[0] or "").strip()
    if not confirmed_emotion:
        return response(400, {"error": "confirmed_emotion is required for cry feedback"}, event)

    notes = str(body.get("notes", "") or "").strip()[:500]
    feedback_payload = {
        "session_id": session_id,
        "feedback_type": "cry_emotion",
        "confirmed_emotion": confirmed_emotion,
        "was_correct": bool(body.get("was_correct", True)),
        "notes": notes,
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
# GET /status — System status (AI mode, feature flags)
# =============================================================================
def get_status(event: Dict) -> Dict:
    endpoint_configured = bool(SAGEMAKER_HUBERT_ENDPOINT)
    sagemaker_enabled = bool(USE_SAGEMAKER_INTENT_ENDPOINT and endpoint_configured)
    return response(200, {
        "sagemaker_enabled": sagemaker_enabled,
        "sagemaker_flag_enabled": bool(USE_SAGEMAKER_INTENT_ENDPOINT),
        "hubert_endpoint_configured": endpoint_configured,
        "ai_mode": "Advanced" if sagemaker_enabled else "Basic",
    }, event)


# =============================================================================
# GET /child/{child_id}/training-stats — Training contribution counts
# =============================================================================
def get_training_stats(event: Dict) -> Dict:
    child_id = event["pathParameters"]["child_id"]
    user_id = get_user_id(event)

    # Verify ownership
    profile_resp = child_profile_table.get_item(Key={"child_id": child_id})
    if "Item" not in profile_resp:
        return response(404, {"error": "Child not found"}, event)
    if profile_resp["Item"].get("parent_id") != user_id:
        return response(403, {"error": "Not authorized"}, event)

    child_count = 0
    total_count = 0

    if training_features_table:
        try:
            # Scan for confirmed samples — count child-specific and total
            scan_kwargs = {
                "Select": "COUNT",
                "FilterExpression": "is_confirmed = :true",
                "ExpressionAttributeValues": {":true": True},
            }
            # Total count
            resp = training_features_table.scan(**scan_kwargs)
            total_count = resp.get("Count", 0)
            while resp.get("LastEvaluatedKey"):
                resp = training_features_table.scan(
                    **scan_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"]
                )
                total_count += resp.get("Count", 0)

            # Child-specific count
            child_kwargs = {
                "Select": "COUNT",
                "FilterExpression": "is_confirmed = :true AND child_id = :cid",
                "ExpressionAttributeValues": {":true": True, ":cid": child_id},
            }
            resp = training_features_table.scan(**child_kwargs)
            child_count = resp.get("Count", 0)
            while resp.get("LastEvaluatedKey"):
                resp = training_features_table.scan(
                    **child_kwargs, ExclusiveStartKey=resp["LastEvaluatedKey"]
                )
                child_count += resp.get("Count", 0)
        except Exception as e:
            logger.warning(f"Training stats query failed: {e}")

    return response(200, {
        "child_count": child_count,
        "total_count": total_count,
    }, event)


# =============================================================================
# Router
# =============================================================================
ROUTES = {
    ("GET", "/child"): list_children,
    ("POST", "/child"): create_child,
    ("DELETE", "/child/{child_id}"): delete_child,
    ("DELETE", "/account"): delete_account,
    ("GET", "/child/{child_id}/sessions"): list_sessions,
    ("GET", "/child/{child_id}/training-stats"): get_training_stats,
    ("GET", "/status"): get_status,
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
