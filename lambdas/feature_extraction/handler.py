"""
Qleam — Feature Extraction Lambda
Extracts acoustic features from uploaded audio and updates child baseline.

Trigger: Step Function first state (after S3 upload)
Input:  { child_id, session_id, s3_audio_path }
Output: { status, session_id, feature_scores, embedding_vector, deviation }
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

import boto3
from boto3.dynamodb.conditions import Key

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    ALPHA_VALUE,
    CHILD_PROFILE_TABLE,
    MIN_SESSIONS_FOR_DEVIATION,
    S3_BUCKET_NAME,
    SESSION_TABLE,
)
from normalization import (
    compute_deviation_level,
    compute_readiness_score,
    update_feature_baselines,
)

# Audio utils imported lazily (requires librosa layer)
from audio_utils import download_audio_from_s3, extract_all_features

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# AWS clients
dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)


def _float_to_decimal(obj: Any) -> Any:
    """Convert floats to Decimal for DynamoDB. Handles numpy floats too."""
    # Handle all numeric types (float, numpy.float32, numpy.float64, int, etc.)
    if isinstance(obj, (int, float)):
        return Decimal(str(obj))
    # Handle numpy numeric types without requiring numpy import
    if hasattr(obj, 'item'):  # numpy types have an 'item' method
        try:
            return Decimal(str(obj.item()))
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, Decimal):
        return obj
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


def _decimal_to_float(obj: Any) -> Any:
    """Convert Decimal back to float from DynamoDB."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def get_or_create_child_profile(child_id: str) -> Dict:
    """Fetch child profile or create a new one."""
    response = child_profile_table.get_item(Key={"child_id": child_id})
    
    if "Item" in response:
        return _decimal_to_float(response["Item"])
    
    # Create new profile
    now = datetime.now(timezone.utc).isoformat()
    new_profile = {
        "child_id": child_id,
        "baseline_features": {},
        "readiness_score": 0.5,
        "language_maturity_level": "pre-linguistic",
        "session_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    child_profile_table.put_item(Item=_float_to_decimal(new_profile))
    logger.info(f"Created new child profile for {child_id}")
    return new_profile


def update_child_profile(child_id: str, new_baselines: Dict, readiness_score: float, session_count: int):
    """Update child profile with new baselines and readiness score."""
    now = datetime.now(timezone.utc).isoformat()
    
    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression=(
            "SET baseline_features = :bf, "
            "readiness_score = :rs, "
            "session_count = :sc, "
            "updated_at = :ua"
        ),
        ExpressionAttributeValues={
            ":bf": _float_to_decimal(new_baselines),
            ":rs": Decimal(str(readiness_score)),
            ":sc": session_count,
            ":ua": now,
        }
    )


def save_session(
    session_id: str,
    child_id: str,
    s3_audio_path: str,
    feature_scores: Dict,
    embedding_vector: list,
    deviation: Dict,
    duration_seconds: float,
):
    """Save session record to DynamoDB."""
    now = datetime.now(timezone.utc).isoformat()
    
    session_item = {
        "session_id": session_id,
        "child_id": child_id,
        "s3_audio_path": s3_audio_path,
        "feature_scores": feature_scores,
        "embedding_vector": embedding_vector,
        "deviation_flag": deviation.get("deviation_flag", False),
        "deviation_level": deviation.get("deviation_level", "none"),
        "deviation_score": deviation.get("deviation_score", 0.0),
        "duration_seconds": duration_seconds,
        "processed": True,
        "timestamp": now,
    }
    
    session_table.put_item(Item=_float_to_decimal(session_item))
    logger.info(f"Saved session {session_id}")


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Feature Extraction Lambda handler.
    
    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "s3_audio_path": str
        }
    
    Returns:
        {
            "status": "features_extracted",
            "session_id": str,
            "child_id": str,
            "feature_scores": dict,
            "embedding_vector": list,
            "deviation": dict
        }
    """
    logger.info(f"Feature extraction started: {json.dumps({k: v for k, v in event.items() if k != 'embedding_vector'})}")
    
    child_id = event["child_id"]
    session_id = event["session_id"]
    s3_audio_path = event["s3_audio_path"]
    
    # 1. Download audio from S3
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    audio_bytes = download_audio_from_s3(bucket, s3_audio_path)
    
    # 2. Extract features
    extraction_result = extract_all_features(audio_bytes)
    feature_scores = extraction_result["feature_scores"]
    embedding_vector = extraction_result["embedding_vector"]
    duration_seconds = extraction_result["duration_seconds"]
    
    logger.info(f"Extracted features: {feature_scores}")
    
    # 3. Get or create child profile
    profile = get_or_create_child_profile(child_id)
    previous_baselines = profile.get("baseline_features", {})
    session_count = profile.get("session_count", 0) + 1
    
    # 4. Update EMA baselines
    alpha = float(os.environ.get("ALPHA_VALUE", str(ALPHA_VALUE)))
    new_baselines = update_feature_baselines(previous_baselines, feature_scores, alpha)
    
    # 5. Compute deviation
    deviation = compute_deviation_level(
        feature_scores,
        previous_baselines,
        session_count,
        MIN_SESSIONS_FOR_DEVIATION
    )
    
    # 6. Compute readiness score
    readiness_score = compute_readiness_score(feature_scores)
    
    # 7. Update child profile
    update_child_profile(child_id, new_baselines, readiness_score, session_count)
    
    # 8. Save session record
    save_session(
        session_id=session_id,
        child_id=child_id,
        s3_audio_path=s3_audio_path,
        feature_scores=feature_scores,
        embedding_vector=embedding_vector,
        deviation=deviation,
        duration_seconds=duration_seconds,
    )
    
    logger.info(f"Feature extraction complete for session {session_id}")
    
    return {
        "status": "features_extracted",
        "session_id": session_id,
        "child_id": child_id,
        "feature_scores": feature_scores,
        "embedding_vector": embedding_vector,
        "deviation": deviation,
        "readiness_score": readiness_score,
        "duration_seconds": duration_seconds,
    }
