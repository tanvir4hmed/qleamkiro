"""
Qleam — Audio Classifier Lambda (formerly Feature Extraction)
First step in the pipeline: classifies audio and routes to appropriate analysis.

Simplified pipeline:
  1. Download + decode audio
  2. Quality gate (basic validation)
  3. Diarization (speaker segmentation)
  4. Sound classification (speech/cry/laugh/silence/noise)
  5. Adult/baby voice detection
  6. Basic feature extraction (embedding for clustering + private language)
  7. Route decision for downstream lambdas

Trigger: Step Function first state (after S3 upload)
Input:  { child_id, session_id, s3_audio_path, session_context? }
Output: { status, session_id, sound_type, is_adult, features, routing }
"""
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3
import numpy as np

# Add shared utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    ALPHA_VALUE,
    CHILD_PROFILE_TABLE,
    S3_BUCKET_NAME,
    SESSION_TABLE,
)
from audio_utils import (
    audio_quality_gate,
    biological_validation,
    download_audio_from_s3,
    extract_all_features_from_array,
    load_audio_from_bytes,
    voice_activity_detection,
)
from diarization import diarize, extract_baby_audio
from age_classifier import classify_probabilistic
from sound_classifier import classify_sound, classify_segments, aggregate_sound_types

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)


def _float_to_decimal(obj: Any) -> Any:
    import math
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


def _compute_age_days(birth_date_str: Optional[str]) -> Optional[int]:
    if not birth_date_str:
        return None
    try:
        birth = date.fromisoformat(birth_date_str)
        today = datetime.now(timezone.utc).date()
        return max(0, (today - birth).days)
    except (ValueError, TypeError):
        return None


def _enhance_baby_signal(y: np.ndarray) -> np.ndarray:
    """Lightweight denoise for baby-segment audio."""
    if y is None or len(y) == 0:
        return y
    y = y - float(np.mean(y))
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 1e-8:
        y = y / peak
    mag = np.abs(y)
    noise_floor = float(np.percentile(mag, 20))
    if noise_floor > 0.0:
        y = np.where(mag < noise_floor, y * 0.35, y)
    y_pre = np.empty_like(y)
    y_pre[0] = y[0]
    y_pre[1:] = y[1:] - 0.95 * y[:-1]
    return y_pre


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Audio Classifier Lambda handler.

    Simplified pipeline:
      1. Download + decode audio
      2. Quality gate
      3. Diarization + baby extraction
      4. Sound classification (speech/cry/laugh/silence/noise)
      5. Adult/baby detection
      6. Feature extraction (embedding)
      7. Save session + return routing info
    """
    logger.info(f"Audio classifier started: {json.dumps({k: v for k, v in event.items() if k != 'embedding_vector'})}")

    child_id = event["child_id"]
    session_id = event["session_id"]
    s3_audio_path = event["s3_audio_path"]
    session_context = event.get("session_context") or {}

    # --- 1. Download and decode audio ---
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    audio_bytes = download_audio_from_s3(bucket, s3_audio_path)
    decoded_audio, sample_rate = load_audio_from_bytes(audio_bytes, target_sr=22050)
    duration_seconds = round(len(decoded_audio) / max(sample_rate, 1), 2)

    # VAD trim
    audio_array = voice_activity_detection(decoded_audio, sample_rate)
    if len(audio_array) < sample_rate * 0.5:
        audio_array = decoded_audio

    # --- 2. Quality gate ---
    quality_gate = {}
    try:
        quality_gate = audio_quality_gate(audio_array, sample_rate, duration_seconds)
        if not quality_gate.get("passed", True):
            logger.warning(f"Quality gate issues: {quality_gate.get('issues', [])}")
    except Exception as e:
        logger.warning(f"Quality gate error: {e}")

    # Check for critical failures (no signal, too short)
    critical = _check_critical_issues(quality_gate)
    if critical:
        return _save_and_return_fast_reject(
            child_id, session_id, s3_audio_path, duration_seconds,
            quality_gate, session_context, critical,
        )

    # --- 3. Feature extraction (embedding for clustering + private language) ---
    extraction = extract_all_features_from_array(audio_array, sample_rate, apply_vad=False)
    feature_scores = extraction["feature_scores"]
    embedding_vector = extraction["embedding_vector"]

    # --- 4. Diarization ---
    diarization_result = {}
    baby_audio = audio_array
    try:
        diarization_result = diarize(audio_array, sample_rate)
        baby_audio = extract_baby_audio(audio_array, sample_rate, diarization_result)
        baby_audio = _enhance_baby_signal(baby_audio)
        logger.info(f"Diarization: {diarization_result.get('total_segments', 0)} segments, "
                     f"baby_fraction={diarization_result.get('baby_audio_fraction', 0):.0%}")
    except Exception as e:
        logger.warning(f"Diarization error: {e}")
        baby_audio = audio_array

    # --- 5. Sound classification ---
    sound_result = classify_sound(baby_audio, sample_rate, duration_s=duration_seconds)
    sound_type = sound_result["primary_type"]
    logger.info(f"Sound classification: type={sound_type} conf={sound_result['confidence']}")

    # Per-segment classification
    segment_classifications = []
    if diarization_result.get("segments"):
        try:
            segment_classifications = classify_segments(
                audio_array, sample_rate, diarization_result["segments"]
            )
        except Exception as e:
            logger.warning(f"Segment classification error: {e}")

    sound_summary = aggregate_sound_types(segment_classifications) if segment_classifications else {
        "dominant_type": sound_type,
        "has_speech": sound_type == "speech",
        "has_cry": sound_type == "cry",
        "has_laugh": sound_type == "laugh",
    }

    # --- 6. Adult/baby detection ---
    bio_result = {}
    age_classification = {}
    try:
        bio_result = biological_validation(baby_audio, sample_rate)
    except Exception as e:
        logger.warning(f"Bio validation error: {e}")

    try:
        from rich_features import extract_rich_features
        rich_features = extract_rich_features(baby_audio, sample_rate,
                                               formants=bio_result.get("formants"))
        age_classification = classify_probabilistic(rich_features, bio_result or {})
        logger.info(f"Age classifier: class={age_classification.get('final_class')} "
                     f"conf={age_classification.get('confidence', 0):.3f}")
    except Exception as e:
        logger.warning(f"Age classification error: {e}")
        rich_features = {}

    # Determine adult/baby
    is_adult = _determine_is_adult(bio_result, age_classification)

    # --- 7. Get child profile for age info ---
    profile = _get_child_profile(child_id)
    age_days = _compute_age_days(profile.get("birth_date"))

    # Determine routing
    routing = _build_routing(
        sound_type=sound_type,
        sound_summary=sound_summary,
        is_adult=is_adult,
        age_days=age_days,
    )

    # --- 8. Save session ---
    now = datetime.now(timezone.utc).isoformat()
    session_item = {
        "session_id": session_id,
        "child_id": child_id,
        "s3_audio_path": s3_audio_path,
        "timestamp": now,
        "duration_seconds": duration_seconds,
        "processed": True,
        # Sound classification
        "sound_type": sound_type,
        "sound_classification": sound_result,
        "sound_summary": sound_summary,
        "segment_classifications": segment_classifications[:10],
        # Voice detection
        "is_adult": is_adult,
        "biological": bio_result,
        "age_classification": age_classification,
        # Features
        "feature_scores": feature_scores,
        "embedding_vector": embedding_vector,
        "sound_features": sound_result.get("features", {}),
        "rich_features": rich_features,
        # Metadata
        "quality_gate": quality_gate,
        "diarization": diarization_result,
        "age_days_at_recording": age_days,
        "session_context": session_context,
        "routing": routing,
    }
    session_table.put_item(Item=_float_to_decimal(session_item))
    logger.info(f"Session saved: {session_id} type={sound_type} adult={is_adult}")

    return {
        "status": "classified",
        "session_id": session_id,
        "child_id": child_id,
        "sound_type": sound_type,
        "is_adult": is_adult,
        "sound_classification": sound_result,
        "sound_summary": sound_summary,
        "embedding_vector": embedding_vector,
        "feature_scores": feature_scores,
        "sound_features": sound_result.get("features", {}),
        "rich_features": rich_features,
        "biological": bio_result,
        "age_classification": age_classification,
        "age_days": age_days,
        "duration_seconds": duration_seconds,
        "quality_gate": quality_gate,
        "routing": routing,
        "session_context": session_context,
        "s3_audio_path": s3_audio_path,
        "fast_reject": False,
    }


def _determine_is_adult(bio_result: Dict, age_classification: Dict) -> bool:
    """Determine if the speaker is an adult."""
    # Check age classifier first (more comprehensive)
    if age_classification:
        is_adult_cls = age_classification.get("is_adult", False)
        conf = float(age_classification.get("confidence", 0))
        if is_adult_cls and conf >= 0.60:
            return True

    # Check bio validation
    if bio_result:
        if bio_result.get("is_adult", False) and bio_result.get("bio_confidence", 0) >= 0.55:
            return True
        if bio_result.get("mimicry_suspected", False):
            return True

    return False


def _build_routing(
    sound_type: str,
    sound_summary: Dict,
    is_adult: bool,
    age_days: Optional[int],
) -> Dict[str, Any]:
    """Build routing decision for downstream lambdas."""
    # Determine which pipelines to run
    run_transcription = False
    run_cry_analysis = False
    run_laugh_detection = False

    if sound_summary.get("has_speech", False) or sound_type == "speech":
        run_transcription = True
    if sound_summary.get("has_cry", False) or sound_type == "cry":
        run_cry_analysis = True
    if sound_summary.get("has_laugh", False) or sound_type == "laugh":
        run_laugh_detection = True

    # Mixed sound: run all relevant pipelines
    if sound_type == "mixed":
        if sound_summary.get("has_speech"):
            run_transcription = True
        if sound_summary.get("has_cry"):
            run_cry_analysis = True
        if sound_summary.get("has_laugh"):
            run_laugh_detection = True

    return {
        "sound_type": sound_type,
        "is_adult": is_adult,
        "run_transcription": run_transcription,
        "run_cry_analysis": run_cry_analysis,
        "run_laugh_detection": run_laugh_detection,
        "age_days": age_days,
    }


def _check_critical_issues(quality_gate: Dict) -> list:
    """Check for critical quality issues that warrant fast rejection."""
    if not isinstance(quality_gate, dict):
        return []
    issues = quality_gate.get("issues", []) or []
    critical = [i for i in issues if str(i).startswith(("no_signal", "too_short:"))]
    return critical


def _get_child_profile(child_id: str) -> Dict:
    """Fetch child profile."""
    try:
        response = child_profile_table.get_item(Key={"child_id": child_id})
        if "Item" in response:
            return _decimal_to_float(response["Item"])
    except Exception as e:
        logger.warning(f"Failed to get child profile: {e}")

    return {"child_id": child_id}


def _save_and_return_fast_reject(
    child_id, session_id, s3_audio_path, duration_seconds,
    quality_gate, session_context, critical_issues,
) -> Dict:
    """Save and return a fast-reject result."""
    profile = _get_child_profile(child_id)
    age_days = _compute_age_days(profile.get("birth_date"))
    now = datetime.now(timezone.utc).isoformat()

    session_item = {
        "session_id": session_id,
        "child_id": child_id,
        "s3_audio_path": s3_audio_path,
        "timestamp": now,
        "duration_seconds": duration_seconds,
        "processed": True,
        "sound_type": "silence",
        "is_adult": False,
        "quality_gate": quality_gate,
        "age_days_at_recording": age_days,
        "session_context": session_context,
        "routing": {"sound_type": "silence", "is_adult": False,
                     "run_transcription": False, "run_cry_analysis": False,
                     "run_laugh_detection": False},
        "fast_reject": True,
        "fast_reject_reasons": critical_issues,
    }
    session_table.put_item(Item=_float_to_decimal(session_item))

    return {
        "status": "classified",
        "session_id": session_id,
        "child_id": child_id,
        "sound_type": "silence",
        "is_adult": False,
        "fast_reject": True,
        "fast_reject_reasons": critical_issues,
        "routing": session_item["routing"],
        "duration_seconds": duration_seconds,
        "embedding_vector": [],
        "feature_scores": {},
        "sound_features": {},
        "sound_classification": {},
        "sound_summary": {},
        "biological": {},
        "age_classification": {},
        "age_days": age_days,
        "quality_gate": quality_gate,
        "session_context": session_context,
        "s3_audio_path": s3_audio_path,
    }
