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
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

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
    developmental_stage_from_age,
    update_feature_baselines,
)

# Audio utils imported lazily (requires librosa layer)
from audio_utils import (
    audio_quality_gate,
    biological_validation,
    download_audio_from_s3,
    extract_all_features,
)

# Configure logging
log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

# AWS clients
dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)


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
            ":rs": _float_to_decimal(readiness_score),
            ":sc": _float_to_decimal(session_count),
            ":ua": now,
        }
    )


def compute_age_days(birth_date_str: Optional[str]) -> Optional[int]:
    """Compute age in days from birth_date ISO string to today (UTC)."""
    if not birth_date_str:
        return None
    try:
        birth = date.fromisoformat(birth_date_str)
        today = datetime.now(timezone.utc).date()
        return max(0, (today - birth).days)
    except (ValueError, TypeError):
        return None


def save_session(
    session_id: str,
    child_id: str,
    s3_audio_path: str,
    feature_scores: Dict,
    embedding_vector: list,
    deviation: Dict,
    duration_seconds: float,
    quality_gate: Optional[Dict] = None,
    biological: Optional[Dict] = None,
    age_days_at_recording: Optional[int] = None,
    developmental_stage: str = "UNKNOWN",
    developmental_mode: str = "PRE_LINGUISTIC",
):
    """Save session record to DynamoDB with Phase 1 quality and bio fields."""
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
        # Phase 1 additions
        "quality_gate": quality_gate or {},
        "biological": biological or {},
        "age_days_at_recording": age_days_at_recording,
        "developmental_stage": developmental_stage,
        "developmental_mode": developmental_mode,
    }

    session_table.put_item(Item=_float_to_decimal(session_item))
    logger.info(f"Saved session {session_id}")


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Feature Extraction Lambda handler — Phase 1 updated.

    Pipeline:
      0. Download audio from S3
      1. [Phase 1] Audio quality gate (SNR, clipping, silence, duration, Lombard)
      2. Extract acoustic features (4 scores + embedding)
      3. [Phase 1] Biological validation (formants, VTL, infant/adult classifier)
      4. Get child profile → compute age + developmental stage from birth_date
      5. Update EMA baselines, deviation, readiness
      6. Save session (with all Phase 1 metadata)

    Args:
        event: { "child_id": str, "session_id": str, "s3_audio_path": str }
    """
    logger.info(f"Feature extraction started: {json.dumps({k: v for k, v in event.items() if k != 'embedding_vector'})}")

    child_id = event["child_id"]
    session_id = event["session_id"]
    s3_audio_path = event["s3_audio_path"]

    # 0. Download audio from S3
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    audio_bytes = download_audio_from_s3(bucket, s3_audio_path)

    # 1. Extract features (includes loading + VAD)
    extraction_result = extract_all_features(audio_bytes)
    feature_scores = extraction_result["feature_scores"]
    embedding_vector = extraction_result["embedding_vector"]
    duration_seconds = extraction_result["duration_seconds"]
    audio_array = extraction_result.get("audio_array")
    sample_rate = extraction_result.get("sample_rate", 22050)

    logger.info(f"Extracted features: {feature_scores}")

    # 2. [Phase 1] Audio quality gate
    quality_gate_result = {}
    if audio_array is not None:
        try:
            quality_gate_result = audio_quality_gate(audio_array, sample_rate, duration_seconds)
            if not quality_gate_result["passed"]:
                logger.warning(f"Quality gate failed for session {session_id}: {quality_gate_result['issues']}")
            else:
                logger.info(f"Quality gate passed: SNR={quality_gate_result['snr_db']}dB, silence={quality_gate_result['silence_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Quality gate error (non-blocking): {e}")

    # 3. [Phase 1] Biological validation
    bio_result = {}
    if audio_array is not None:
        try:
            bio_result = biological_validation(audio_array, sample_rate)
            if bio_result.get("mimicry_suspected"):
                logger.warning(f"Adult mimicry suspected for session {session_id}: {bio_result['evidence']}")
            else:
                logger.info(f"Bio validation: is_infant={bio_result.get('is_infant')}, VTL={bio_result.get('vtl_cm')}cm, F0={bio_result.get('f0_hz')}Hz")
        except Exception as e:
            logger.warning(f"Biological validation error (non-blocking): {e}")

    # 4. Get child profile → age + developmental stage
    profile = get_or_create_child_profile(child_id)
    previous_baselines = profile.get("baseline_features", {})
    session_count = profile.get("session_count", 0) + 1

    birth_date_str = profile.get("birth_date")
    age_days = compute_age_days(birth_date_str)
    stage_info = developmental_stage_from_age(age_days)
    developmental_stage = stage_info["stage"]
    developmental_mode = stage_info["mode"]

    logger.info(f"Child age: {age_days} days → stage={developmental_stage}, mode={developmental_mode}")

    # 5. Update EMA baselines
    alpha = float(os.environ.get("ALPHA_VALUE", str(ALPHA_VALUE)))
    new_baselines = update_feature_baselines(previous_baselines, feature_scores, alpha)

    # 6. Compute deviation
    deviation = compute_deviation_level(
        feature_scores,
        previous_baselines,
        session_count,
        MIN_SESSIONS_FOR_DEVIATION,
    )

    # 7. Compute readiness score
    readiness_score = compute_readiness_score(feature_scores)

    # 8. Update child profile (also store developmental_stage)
    update_child_profile(child_id, new_baselines, readiness_score, session_count)

    # 9. Save session record with Phase 1 metadata
    save_session(
        session_id=session_id,
        child_id=child_id,
        s3_audio_path=s3_audio_path,
        feature_scores=feature_scores,
        embedding_vector=embedding_vector,
        deviation=deviation,
        duration_seconds=duration_seconds,
        quality_gate=quality_gate_result,
        biological=bio_result,
        age_days_at_recording=age_days,
        developmental_stage=developmental_stage,
        developmental_mode=developmental_mode,
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
        "quality_gate": quality_gate_result,
        "biological": bio_result,
        "developmental_stage": developmental_stage,
        "developmental_mode": developmental_mode,
    }
