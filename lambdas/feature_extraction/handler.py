"""
Qleam — Feature Extraction Lambda
Extracts acoustic features from uploaded audio and updates child baseline.

Trigger: Step Function first state (after S3 upload)
Input:  { child_id, session_id, s3_audio_path, session_context? }
Output: { status, session_id, feature_scores, rich_features, embedding_vector, deviation }
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
    audio_stage_hint_from_bio,
    update_feature_baselines,
)

# Audio utils imported lazily (requires librosa layer)
from audio_utils import (
    audio_quality_gate,
    biological_validation,
    download_audio_from_s3,
    extract_all_features,
)

# Phase 2 imports
from diarization import diarize, extract_baby_audio
from speaker_identity import determine_routing, verify_enrolled_baby

# Phase 3 imports
from rich_features import extract_rich_features

# Phase 4 imports — probabilistic age classifier
from age_classifier import classify_probabilistic, age_class_to_stage_hint

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


def update_child_profile(
    child_id: str,
    new_baselines: Dict,
    readiness_score: float,
    session_count: int,
    developmental_stage: str = "UNKNOWN",
    developmental_mode: str = "PRE_LINGUISTIC",
):
    """Update child profile with new baselines, readiness, and current developmental stage."""
    now = datetime.now(timezone.utc).isoformat()

    child_profile_table.update_item(
        Key={"child_id": child_id},
        UpdateExpression=(
            "SET baseline_features = :bf, "
            "readiness_score = :rs, "
            "session_count = :sc, "
            "developmental_stage = :ds, "
            "developmental_mode = :dm, "
            "updated_at = :ua"
        ),
        ExpressionAttributeValues={
            ":bf": _float_to_decimal(new_baselines),
            ":rs": _float_to_decimal(readiness_score),
            ":sc": _float_to_decimal(session_count),
            ":ds": developmental_stage,
            ":dm": developmental_mode,
            ":ua": now,
        },
    )


def load_historical_embeddings(
    child_id: str,
    current_session_id: str,
    limit: int = 10,
) -> list:
    """
    Load embedding vectors from the most recent sessions for this child.
    Excludes the current session (which has no embedding yet when this runs).

    Returns:
        List of embedding vectors (each a List[float])
    """
    response = session_table.query(
        IndexName="child_id-timestamp-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
        ScanIndexForward=False,  # Most recent first
        Limit=limit + 1,
        ProjectionExpression="session_id, embedding_vector",
    )

    embeddings = []
    for item in response.get("Items", []):
        if item.get("session_id") == current_session_id:
            continue  # Skip current session (shouldn't have embedding yet anyway)
        raw = item.get("embedding_vector")
        if raw:
            embeddings.append([float(v) for v in raw])

    return embeddings[:limit]


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
    diarization: Optional[Dict] = None,
    enrollment: Optional[Dict] = None,
    routing: Optional[Dict] = None,
    rich_features: Optional[Dict] = None,
    session_context: Optional[Dict] = None,
    age_classification: Optional[Dict] = None,
):
    """Save session record to DynamoDB with Phase 1–4 metadata."""
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
        # Phase 1
        "quality_gate": quality_gate or {},
        "biological": biological or {},
        "age_days_at_recording": age_days_at_recording,
        "developmental_stage": developmental_stage,
        "developmental_mode": developmental_mode,
        # Phase 2
        "diarization": diarization or {},
        "enrollment": enrollment or {},
        "routing": routing or {},
        # Phase 3
        "rich_features": rich_features or {},
        "session_context": session_context or {},
        # Phase 4 — probabilistic age classification
        "age_classification": age_classification or {},
    }

    session_table.put_item(Item=_float_to_decimal(session_item))
    logger.info(f"Saved session {session_id}")


def _reconcile_bio_with_age_class(bio_result: Dict, age_class: Dict) -> None:
    """
    Overwrite bio_result flags with the probabilistic classifier's verdict
    when it is more confident.

    The probabilistic classifier uses 7+ acoustic features (F0, VTL, jitter,
    shimmer, HNR, spectral centroid, cry fraction, syllable rate) against
    literature-based Gaussian priors.  The original biological_validation uses
    a simpler score-based system and can be overridden when the richer model
    disagrees with high confidence.

    Rules:
      • Classifier says ADULT (conf ≥ 0.55):
          force is_infant=False, is_adult=True, mimicry_suspected=True,
          update speaker_category and bio_confidence.

      • Classifier says NON-ADULT (conf ≥ 0.60) but bio said ADULT:
          flip is_adult=False, mimicry_suspected=False,
          update speaker_category and bio_confidence.

    Anything below these confidence thresholds: no change (trust bio_result).
    """
    cls  = age_class.get("final_class", "unknown")
    conf = float(age_class.get("confidence", 0.0))

    if cls == "unknown" or conf < 0.50:
        return

    is_adult = age_class.get("is_adult", False)
    is_baby  = age_class.get("is_baby",  False)
    is_child = age_class.get("is_child", False)

    if is_adult and conf >= 0.70:
        bio_result["is_infant"]        = False
        bio_result["is_child"]         = False
        bio_result["is_adult"]         = True
        bio_result["mimicry_suspected"]= True
        bio_result["speaker_category"] = cls
        bio_result["speaker_type"]     = "adult"
        bio_result["bio_confidence"]   = round(max(bio_result.get("bio_confidence", 0.0), conf), 3)
        bio_result["classifier_source"]= "age_classifier_phase4"

    elif (is_baby or is_child) and conf >= 0.68:
        bio_was_adult = bio_result.get("is_adult", False)
        if bio_was_adult:
            bio_result["is_infant"]        = is_baby
            bio_result["is_child"]         = is_child
            bio_result["is_adult"]         = False
            bio_result["mimicry_suspected"]= False
            bio_result["speaker_category"] = cls
            bio_result["speaker_type"]     = (
                "infant" if is_baby else ("child" if is_child else "toddler")
            )
            bio_result["bio_confidence"]   = round(conf, 3)
            bio_result["classifier_source"]= "age_classifier_phase4"


def _enhance_baby_signal(y: np.ndarray) -> np.ndarray:
    """
    Lightweight denoise/enhancement for baby-segment audio.
    Keeps Lambda fast while reducing low-energy background contamination.
    """
    if y is None or len(y) == 0:
        return y

    # Remove DC offset and normalize to stable amplitude range.
    y = y - float(np.mean(y))
    peak = float(np.max(np.abs(y))) if len(y) else 0.0
    if peak > 1e-8:
        y = y / peak

    # Soft-noise suppression: attenuate very low-energy samples.
    mag = np.abs(y)
    noise_floor = float(np.percentile(mag, 20))
    if noise_floor > 0.0:
        y = np.where(mag < noise_floor, y * 0.35, y)

    # Mild pre-emphasis helps F0/formant extraction in noisy home recordings.
    y_pre = np.empty_like(y)
    y_pre[0] = y[0]
    y_pre[1:] = y[1:] - 0.95 * y[:-1]
    return y_pre


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Feature Extraction Lambda handler — Phase 1–4.

    Pipeline (corrected order for accuracy):
      0.  Download audio from S3
      1.  Extract acoustic features on full audio (embedding, feature_scores, audio_array)
      2.  [Phase 1] Audio quality gate (SNR, clipping, silence, Lombard)
      3.  [Phase 2] Diarization on full audio — speaker-segment labels
      4.  Extract baby-only audio from diarization segments
      5.  [Phase 1] Biological validation on BABY audio (clean, not adult-contaminated)
      6.  [Phase 3] Rich feature extraction (~65 features) on BABY audio
      7.  [Phase 4] Probabilistic age classification (Gaussian + voice-type + adult gate)
      8.  Reconcile bio_result flags with probabilistic classifier
      9.  [Phase 2] Load embeddings → enrolled baby identity verification
      10. Get child profile → age + developmental stage selection
      11. [Phase 2] Determine analysis routing
      12. Update EMA baselines, deviation, readiness score
      13. Update child profile
      14. Save session

    Key accuracy improvement: running bio validation and rich feature extraction on
    baby-only audio (step 4) prevents adult voice contamination of acoustic features.

    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "s3_audio_path": str,
            "session_context": dict  # optional
        }
    """
    logger.info(f"Feature extraction started: {json.dumps({k: v for k, v in event.items() if k != 'embedding_vector'})}")

    child_id       = event["child_id"]
    session_id     = event["session_id"]
    s3_audio_path  = event["s3_audio_path"]
    session_context = event.get("session_context") or {}

    # 0. Download audio from S3
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    audio_bytes = download_audio_from_s3(bucket, s3_audio_path)

    # 1. Full-audio extraction: embedding (for enrollment), feature_scores, audio_array
    extraction_result = extract_all_features(audio_bytes)
    feature_scores   = extraction_result["feature_scores"]
    embedding_vector = extraction_result["embedding_vector"]
    duration_seconds = extraction_result["duration_seconds"]
    audio_array      = extraction_result.get("audio_array")
    sample_rate      = extraction_result.get("sample_rate", 22050)

    logger.info(f"Extracted features: {feature_scores}")

    # 2. [Phase 1] Audio quality gate — always run on full audio
    quality_gate_result = {}
    if audio_array is not None:
        try:
            quality_gate_result = audio_quality_gate(audio_array, sample_rate, duration_seconds)
            if not quality_gate_result["passed"]:
                logger.warning(f"Quality gate FAILED session {session_id}: {quality_gate_result['issues']}")
            else:
                logger.info(f"Quality gate passed: SNR={quality_gate_result['snr_db']}dB silence={quality_gate_result['silence_ratio']:.0%}")
        except Exception as e:
            logger.warning(f"Quality gate error (non-blocking): {e}")

    # 3. [Phase 2] Diarization on FULL audio — segment and label by speaker type
    # Running this FIRST allows us to isolate baby audio before bio/rich feature extraction.
    diarization_result = {}
    baby_audio = audio_array   # fallback: full audio
    if audio_array is not None:
        try:
            diarization_result = diarize(audio_array, sample_rate)
            logger.info(
                f"Diarization: {diarization_result['total_segments']} segments, "
                f"baby_fraction={diarization_result['baby_audio_fraction']:.0%}, "
                f"adult_segments={diarization_result['adult_segments_detected']}"
            )
            # 4. Extract baby-labeled audio for clean downstream analysis
            # "unknown" segments are included (conservative — might be quiet baby sounds)
            baby_audio = extract_baby_audio(audio_array, sample_rate, diarization_result)
            baby_audio = _enhance_baby_signal(baby_audio)
            baby_secs  = len(baby_audio) / max(sample_rate, 1)
            logger.info(f"Baby audio extracted: {baby_secs:.1f}s of {duration_seconds:.1f}s total")
        except Exception as e:
            logger.warning(f"Diarization error (non-blocking): {e}")
            baby_audio = audio_array  # safe fallback

    # 5. [Phase 1] Biological validation on BABY audio
    # Running on clean baby audio prevents adult VTL/F0 from contaminating estimates.
    bio_result = {}
    if baby_audio is not None:
        try:
            bio_result = biological_validation(baby_audio, sample_rate)
            if bio_result.get("mimicry_suspected"):
                logger.warning(f"Adult mimicry suspected for session {session_id}: {bio_result['evidence']}")
            else:
                logger.info(f"Bio: is_infant={bio_result.get('is_infant')} VTL={bio_result.get('vtl_cm')}cm F0={bio_result.get('f0_hz')}Hz")
        except Exception as e:
            logger.warning(f"Biological validation error (non-blocking): {e}")

    # 6. [Phase 3] Rich feature extraction (~65 features) on BABY audio
    # Formants from bio validation reused to avoid a second LPC pass.
    rich_features_result = {}
    if baby_audio is not None:
        try:
            formants_for_rich = bio_result.get("formants") if bio_result else None
            rich_features_result = extract_rich_features(
                baby_audio, sample_rate, formants=formants_for_rich
            )
            logger.info(f"Rich features extracted: {len(rich_features_result)} features")
        except Exception as e:
            logger.warning(f"Rich feature extraction error (non-blocking): {e}")

    # 7. [Phase 4] Probabilistic age classification
    # Voice type layer + diagonal Gaussian scoring + conservative adult gate.
    age_classification_result = {}
    if rich_features_result:
        try:
            age_classification_result = classify_probabilistic(
                rich_features_result, bio_result or {}
            )
            logger.info(
                f"Age classifier: class={age_classification_result.get('final_class')} "
                f"conf={age_classification_result.get('confidence', 0.0):.3f} "
                f"voice_type={age_classification_result.get('voice_type')} "
                f"probs={age_classification_result.get('probability_distribution')}"
            )
        except Exception as e:
            logger.warning(f"Age classification error (non-blocking): {e}")

    # 8. Reconcile bio_result with probabilistic classifier
    # Overwrites is_infant, is_adult, mimicry_suspected, speaker_category
    # when the richer multi-feature classifier disagrees with sufficient confidence.
    if age_classification_result and bio_result:
        try:
            _reconcile_bio_with_age_class(bio_result, age_classification_result)
        except Exception as e:
            logger.warning(f"Bio reconciliation error (non-blocking): {e}")

    # 9. [Phase 2] Load historical embeddings → enrolled baby identity verification
    # Uses FULL-audio embedding (not baby-only) — intentional for identity consistency.
    enrollment_result = {}
    try:
        historical_embeddings = load_historical_embeddings(child_id, session_id, limit=10)
        session_count_for_enrollment = len(historical_embeddings) + 1
        enrollment_result = verify_enrolled_baby(
            new_embedding=embedding_vector,
            historical_embeddings=historical_embeddings,
            session_count=session_count_for_enrollment,
        )
        logger.info(
            f"Enrollment: status={enrollment_result.get('enrollment_status')} "
            f"similarity={enrollment_result.get('similarity_score')} "
            f"sessions_used={enrollment_result.get('sessions_used')}"
        )
    except Exception as e:
        logger.warning(f"Enrollment verification error (non-blocking): {e}")

    # 10. Get child profile → age + developmental stage
    profile = get_or_create_child_profile(child_id)
    previous_baselines = profile.get("baseline_features", {})
    session_count = profile.get("session_count", 0) + 1

    birth_date_str = profile.get("birth_date")
    age_days = compute_age_days(birth_date_str)
    age_stage_info = developmental_stage_from_age(age_days)

    # Stage source priority:
    #   1. Bio hint (VTL + F0) — highest physical grounding, conf ≥ 0.55
    #   2. Probabilistic hint (7 features) — conf ≥ 0.40
    #   3. Birth-date estimate — fallback when both audio signals are weak
    #
    # Note: bio_result has already been reconciled with age_classification above,
    # so audio_stage_hint_from_bio will return _NO_HINT if prob classifier
    # detected adult (mimicry_suspected=True).
    audio_hint = audio_stage_hint_from_bio(bio_result)
    prob_hint  = age_class_to_stage_hint(age_classification_result) if age_classification_result else {}

    if audio_hint.get("stage") and audio_hint.get("confidence", 0.0) >= 0.55:
        developmental_stage = audio_hint["stage"]
        developmental_mode  = audio_hint["mode"]
        if age_stage_info["stage"] != audio_hint["stage"]:
            logger.info(
                f"Stage: bio={audio_hint['stage']} (conf={audio_hint['confidence']}) "
                f"overrides age-based={age_stage_info['stage']}"
            )
        else:
            logger.info(f"Stage: bio={audio_hint['stage']} agrees with age-based estimate")

    elif prob_hint.get("stage") and prob_hint.get("confidence", 0.0) >= 0.40:
        developmental_stage = prob_hint["stage"]
        developmental_mode  = prob_hint["mode"]
        logger.info(
            f"Stage: probabilistic hint — class={age_classification_result.get('final_class')} "
            f"→ stage={developmental_stage} conf={prob_hint['confidence']}"
        )

    else:
        developmental_stage = age_stage_info["stage"]
        developmental_mode  = age_stage_info["mode"]
        logger.info(
            f"Stage: fallback to age-based={developmental_stage} "
            f"(bio_conf={audio_hint.get('confidence', 0):.2f}, "
            f"prob_conf={prob_hint.get('confidence', 0):.2f})"
        )

    # Hard guardrail: infants under 12 months must not be routed to linguistic mode
    # from a single noisy audio-stage estimate.
    if age_days is not None and age_days < 366 and developmental_mode == "LINGUISTIC":
        developmental_stage = age_stage_info["stage"]
        developmental_mode = age_stage_info["mode"]
        logger.warning(
            f"Stage guardrail applied for session {session_id}: "
            f"age_days={age_days} forcing stage={developmental_stage} mode={developmental_mode}"
        )

    logger.info(f"Child: age={age_days}d stage={developmental_stage} mode={developmental_mode}")

    # 11. [Phase 2] Determine analysis routing
    # bio_result is already reconciled with age_classification — passes both signals.
    routing_result = determine_routing(
        developmental_stage=developmental_stage,
        developmental_mode=developmental_mode,
        bio_result=bio_result,
        enrollment_result=enrollment_result,
        age_classification=age_classification_result,
    )
    logger.info(f"Routing: {routing_result['analysis_type']}")

    # 8. Update EMA baselines
    alpha = float(os.environ.get("ALPHA_VALUE", str(ALPHA_VALUE)))
    new_baselines = update_feature_baselines(previous_baselines, feature_scores, alpha)

    # 9. Compute deviation
    deviation = compute_deviation_level(
        feature_scores,
        previous_baselines,
        session_count,
        MIN_SESSIONS_FOR_DEVIATION,
    )

    # 10. Compute readiness score
    readiness_score = compute_readiness_score(feature_scores)

    # 11. Update child profile with developmental stage
    update_child_profile(
        child_id=child_id,
        new_baselines=new_baselines,
        readiness_score=readiness_score,
        session_count=session_count,
        developmental_stage=developmental_stage,
        developmental_mode=developmental_mode,
    )

    # 12. Save session with all Phase 1–4 metadata
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
        diarization=diarization_result,
        enrollment=enrollment_result,
        routing=routing_result,
        rich_features=rich_features_result,
        session_context=session_context,
        age_classification=age_classification_result,
    )

    logger.info(f"Feature extraction complete for session {session_id}")

    return {
        "status": "features_extracted",
        "session_id": session_id,
        "child_id": child_id,
        "feature_scores": feature_scores,
        "rich_features": rich_features_result,
        "embedding_vector": embedding_vector,
        "deviation": deviation,
        "readiness_score": readiness_score,
        "duration_seconds": duration_seconds,
        "quality_gate": quality_gate_result,
        "biological": bio_result,
        "diarization": diarization_result,
        "enrollment": enrollment_result,
        "routing": routing_result,
        "developmental_stage": developmental_stage,
        "developmental_mode": developmental_mode,
        "session_context": session_context,
        "age_classification": age_classification_result,
    }
