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
Input:  { child_id, session_id, s3_audio_path }
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
    CHILD_PROFILE_TABLE,
    S3_BUCKET_NAME,
    SAGEMAKER_HUBERT_ENDPOINT,
    SESSION_TABLE,
    TRAINING_FEATURES_TABLE,
    USE_SAGEMAKER_INTENT_ENDPOINT,
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
from core_features import compute_core_features
from hubert_client import extract_hubert_embeddings
from emotion_classifier import predict_emotion, load_model as load_emotion_model
from sound_classifier import classify_sound, classify_segments, aggregate_sound_types

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
training_features_table = dynamodb.Table(TRAINING_FEATURES_TABLE) if TRAINING_FEATURES_TABLE else None
MAX_SUPPORTED_CHILD_AGE_DAYS = 730  # 24 months

# Try loading emotion classifier at cold start
_emotion_model_loaded = load_emotion_model()


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
    # critical = _check_critical_issues(quality_gate)
    critical, reject_title, reject_message = _check_critical_issues(quality_gate)
    if critical:
        return _save_and_return_fast_reject(
            child_id, session_id, s3_audio_path, duration_seconds,
            quality_gate, critical, reject_title, reject_message,
        )

    # --- 2.1 Fetch child profile early so all downstream decisions use DOB age ---
    profile = _get_child_profile(child_id)
    age_days = _compute_age_days(profile.get("birth_date"))

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

    # --- 4.5. Core features (F0, RMS, spectral) — computed ONCE ---
    baby_core = compute_core_features(baby_audio, sample_rate)

    # --- 4.6. Early rejection gate (silence/noise/adult-only) ---
    early_reject = _check_early_rejection(baby_core)
    if early_reject:
        return _save_and_return_fast_reject(
            child_id, session_id, s3_audio_path, duration_seconds,
            quality_gate, early_reject["reasons"],
            early_reject["title"], early_reject["message"],
        )

    # --- 5. Sound classification (uses pre-computed core features) ---
    sound_result = classify_sound(baby_audio, sample_rate, duration_s=duration_seconds,
                                  core_features=baby_core)
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

    # In strict 0-3 month scope, map borderline speech/mixed back to cry when
    # whole-recording evidence is cry-dominant.
    normalized_sound_type = _normalize_sound_type_for_scope(
        sound_type=sound_type,
        sound_summary=sound_summary,
        sound_scores=sound_result.get("scores", {}),
        age_days=age_days,
    )
    if normalized_sound_type != sound_type:
        logger.info(f"Sound type normalized for 0-3 month mode: {sound_type} -> {normalized_sound_type}")
        sound_type = normalized_sound_type
        sound_result["primary_type"] = normalized_sound_type
        if isinstance(sound_summary, dict):
            sound_summary["dominant_type"] = normalized_sound_type
            sound_summary["has_cry"] = normalized_sound_type == "cry" or bool(sound_summary.get("has_cry", False))
            if normalized_sound_type == "cry":
                sound_summary["has_speech"] = False

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

    # --- 7.1 Hard reject for out-of-scope age / adult / noisy / chaotic / broken ---
    post_reject_reasons, post_reject_title, post_reject_message = _check_post_classification_rejects(
        sound_type=sound_type,
        is_adult=is_adult,
        quality_gate=quality_gate,
        age_days=age_days,
        sound_summary=sound_summary,
        sound_scores=sound_result.get("scores", {}),
    )
    if post_reject_reasons:
        return _save_and_return_fast_reject(
            child_id, session_id, s3_audio_path, duration_seconds,
            quality_gate, post_reject_reasons, post_reject_title, post_reject_message,
            reject_sound_type=sound_type, reject_is_adult=is_adult,
        )

    # Determine routing
    routing = _build_routing(
        sound_type=sound_type,
        sound_summary=sound_summary,
        is_adult=is_adult,
        age_days=age_days,
    )

    # --- 7.5 HuBERT embeddings + emotion classifier (EARS + BRAIN) ---
    hubert_result = {}
    classifier_result = {}
    if USE_SAGEMAKER_INTENT_ENDPOINT and SAGEMAKER_HUBERT_ENDPOINT and sound_type in ("cry", "mixed"):
        try:
            hubert_result = extract_hubert_embeddings(
                baby_audio, sample_rate, SAGEMAKER_HUBERT_ENDPOINT,
            )
            hubert_emb = hubert_result.get("embeddings")
            if hubert_emb is not None and hubert_emb.shape[0] == 768:
                classifier_result = predict_emotion(hubert_emb, age_days=age_days)
                logger.info(
                    f"Emotion classifier: {classifier_result.get('primary_emotion')} "
                    f"conf={classifier_result.get('confidence', 0):.3f} "
                    f"model={classifier_result.get('model_version', 'unknown')}"
                )
                # Store embeddings for Phase 3 training
                _store_training_features(
                    session_id=session_id,
                    hubert_embeddings=hubert_emb,
                    sound_type=sound_type,
                    classifier_result=classifier_result,
                    age_days=age_days,
                    duration_s=duration_seconds,
                )
        except Exception as e:
            logger.warning(f"HuBERT/classifier error (non-fatal): {e}")
    elif sound_type in ("cry", "mixed") and not USE_SAGEMAKER_INTENT_ENDPOINT:
        logger.info("HuBERT call skipped: USE_SAGEMAKER_INTENT_ENDPOINT=false")

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
        # HuBERT + classifier
        "classifier_result": classifier_result if classifier_result else None,
        "hubert_latency_ms": hubert_result.get("latency_ms"),
        # Metadata
        "quality_gate": quality_gate,
        "diarization": diarization_result,
        "age_days_at_recording": age_days,
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
        "classifier_result": classifier_result if classifier_result else None,
        "biological": bio_result,
        "age_classification": age_classification,
        "age_days": age_days,
        "duration_seconds": duration_seconds,
        "quality_gate": quality_gate,
        "routing": routing,
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

    # 0-3 month babies: cry-only analysis, disable transcription
    if isinstance(age_days, int) and age_days <= 90:
        run_transcription = False

    return {
        "sound_type": sound_type,
        "is_adult": is_adult,
        "run_transcription": run_transcription,
        "run_cry_analysis": run_cry_analysis,
        "run_laugh_detection": run_laugh_detection,
        "age_days": age_days,
    }


def _check_critical_issues(quality_gate: Dict) -> tuple:
    """Check early quality issues that warrant fast rejection."""
    if not isinstance(quality_gate, dict):
        return [], "", ""
    issues = quality_gate.get("issues", []) or []
    reasons = []
    has_broken = False
    has_noisy = False
    for issue in issues:
        issue_text = str(issue)
        if issue_text.startswith(("no_signal", "too_short:", "too_long:", "clipping:")):
            reasons.append(issue_text)
            has_broken = True
        elif issue_text.startswith(("low_snr:", "too_silent:", "no_vocal_activity_detected")):
            reasons.append(issue_text)
            has_noisy = True

    if has_broken:
        return reasons, "Audio Quality Issue", "Audio is broken. Please try to record again with a clear baby sound."
    if has_noisy:
        return reasons, "Noisy Environment", "Noisy environment detected. Please record again in a quieter place."
    return [], "", ""


def _check_post_classification_rejects(
    sound_type: str,
    is_adult: bool,
    quality_gate: Dict,
    age_days: Optional[int],
    sound_summary: Optional[Dict] = None,
    sound_scores: Optional[Dict] = None,
) -> tuple:
    """Check post-classification rejection conditions."""
    reasons = []
    issues = quality_gate.get("issues", []) if isinstance(quality_gate, dict) else []

    if not isinstance(age_days, int) or age_days < 0:
        reasons.append("age_unavailable")
    if isinstance(age_days, int) and age_days > MAX_SUPPORTED_CHILD_AGE_DAYS:
        reasons.append(f"age_out_of_range:{age_days}d")

    if is_adult:
        reasons.append("adult_voice_detected")

    if sound_type == "noise":
        reasons.append("noisy_environment")
    # Speech is only rejected for 0-3m babies (cry-only scope)
    if sound_type == "speech" and isinstance(age_days, int) and age_days <= 90:
        reasons.append("speech_not_expected")
    if sound_type == "mixed":
        if _is_chaotic_mixed(sound_summary, sound_scores):
            reasons.append("chaotic_environment")

    for issue in issues:
        issue_text = str(issue)
        if issue_text.startswith(("no_signal", "too_short:", "too_long:", "clipping:")):
            reasons.append("broken_audio")
        if issue_text.startswith(("low_snr:", "too_silent:", "no_vocal_activity_detected")):
            reasons.append("noisy_environment")

    if not reasons:
        return [], "", ""

    if "age_unavailable" in reasons or any(str(r).startswith("age_out_of_range:") for r in reasons):
        return reasons, "Age Not Supported", "This system supports children aged 0-24 months only."
    if "adult_voice_detected" in reasons:
        return reasons, "Adult Voice Detected", "Adult voice detected. Please record a clean and fresh baby sound."
    if "speech_not_expected" in reasons:
        return reasons, "Speech Not Supported", "Babies under 3 months are analyzed for cry patterns only. Please upload a baby crying recording."
    if "chaotic_environment" in reasons:
        return reasons, "Chaotic Environment", "Chaotic environment detected. Please record a cleaner baby-only sound."
    if "noisy_environment" in reasons:
        return reasons, "Noisy Environment", "Noisy environment detected. Please record in a quieter place."
    return reasons, "Audio Quality Issue", "Audio is broken. Please try to record again."


def _is_chaotic_mixed(sound_summary: Optional[Dict], sound_scores: Optional[Dict]) -> bool:
    """Return True if mixed audio is too noisy/non-cry to analyze safely."""
    summary = sound_summary if isinstance(sound_summary, dict) else {}
    scores = sound_scores if isinstance(sound_scores, dict) else {}
    ratios = summary.get("type_ratios", {}) if isinstance(summary.get("type_ratios"), dict) else {}

    cry_ratio = float(ratios.get("cry", 0.0))
    speech_ratio = float(ratios.get("speech", 0.0))
    noise_ratio = float(ratios.get("noise", 0.0))

    # Segment-ratio path (preferred when diarized segments exist).
    if ratios:
        cry_dominant = (
            cry_ratio >= 0.35
            and cry_ratio >= speech_ratio + 0.08
            and cry_ratio >= noise_ratio
        )
        return not cry_dominant

    # Fallback to session-level classifier scores.
    cry_score = float(scores.get("cry", 0.0))
    speech_score = float(scores.get("speech", 0.0))
    noise_score = float(scores.get("noise", 0.0))
    mixed_score = float(scores.get("mixed", 0.0))

    cry_dominant = (
        cry_score >= 0.45
        and cry_score >= speech_score + 0.08
        and cry_score >= noise_score
        and cry_score >= mixed_score
    )
    return not cry_dominant


def _normalize_sound_type_for_scope(
    sound_type: str,
    sound_summary: Optional[Dict],
    sound_scores: Optional[Dict],
    age_days: Optional[int],
) -> str:
    """Normalize sound type for strict 0-3 month cry-only analysis mode."""
    if not isinstance(age_days, int) or age_days > MAX_SUPPORTED_CHILD_AGE_DAYS:
        return sound_type

    if sound_type == "speech":
        # Keep speech only when whole-session evidence is strongly speech.
        if _is_clear_speech_without_cry(sound_summary, sound_scores):
            return sound_type
        return "cry"

    if sound_type == "mixed":
        # In this age scope, mixed that is cry-dominant should proceed as cry.
        if not _is_chaotic_mixed(sound_summary, sound_scores):
            return "cry"
        return sound_type

    return sound_type


def _is_clear_speech_without_cry(sound_summary: Optional[Dict], sound_scores: Optional[Dict]) -> bool:
    """Strong speech dominance over the full recording; avoids cry->speech misfires."""
    summary = sound_summary if isinstance(sound_summary, dict) else {}
    scores = sound_scores if isinstance(sound_scores, dict) else {}
    ratios = summary.get("type_ratios", {}) if isinstance(summary.get("type_ratios"), dict) else {}

    if ratios:
        speech_ratio = float(ratios.get("speech", 0.0))
        cry_ratio = float(ratios.get("cry", 0.0))
        noise_ratio = float(ratios.get("noise", 0.0))
        return (
            speech_ratio >= 0.55
            and speech_ratio >= cry_ratio + 0.20
            and cry_ratio <= 0.15
            and noise_ratio <= 0.35
        )

    speech_score = float(scores.get("speech", 0.0))
    cry_score = float(scores.get("cry", 0.0))
    noise_score = float(scores.get("noise", 0.0))
    return (
        speech_score >= 0.70
        and speech_score >= cry_score + 0.20
        and cry_score <= 0.30
        and noise_score <= 0.45
    )


def _check_early_rejection(core: Dict) -> Optional[Dict]:
    """
    Early rejection gate using pre-computed core features.
    Rejects silence, noise, and adult-only audio in <2s.
    Returns None if audio should proceed, or a dict with reasons/title/message.
    """
    reasons = []

    # Silence: very low RMS across most frames
    rms = core.get("rms")
    rms_mean = core.get("rms_mean", 0.0)
    voiced_frac = core.get("voiced_fraction", 0.0)

    if rms is not None and len(rms) > 0 and rms_mean < 0.005:
        low_frames = float(np.sum(rms < 0.005)) / max(1, len(rms))
        if low_frames >= 0.80:
            reasons.append("silence_detected")

    # No voiced frames at all
    if voiced_frac < 0.03 and rms_mean < 0.015:
        reasons.append("no_voiced_frames")

    if reasons:
        return {
            "reasons": reasons,
            "title": "No Sound Detected",
            "message": "No baby sound detected. Please record closer to the baby.",
        }

    # Adult-only: F0 median below baby range with no high-F0 segments
    f0_mean = core.get("f0_mean", 0.0)
    if 0 < f0_mean < 200 and voiced_frac > 0.2:
        reasons.append("adult_voice_only")
        return {
            "reasons": reasons,
            "title": "Adult Voice Detected",
            "message": "Adult voice detected. Please record a clean baby sound.",
        }

    return None


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
    quality_gate, critical_issues,
    reject_title: Optional[str] = None,
    reject_message: Optional[str] = None,
    reject_sound_type: str = "silence",
    reject_is_adult: bool = False,
) -> Dict:
    """Save and return a fast-reject result."""
    profile = _get_child_profile(child_id)
    age_days = _compute_age_days(profile.get("birth_date"))
    now = datetime.now(timezone.utc).isoformat()

    final_title = reject_title or "Audio Rejected"
    final_message = reject_message or "The recording could not be processed. Please try a cleaner baby recording."

    session_item = {
        "session_id": session_id,
        "child_id": child_id,
        "s3_audio_path": s3_audio_path,
        "timestamp": now,
        "duration_seconds": duration_seconds,
        "processed": True,
        # "sound_type": "silence",
        "sound_type": reject_sound_type,
        # "is_adult": False,
        "is_adult": reject_is_adult,
        "quality_gate": quality_gate,
        "age_days_at_recording": age_days,
        # "routing": {"sound_type": "silence", "is_adult": False,
        #              "run_transcription": False, "run_cry_analysis": False,
        #              "run_laugh_detection": False},
        "routing": {"sound_type": reject_sound_type, "is_adult": reject_is_adult,
                    "run_transcription": False, "run_cry_analysis": False,
                    "run_laugh_detection": False},
        "fast_reject": True,
        "fast_reject_reasons": critical_issues,
        "fast_reject_title": final_title,
        "fast_reject_message": final_message,
    }
    session_table.put_item(Item=_float_to_decimal(session_item))

    return {
        "status": "classified",
        "session_id": session_id,
        "child_id": child_id,
        # "sound_type": "silence",
        "sound_type": reject_sound_type,
        # "is_adult": False,
        "is_adult": reject_is_adult,
        "fast_reject": True,
        "fast_reject_reasons": critical_issues,
        "fast_reject_title": final_title,
        "fast_reject_message": final_message,
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
        "s3_audio_path": s3_audio_path,
    }


def _store_training_features(
    session_id: str,
    hubert_embeddings: np.ndarray,
    sound_type: str,
    classifier_result: Dict,
    age_days: Optional[int],
    duration_s: float,
):
    """
    Store HuBERT embeddings in S3 and metadata in DynamoDB for Phase 3 training.
    NOT linked to child_id (anonymization happens at feedback time).
    """
    import uuid

    feature_id = str(uuid.uuid4())
    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    s3_key = f"training-features/{feature_id}/embeddings.npy"

    try:
        # Store embeddings in S3
        import io
        buf = io.BytesIO()
        np.save(buf, hubert_embeddings.astype(np.float32))
        buf.seek(0)
        s3_client.put_object(Bucket=bucket, Key=s3_key, Body=buf.read())

        # Store metadata in DynamoDB
        if training_features_table is not None:
            now = datetime.now(timezone.utc).isoformat()
            item = {
                "feature_id": feature_id,
                "session_id": session_id,
                "s3_embeddings_path": s3_key,
                "sound_type": sound_type,
                "predicted_emotion": classifier_result.get("primary_emotion", "unknown"),
                "predicted_confidence": classifier_result.get("confidence", 0.0),
                "model_version": classifier_result.get("model_version", "unknown"),
                "age_days": age_days if isinstance(age_days, int) else 0,
                "duration_s": duration_s,
                "created_at": now,
            }
            training_features_table.put_item(Item=_float_to_decimal(item))

        logger.info(f"Training features stored: {feature_id} -> s3://{bucket}/{s3_key}")
    except Exception as e:
        logger.warning(f"Failed to store training features (non-fatal): {e}")
