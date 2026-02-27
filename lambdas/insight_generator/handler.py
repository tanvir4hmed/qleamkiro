"""
Qleam - Insight Generator Lambda
Translates system state into structured, non-diagnostic parent guidance.

Phase 4 - Three-Source Evidence Model:
- 60% Acoustic signal    - real-time audio features (summary + Phase 3 rich features)
- 15% Research priors    - developmental stage norms + session context (feeding, health)
- 25% Feedback history   - parent reinforcement over time
  -> Acoustic is ground truth; feedback personalises without dominating early sessions.
- Insight now includes evidence breakdown for transparency.

Trigger: Step Function third state
Input:  { child_id, session_id, cluster_id }
Output: Structured insight JSON stored in Session table
"""
import json
import logging
import os
import re
import sys
import time
import uuid
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

# Add shared utilities to path (for container image deployment)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    BEDROCK_MODEL_ID,
    CHILD_PROFILE_TABLE,
    DISCLAIMER,
    INTENT_LABELS,
    MODEL_REGISTRY_TABLE,
    POPULATION_MODEL_TABLE,
    S3_BUCKET_NAME,
    SEMANTIC_BRIDGE_TABLE,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    SAGEMAKER_INTENT_ENDPOINT_NAME,
    TRANSCRIBE_TIMEOUT_SECONDS,
    USE_BEDROCK,
    USE_SAGEMAKER_INTENT_ENDPOINT,
    USE_TRANSCRIBE_FOR_LINGUISTIC,
)
from normalization import normalize_probability_distribution
from evidence_model import determine_probable_intent_v2
from intent_taxonomy import canonical_intent_key, canonical_intent_keys
from training_model import predict_intent_distribution

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
semantic_bridge_table = dynamodb.Table(SEMANTIC_BRIDGE_TABLE)
population_model_table = dynamodb.Table(POPULATION_MODEL_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)

_CRITICAL_GATE_ISSUES = ("no_signal", "too_short:")


# =============================================================================
# DynamoDB Helpers
# =============================================================================

def _decimal_to_float(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _float_to_decimal(obj: Any) -> Any:
    """Convert floats to Decimal for DynamoDB."""
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
        if math.isnan(obj):
            return Decimal("0")
        if math.isinf(obj):
            return Decimal("0") if obj < 0 else Decimal("1")
        return Decimal(str(obj))
    if isinstance(obj, bool):
        return Decimal("1") if obj else Decimal("0")
    if isinstance(obj, str):
        try:
            return Decimal(obj)
        except Exception:
            return obj
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


# =============================================================================
# DynamoDB Fetchers
# =============================================================================

def get_session(session_id: str) -> Optional[Dict]:
    response = session_table.get_item(Key={"session_id": session_id})
    return _decimal_to_float(response.get("Item"))


def get_child_profile(child_id: str) -> Optional[Dict]:
    response = child_profile_table.get_item(Key={"child_id": child_id})
    return _decimal_to_float(response.get("Item"))


def get_cluster(cluster_id: str) -> Optional[Dict]:
    response = sound_cluster_table.get_item(Key={"cluster_id": cluster_id})
    return _decimal_to_float(response.get("Item"))


def get_semantic_bridge(cluster_id: str) -> Optional[Dict]:
    """Get the highest-confidence semantic bridge for a cluster."""
    response = semantic_bridge_table.query(
        IndexName="cluster_id-index",
        KeyConditionExpression=boto3.dynamodb.conditions.Key("cluster_id").eq(cluster_id)
    )
    bridges = response.get("Items", [])
    if not bridges:
        return None
    return _decimal_to_float(max(bridges, key=lambda b: float(b.get("semantic_confidence_score", 0))))


def get_population_prior(developmental_stage: str) -> Optional[Dict[str, float]]:
    """
    Load the Phase 8 FL population prior for a given developmental stage.

    Returns the prior distribution if it exists AND is reliable
    (n_participants >= FL_MIN_PARTICIPANTS). Returns None otherwise,
    causing evidence_model to fall back to static literature priors.
    """
    try:
        response = population_model_table.get_item(
            Key={"stage": developmental_stage.upper()},
            ProjectionExpression="population_prior, n_participants, is_reliable",
        )
        item = _decimal_to_float(response.get("Item") or {})
        if not item:
            return None
        if not item.get("is_reliable"):
            logger.debug(f"Population prior for {developmental_stage} exists but not reliable - using literature priors")
            return None
        prior = item.get("population_prior")
        if prior and isinstance(prior, dict):
            logger.debug(f"Using FL population prior for stage={developmental_stage} n={item.get('n_participants')}")
            return prior
    except Exception as e:
        logger.warning(f"Failed to load population prior for {developmental_stage}: {e}")
    return None


def get_training_dataset_profile(developmental_stage: str) -> Dict[str, Any]:
    """
    Load stage-level accepted training dataset profile from PopulationModel table.

    Returns a shape with safe defaults when no dataset exists:
      {
        "prior": None | {intent: prob},
        "n": int,
        "is_reliable": bool
      }
    """
    try:
        response = population_model_table.get_item(
            Key={"stage": developmental_stage.upper()},
            ProjectionExpression="dataset_prior, dataset_n, dataset_is_reliable",
        )
        item = _decimal_to_float(response.get("Item") or {})
        prior = item.get("dataset_prior")
        if isinstance(prior, dict) and len(prior) >= 3:
            n = int(item.get("dataset_n") or 0)
            is_reliable = bool(item.get("dataset_is_reliable"))
            return {"prior": prior, "n": n, "is_reliable": is_reliable}
    except Exception as e:
        logger.warning(f"Failed to load training dataset profile for {developmental_stage}: {e}")
    return {"prior": None, "n": 0, "is_reliable": False}


_CORE_INTENT_KEYS = tuple(canonical_intent_keys(include_technical=False))


def invoke_sagemaker_intent_endpoint(session: Dict, developmental_stage: str) -> Dict[str, Any]:
    """
    Optional managed inference override for acoustic intent scores.
    Expected endpoint response JSON shape:
      {
        "intent_distribution": {"hunger": 0.2, ...},
        "emotion_profile": {...},                  # optional
        "model_version": "x.y.z"                  # optional
      }
    """
    if not USE_SAGEMAKER_INTENT_ENDPOINT or not SAGEMAKER_INTENT_ENDPOINT_NAME:
        return {}

    try:
        runtime = boto3.client("sagemaker-runtime")
        payload = {
            "feature_scores": session.get("feature_scores", {}),
            "rich_features": session.get("rich_features", {}),
            "biological": session.get("biological", {}),
            "diarization": session.get("diarization", {}),
            "developmental_stage": developmental_stage,
        }
        response = runtime.invoke_endpoint(
            EndpointName=SAGEMAKER_INTENT_ENDPOINT_NAME,
            ContentType="application/json",
            Body=json.dumps(payload).encode("utf-8"),
        )
        raw = response["Body"].read().decode("utf-8")
        parsed = json.loads(raw) if raw else {}

        dist = (
            parsed.get("intent_distribution")
            or parsed.get("acoustic_scores")
            or {}
        )
        cleaned: Dict[str, float] = {}
        if isinstance(dist, dict):
            for k, v in dist.items():
                key = canonical_intent_key(k, allow_technical=False)
                if key and key in _CORE_INTENT_KEYS:
                    try:
                        cleaned[key] = max(0.0, float(v))
                    except Exception:
                        continue

        if len(cleaned) >= 2:
            cleaned = normalize_probability_distribution(cleaned)
        else:
            cleaned = {}

        result: Dict[str, Any] = {"acoustic_scores": cleaned}
        emo = parsed.get("emotion_profile")
        if isinstance(emo, dict):
            result["emotion_profile"] = emo

        meta = parsed.get("acoustic_meta") if isinstance(parsed.get("acoustic_meta"), dict) else {}
        if not meta:
            meta = {
                "training_samples": parsed.get("training_samples"),
                "reliability": parsed.get("reliability"),
            }
        try:
            meta_clean = {}
            if meta.get("training_samples") is not None:
                meta_clean["training_samples"] = int(meta.get("training_samples"))
            if meta.get("reliability") is not None:
                meta_clean["reliability"] = float(meta.get("reliability"))
            if meta_clean:
                result["acoustic_meta"] = meta_clean
        except Exception:
            pass

        result["managed_model"] = {
            "provider": "sagemaker",
            "endpoint": SAGEMAKER_INTENT_ENDPOINT_NAME,
            "model_version": parsed.get("model_version"),
            "acoustic_meta": result.get("acoustic_meta"),
        }
        return result
    except Exception as e:
        logger.warning(f"SageMaker intent inference failed: {e}")
        return {}


def invoke_internal_stage_model(session: Dict, developmental_stage: str) -> Dict[str, Any]:
    """
    Optional internal stage model inference from ModelRegistry.
    Used when managed endpoint output is unavailable.
    """
    try:
        stage_resp = population_model_table.get_item(
            Key={"stage": developmental_stage.upper()},
            ProjectionExpression=(
                "active_model_id, active_model_reliability, "
                "active_model_training_samples, model_version"
            ),
        )
        stage_item = _decimal_to_float(stage_resp.get("Item") or {})
        active_model_id = str(stage_item.get("active_model_id") or "").strip()
        if not active_model_id:
            return {}

        model_resp = model_registry_table.get_item(Key={"model_id": active_model_id})
        model_item = _decimal_to_float(model_resp.get("Item") or {})
        if not model_item:
            return {}
        if str(model_item.get("status") or "").upper() == "RETIRED":
            return {}

        artifact = model_item.get("artifact") or {}
        if not isinstance(artifact, dict):
            return {}

        acoustic_scores = predict_intent_distribution(
            model=artifact,
            feature_scores=session.get("feature_scores", {}),
            rich_features=session.get("rich_features", {}),
        )
        if not isinstance(acoustic_scores, dict) or len(acoustic_scores) < 2:
            return {}

        reliability = float(
            model_item.get(
                "reliability",
                stage_item.get("active_model_reliability", 0.0),
            )
            or 0.0
        )
        training_samples = int(
            model_item.get(
                "training_samples",
                stage_item.get("active_model_training_samples", 0),
            )
            or 0
        )
        meta = {
            "training_samples": training_samples,
            "reliability": max(0.0, min(1.0, reliability)),
        }
        return {
            "acoustic_scores": normalize_probability_distribution(acoustic_scores),
            "acoustic_meta": meta,
            "managed_model": {
                "provider": str(model_item.get("provider") or "qleam_online_supervised_v1"),
                "model_id": active_model_id,
                "model_version": int(model_item.get("model_version", 0) or 0),
                "acoustic_meta": meta,
            },
        }
    except Exception as e:
        logger.warning(f"Internal stage model inference failed (non-fatal): {e}")
        return {}


def transcribe_session_audio(session: Dict) -> Optional[Dict[str, Any]]:
    """
    Optional transcription via Amazon Transcribe.
    Returns None on timeout/failure.
    """
    if not USE_TRANSCRIBE_FOR_LINGUISTIC:
        return None

    s3_key = str(session.get("s3_audio_path") or "").strip()
    if not s3_key:
        return None

    bucket = os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME)
    media_uri = f"s3://{bucket}/{s3_key}"
    timeout_s = int(os.environ.get("TRANSCRIBE_TIMEOUT_SECONDS", str(TRANSCRIBE_TIMEOUT_SECONDS)))
    job_name = f"qleam-{uuid.uuid4().hex[:12]}"

    try:
        transcribe = boto3.client("transcribe")
        transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": media_uri},
            IdentifyLanguage=True,
        )
    except Exception as e:
        logger.warning(f"Transcribe start failed: {e}")
        return None

    deadline = time.time() + max(8, timeout_s)
    while time.time() < deadline:
        try:
            job = transcribe.get_transcription_job(TranscriptionJobName=job_name).get("TranscriptionJob", {})
            status = job.get("TranscriptionJobStatus")
            if status == "COMPLETED":
                uri = (
                    job.get("Transcript", {}).get("TranscriptFileUri")
                    or ""
                )
                if not uri:
                    return None
                with urllib.request.urlopen(uri, timeout=8) as r:
                    data = json.loads(r.read().decode("utf-8"))
                text = " ".join(
                    t.get("transcript", "")
                    for t in data.get("results", {}).get("transcripts", [])
                ).strip()
                if not text:
                    return None
                items = data.get("results", {}).get("items", []) or []
                confidence_values: List[float] = []
                token_count = 0
                for item in items:
                    if str(item.get("type", "")).lower() != "pronunciation":
                        continue
                    token_count += 1
                    alts = item.get("alternatives", []) or []
                    if not alts:
                        continue
                    try:
                        confidence_values.append(float(alts[0].get("confidence", 0.0) or 0.0))
                    except Exception:
                        continue
                avg_confidence = (
                    round(sum(confidence_values) / len(confidence_values), 3)
                    if confidence_values else 0.0
                )
                language_code = (
                    job.get("LanguageCode")
                    or data.get("results", {}).get("language_code")
                    or ""
                )
                return {
                    "text": text,
                    "language_code": language_code,
                    "source": "aws-transcribe",
                    "confidence": avg_confidence,
                    "token_count": int(token_count),
                }
            if status == "FAILED":
                logger.warning(f"Transcribe failed: {job.get('FailureReason', 'unknown')}")
                return None
        except Exception as e:
            logger.warning(f"Transcribe polling error: {e}")
            return None
        time.sleep(2)

    logger.warning(f"Transcribe timeout after {timeout_s}s for job {job_name}")
    return None


_WORD_RE = re.compile(r"[A-Za-z\u00C0-\u024F']{2,}")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "have", "from", "your", "you",
    "are", "was", "were", "been", "will", "would", "should", "could", "they",
    "them", "their", "there", "then", "than", "when", "what", "where", "which",
    "into", "onto", "about", "after", "before", "again", "very", "just", "baby",
    "mama", "dada",
}


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def _estimate_speech_presence_score(
    rich_features: Dict[str, Any],
    segment_summary: Optional[Dict[str, Any]] = None,
) -> float:
    """
    Estimate whether lexical speech is likely present.
    Returns a score in [0, 1].
    """
    syllable_rate = float(rich_features.get("syllable_rate", 0.0) or 0.0)
    hnr_db = float(rich_features.get("hnr_db", 0.0) or 0.0)
    pause_ratio = float(rich_features.get("pause_ratio", 0.5) or 0.5)
    f0_range = float(rich_features.get("f0_range", 0.0) or 0.0)
    voiced_fraction = float(rich_features.get("f0_voiced_fraction", 0.0) or 0.0)
    cry_fraction = float(rich_features.get("cry_fraction", 0.0) or 0.0)
    babble_fraction = float(rich_features.get("babble_fraction", 0.0) or 0.0)

    speech_rate = _clamp01((syllable_rate - 1.2) / 4.8)
    clarity = _clamp01((hnr_db - 6.0) / 16.0)
    prosody = _clamp01((f0_range - 70.0) / 280.0)
    continuity = _clamp01((0.75 - pause_ratio) / 0.75)
    voiced = _clamp01((voiced_fraction - 0.10) / 0.70)
    cry_penalty = _clamp01((cry_fraction - 0.15) / 0.55)
    babble_bonus = _clamp01((babble_fraction - 0.10) / 0.60)

    score = (
        speech_rate * 0.28
        + clarity * 0.24
        + prosody * 0.14
        + continuity * 0.14
        + voiced * 0.12
        + babble_bonus * 0.08
        - cry_penalty * 0.22
    )
    if isinstance(segment_summary, dict) and segment_summary:
        seg_speech = float(segment_summary.get("speech_ratio", 0.0) or 0.0)
        seg_adult_speech = float(segment_summary.get("adult_speech_ratio", 0.0) or 0.0)
        seg_cry = float(segment_summary.get("cry_ratio", 0.0) or 0.0)
        score = (
            score * 0.72
            + _clamp01(seg_speech + seg_adult_speech * 0.7) * 0.33
            - _clamp01(seg_cry) * 0.10
        )
    return round(_clamp01(score), 3)


def _extract_detected_words(transcript_text: str, max_words: int = 8) -> List[Dict[str, Any]]:
    """
    Extract frequent lexical tokens from transcript for UI evidence display.
    """
    if not transcript_text:
        return []
    tokens = [t.lower() for t in _WORD_RE.findall(transcript_text)]
    tokens = [t for t in tokens if t not in _STOPWORDS and len(t) >= 2]
    if not tokens:
        return []
    counts = Counter(tokens)
    out: List[Dict[str, Any]] = []
    for word, count in counts.most_common(max_words):
        out.append({"word": word, "count": int(count)})
    return out


def _evaluate_age_mismatch_evidence(
    age_days: Optional[float],
    transcript: Optional[Dict[str, Any]],
    detected_words: List[Dict[str, Any]],
    speech_presence_score: float,
) -> Dict[str, Any]:
    """
    Estimate how inconsistent lexical speech evidence is with registered age.
    """
    if age_days is None:
        return {
            "score": 0.0,
            "level": "none",
            "reason": "age_missing",
            "registered_age_days": None,
            "transcript_word_count": 0,
            "lexical_complexity": 0.0,
        }

    text = str((transcript or {}).get("text", "") or "").strip()
    tokens = [t.lower() for t in _WORD_RE.findall(text)]
    word_count = len(tokens)
    if word_count <= 0:
        return {
            "score": 0.0,
            "level": "none",
            "reason": "no_lexical_tokens_detected",
            "registered_age_days": int(age_days),
            "transcript_word_count": 0,
            "lexical_complexity": 0.0,
            "unique_word_count": 0,
        }
    unique_count = len(set(tokens))
    long_ratio = (sum(1 for t in tokens if len(t) >= 4) / max(1, word_count)) if word_count else 0.0
    multiword_phrase = 1.0 if word_count >= 2 else 0.0
    lexical_complexity = _clamp01(
        (0.40 * _clamp01(word_count / 8.0))
        + (0.30 * _clamp01(unique_count / 6.0))
        + (0.20 * long_ratio)
        + (0.10 * multiword_phrase)
    )

    score = 0.0
    reason = "age_consistent"
    if age_days < 180:
        # 0-6 months: lexical speech is highly unlikely.
        score = (
            0.30 * _clamp01(word_count / 2.0)
            + 0.32 * lexical_complexity
            + 0.18 * multiword_phrase
            + 0.20 * _clamp01(speech_presence_score)
        )
        reason = "clear lexical speech is atypical for 0-6 months"
    elif age_days < 366:
        # 6-12 months: proto-words possible, fluent lexical speech still unlikely.
        score = (
            0.22 * _clamp01(max(0.0, word_count - 1.0) / 4.0)
            + 0.30 * lexical_complexity
            + 0.18 * multiword_phrase
            + 0.15 * _clamp01(speech_presence_score)
            + 0.15 * _clamp01(unique_count / 5.0)
        )
        reason = "speech complexity appears higher than expected for 6-12 months"
    elif age_days < 730:
        # 12-24 months: words are expected; mismatch only for very complex lexical bursts.
        score = (
            0.18 * _clamp01(max(0.0, word_count - 4.0) / 8.0)
            + 0.20 * _clamp01(max(0.0, unique_count - 3.0) / 8.0)
            + 0.12 * long_ratio
            + 0.10 * _clamp01(speech_presence_score)
        )
        reason = "lexical complexity is somewhat advanced for 12-24 months"
    else:
        score = 0.0
        reason = "lexical speech is age-expected"

    score = round(_clamp01(score), 3)
    if score >= 0.80:
        level = "high"
    elif score >= 0.60:
        level = "moderate"
    elif score >= 0.35:
        level = "mild"
    else:
        level = "none"

    return {
        "score": score,
        "level": level,
        "reason": reason,
        "registered_age_days": int(age_days),
        "transcript_word_count": int(word_count),
        "lexical_complexity": round(lexical_complexity, 3),
        "unique_word_count": int(unique_count),
    }


def _collect_speech_evidence(session: Dict, force_transcribe: bool = False) -> Dict[str, Any]:
    """
    Build speech evidence bundle (speech presence, transcript, detected words, age mismatch).
    Caches result on session object to avoid duplicate Transcribe calls.
    """
    cached = session.get("_speech_evidence_cache")
    if isinstance(cached, dict):
        if not force_transcribe:
            return cached
        if cached.get("transcript") or not USE_TRANSCRIBE_FOR_LINGUISTIC:
            return cached

    rich_features = session.get("rich_features", {}) or {}
    segment_summary = ((session.get("segment_evidence") or {}).get("summary") or {})
    age_days = session.get("age_days_at_recording")
    speech_presence_score = _estimate_speech_presence_score(
        rich_features,
        segment_summary=segment_summary,
    )
    if speech_presence_score >= 0.66:
        presence_label = "speech_likely"
    elif speech_presence_score >= 0.42:
        presence_label = "mixed_or_emerging_speech"
    else:
        presence_label = "non_speech_or_cry"

    transcribe_attempted = False
    transcript: Optional[Dict[str, Any]] = None
    should_transcribe = bool(
        USE_TRANSCRIBE_FOR_LINGUISTIC and (force_transcribe or speech_presence_score >= 0.42)
    )
    if should_transcribe:
        transcribe_attempted = True
        transcript = transcribe_session_audio(session)

    detected_words = _extract_detected_words(str((transcript or {}).get("text", "") or ""))
    age_mismatch = _evaluate_age_mismatch_evidence(
        age_days=age_days if isinstance(age_days, (int, float)) else None,
        transcript=transcript,
        detected_words=detected_words,
        speech_presence_score=speech_presence_score,
    )

    evidence = {
        "speech_presence_score": speech_presence_score,
        "speech_presence_label": presence_label,
        "transcribe_attempted": transcribe_attempted,
        "transcript": transcript,
        "detected_words": detected_words,
        "age_mismatch_evidence": age_mismatch,
        "segment_summary": segment_summary,
    }
    session["_speech_evidence_cache"] = evidence
    return evidence


def _infer_laugh_signal(
    feature_scores: Dict[str, Any],
    rich_features: Dict[str, Any],
    segment_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Heuristic laugh signal detector used as a secondary evidence tag.
    """
    hnr_db = float(rich_features.get("hnr_db", 0.0) or 0.0)
    syllable_rate = float(rich_features.get("syllable_rate", 0.0) or 0.0)
    f0_range = float(rich_features.get("f0_range", 0.0) or 0.0)
    babble_fraction = float(rich_features.get("babble_fraction", 0.0) or 0.0)
    cry_fraction = float(rich_features.get("cry_fraction", 0.0) or 0.0)
    repetition = float(feature_scores.get("repetition", 0.0) or 0.0)
    emotional_intensity = float(feature_scores.get("emotional_intensity", 0.0) or 0.0)

    clarity = _clamp01((hnr_db - 8.0) / 14.0)
    rhythm = _clamp01((syllable_rate - 2.0) / 4.0)
    prosody = _clamp01((f0_range - 120.0) / 240.0)
    babble = _clamp01((babble_fraction - 0.15) / 0.60)
    non_cry = _clamp01(1.0 - cry_fraction)
    rep = _clamp01(repetition)

    score = (
        clarity * 0.27
        + rhythm * 0.20
        + prosody * 0.16
        + babble * 0.15
        + non_cry * 0.12
        + rep * 0.10
    )
    if isinstance(segment_summary, dict) and segment_summary:
        seg_laugh = float(segment_summary.get("laugh_ratio", 0.0) or 0.0)
        seg_cry = float(segment_summary.get("cry_ratio", 0.0) or 0.0)
        score = score * 0.78 + _clamp01(seg_laugh) * 0.35 - _clamp01(seg_cry) * 0.08
    if cry_fraction > 0.30:
        score -= 0.20 * _clamp01((cry_fraction - 0.30) / 0.40)
    if emotional_intensity > 0.88 and cry_fraction > 0.20:
        score -= 0.08
    score = round(_clamp01(score), 3)

    return {
        "detected": bool(score >= 0.62),
        "confidence": score,
        "source": "acoustic_secondary",
    }


def _infer_secondary_signals(
    feature_scores: Dict[str, Any],
    rich_features: Dict[str, Any],
    segment_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Additional non-primary cues for better UX transparency and stage-aware tuning.
    """
    laugh = _infer_laugh_signal(
        feature_scores=feature_scores,
        rich_features=rich_features,
        segment_summary=segment_summary,
    )

    ei = float(feature_scores.get("emotional_intensity", 0.0) or 0.0)
    rh = float(feature_scores.get("rhythm", 0.0) or 0.0)
    rep = float(feature_scores.get("repetition", 0.0) or 0.0)
    ef = float(feature_scores.get("expressive_flow", 0.0) or 0.0)

    cry_fraction = float(rich_features.get("cry_fraction", 0.0) or 0.0)
    jitter = float(rich_features.get("jitter_percent", 0.0) or 0.0)
    hnr_db = float(rich_features.get("hnr_db", 0.0) or 0.0)
    f0_range = float(rich_features.get("f0_range", 0.0) or 0.0)

    seg = segment_summary or {}
    seg_cry = float(seg.get("cry_ratio", 0.0) or 0.0)
    seg_speech = float(seg.get("speech_ratio", 0.0) or 0.0)
    seg_laugh = float(seg.get("laugh_ratio", 0.0) or 0.0)

    shout_score = (
        0.34 * _clamp01((ei - 0.52) / 0.48)
        + 0.22 * _clamp01((1.0 - rh - 0.18) / 0.82)
        + 0.20 * _clamp01((jitter - 6.0) / 14.0)
        + 0.12 * _clamp01((cry_fraction - 0.12) / 0.68)
        + 0.12 * _clamp01((f0_range - 140.0) / 280.0)
    )
    shout_score += 0.15 * _clamp01(seg_cry) + 0.05 * _clamp01(seg_speech)
    shout_score -= 0.10 * _clamp01(seg_laugh) + 0.08 * _clamp01(laugh.get("confidence", 0.0))
    shout_score = round(_clamp01(shout_score), 3)

    distress_score = (
        0.36 * _clamp01((cry_fraction - 0.20) / 0.70)
        + 0.24 * _clamp01((jitter - 7.0) / 14.0)
        + 0.18 * _clamp01((10.0 - hnr_db) / 10.0)
        + 0.12 * _clamp01((ei - 0.45) / 0.55)
        + 0.10 * _clamp01((1.0 - rh - 0.20) / 0.80)
    )
    distress_score += 0.20 * _clamp01(seg_cry)
    distress_score -= 0.08 * _clamp01(seg_laugh)
    distress_score = round(_clamp01(distress_score), 3)

    soothing_need_score = (
        0.28 * _clamp01((ei - 0.30) / 0.70)
        + 0.22 * _clamp01((rep - 0.20) / 0.80)
        + 0.22 * _clamp01((1.0 - ef - 0.10) / 0.90)
        + 0.16 * _clamp01((cry_fraction - 0.08) / 0.60)
        + 0.12 * _clamp01((1.0 - rh) / 1.0)
    )
    soothing_need_score += 0.08 * _clamp01(seg_cry)
    soothing_need_score -= 0.08 * _clamp01(seg_laugh)
    soothing_need_score = round(_clamp01(soothing_need_score), 3)

    return {
        "laugh": laugh,
        "shout_frustration": {
            "detected": bool(shout_score >= 0.60),
            "confidence": shout_score,
            "source": "acoustic_secondary",
        },
        "distress_pressure": {
            "detected": bool(distress_score >= 0.58),
            "confidence": distress_score,
            "source": "acoustic_secondary",
        },
        "soothing_need": {
            "detected": bool(soothing_need_score >= 0.56),
            "confidence": soothing_need_score,
            "source": "acoustic_secondary",
        },
    }


def _augment_sections_with_evidence(
    sections: Dict[str, Any],
    speech_evidence: Dict[str, Any],
    secondary_signals: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Add evidence-specific lines to section text to avoid static-feel outputs.
    """
    out = dict(sections or {})
    what_i_hear = str(out.get("what_i_hear", "") or "").strip()
    what_it_means = str(out.get("what_it_means", "") or "").strip()
    what_to_try = list(out.get("what_to_try", []) or [])

    transcript = speech_evidence.get("transcript") or {}
    detected_words = speech_evidence.get("detected_words") or []
    mismatch = speech_evidence.get("age_mismatch_evidence") or {}
    speech_presence_label = str(speech_evidence.get("speech_presence_label", "") or "")
    laugh_signal = (secondary_signals or {}).get("laugh") or {}
    shout_signal = (secondary_signals or {}).get("shout_frustration") or {}
    distress_signal = (secondary_signals or {}).get("distress_pressure") or {}
    soothing_signal = (secondary_signals or {}).get("soothing_need") or {}

    if transcript.get("text"):
        lang = str(transcript.get("language_code", "") or "").strip() or "unknown"
        what_i_hear = (
            f"{what_i_hear} Detected speech transcript in {lang}."
        ).strip()
    elif speech_presence_label == "speech_likely":
        what_i_hear = (
            f"{what_i_hear} Speech-like vocal patterns are present in this recording."
        ).strip()

    if detected_words:
        preview = ", ".join([w.get("word", "") for w in detected_words[:4] if w.get("word")])
        if preview:
            what_i_hear = (
                f"{what_i_hear} Detected words: {preview}."
            ).strip()

    mismatch_score = float(mismatch.get("score", 0.0) or 0.0)
    if mismatch_score >= 0.60:
        what_it_means = (
            f"{what_it_means} Speech complexity appears higher than expected for the registered age profile."
        ).strip()
        if "Re-check child slot and who was speaking in the clip" not in what_to_try:
            what_to_try.insert(0, "Re-check child slot and who was speaking in the clip")
    elif mismatch_score >= 0.35:
        what_it_means = (
            f"{what_it_means} Some speech cues may be age-advanced for this profile."
        ).strip()

    if bool(laugh_signal.get("detected")):
        what_i_hear = (
            f"{what_i_hear} Laughter-like vocal bursts are also present."
        ).strip()
    if bool(shout_signal.get("detected")) and float(shout_signal.get("confidence", 0.0) or 0.0) >= 0.62:
        what_i_hear = (
            f"{what_i_hear} I also hear shout-like/frustrated bursts."
        ).strip()
    if bool(distress_signal.get("detected")) and float(distress_signal.get("confidence", 0.0) or 0.0) >= 0.60:
        what_it_means = (
            f"{what_it_means} Distress pressure is elevated in this sample."
        ).strip()
    if bool(soothing_signal.get("detected")) and float(soothing_signal.get("confidence", 0.0) or 0.0) >= 0.60:
        if "Try close soothing (hold, rocking, gentle voice) for 2-3 minutes then re-check" not in what_to_try:
            what_to_try.insert(0, "Try close soothing (hold, rocking, gentle voice) for 2-3 minutes then re-check")

    out["what_i_hear"] = what_i_hear
    out["what_it_means"] = what_it_means
    out["what_to_try"] = what_to_try[:3] if what_to_try else []
    return out


def _calibrate_probable_intent_with_phase_rules(
    probable_intent: Dict[str, Any],
    developmental_stage: str,
    feature_scores: Dict[str, Any],
    rich_features: Dict[str, Any],
    speech_evidence: Dict[str, Any],
    secondary_signals: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Post-fusion calibration:
      - age/stage-aware smoothing
      - anger/hunger/discomfort conflict tuning
      - laugh secondary signal influence
      - lexical mismatch confidence penalty for infant buckets
    """
    if not isinstance(probable_intent, dict):
        return probable_intent
    evidence = dict(probable_intent.get("evidence") or {})
    blended_raw = evidence.get("blended") or {}
    if not isinstance(blended_raw, dict) or not blended_raw:
        return probable_intent

    blended: Dict[str, float] = {
        str(k): max(0.0, float(v or 0.0)) for k, v in blended_raw.items()
    }
    stage = str(developmental_stage or "UNKNOWN").upper().strip()
    infant_stage = stage in {"NEWBORN", "EARLY_VOCAL", "CANONICAL_BABBLE", "PROTO_WORDS"}

    cry_fraction = float(rich_features.get("cry_fraction", 0.0) or 0.0)
    hnr_db = float(rich_features.get("hnr_db", 0.0) or 0.0)
    jitter = float(rich_features.get("jitter_percent", 0.0) or 0.0)
    rhythm = float(feature_scores.get("rhythm", 0.0) or 0.0)
    repetition = float(feature_scores.get("repetition", 0.0) or 0.0)
    emotional_intensity = float(feature_scores.get("emotional_intensity", 0.0) or 0.0)

    calibration = {
        "applied": [],
        "stage": stage,
    }
    laugh_signal = (secondary_signals or {}).get("laugh") or {}
    shout_signal = (secondary_signals or {}).get("shout_frustration") or {}
    distress_signal = (secondary_signals or {}).get("distress_pressure") or {}
    soothing_signal = (secondary_signals or {}).get("soothing_need") or {}

    # 1) Laugh signal boosts positive affect and exploratory intent.
    laugh_conf = float(laugh_signal.get("confidence", 0.0) or 0.0)
    if bool(laugh_signal.get("detected")) and laugh_conf >= 0.62:
        boost = min(0.08, 0.04 + 0.04 * laugh_conf)
        blended["happy"] = blended.get("happy", 0.0) + boost
        blended["exploration"] = blended.get("exploration", 0.0) + boost * 0.45
        blended["pain"] = max(0.0, blended.get("pain", 0.0) - boost * 0.45)
        blended["discomfort"] = max(0.0, blended.get("discomfort", 0.0) - boost * 0.35)
        calibration["applied"].append("laugh_positive_shift")
    shout_conf = float(shout_signal.get("confidence", 0.0) or 0.0)
    if bool(shout_signal.get("detected")) and shout_conf >= 0.60:
        boost = min(0.08, 0.03 + 0.05 * shout_conf)
        blended["frustration"] = blended.get("frustration", 0.0) + boost
        blended["discomfort"] = blended.get("discomfort", 0.0) + boost * 0.35
        blended["happy"] = max(0.0, blended.get("happy", 0.0) - boost * 0.50)
        blended["closeness"] = max(0.0, blended.get("closeness", 0.0) - boost * 0.20)
        calibration["applied"].append("shout_frustration_shift")
    distress_conf = float(distress_signal.get("confidence", 0.0) or 0.0)
    if bool(distress_signal.get("detected")) and distress_conf >= 0.58:
        boost = min(0.08, 0.03 + 0.05 * distress_conf)
        blended["pain"] = blended.get("pain", 0.0) + boost * 0.50
        blended["discomfort"] = blended.get("discomfort", 0.0) + boost * 0.50
        blended["distress_unknown"] = blended.get("distress_unknown", 0.0) + boost * 0.25
        blended["happy"] = max(0.0, blended.get("happy", 0.0) - boost * 0.60)
        calibration["applied"].append("distress_pressure_shift")
    soothing_conf = float(soothing_signal.get("confidence", 0.0) or 0.0)
    if bool(soothing_signal.get("detected")) and soothing_conf >= 0.56:
        boost = min(0.06, 0.02 + 0.04 * soothing_conf)
        blended["closeness"] = blended.get("closeness", 0.0) + boost
        blended["frustration"] = max(0.0, blended.get("frustration", 0.0) - boost * 0.30)
        calibration["applied"].append("soothing_need_shift")

    # 2) Strong cry distress pushes pain/discomfort signal for infant stages.
    if infant_stage and cry_fraction >= 0.45 and jitter >= 7.0 and hnr_db <= 10.0:
        shift = min(0.09, 0.04 + (cry_fraction - 0.45) * 0.08)
        blended["pain"] = blended.get("pain", 0.0) + shift * 0.55
        blended["discomfort"] = blended.get("discomfort", 0.0) + shift * 0.45
        blended["happy"] = max(0.0, blended.get("happy", 0.0) - shift * 0.45)
        blended["exploration"] = max(0.0, blended.get("exploration", 0.0) - shift * 0.30)
        calibration["applied"].append("infant_distress_shift")

    # 3) Resolve hunger vs frustration/discomfort ties.
    hunger = blended.get("hunger", 0.0)
    frustration = blended.get("frustration", 0.0)
    discomfort = blended.get("discomfort", 0.0)
    if abs(hunger - frustration) <= 0.08:
        irregular = max(0.0, 1.0 - rhythm)
        frustration_support = irregular * 0.55 + min(jitter / 20.0, 1.0) * 0.45
        hunger_support = rhythm * 0.55 + repetition * 0.45
        shift = min(0.05, abs(frustration_support - hunger_support) * 0.08)
        if frustration_support > hunger_support:
            blended["frustration"] = frustration + shift
            blended["hunger"] = max(0.0, hunger - shift * 0.7)
            calibration["applied"].append("frustration_over_hunger")
        elif hunger_support > frustration_support:
            blended["hunger"] = hunger + shift
            blended["frustration"] = max(0.0, frustration - shift * 0.7)
            calibration["applied"].append("hunger_over_frustration")
    if abs(hunger - discomfort) <= 0.08 and infant_stage:
        hunger_support = rhythm * 0.50 + repetition * 0.30 + min(cry_fraction / 0.8, 1.0) * 0.20
        discomfort_support = (1.0 - rhythm) * 0.45 + min(jitter / 20.0, 1.0) * 0.35 + min(cry_fraction / 0.8, 1.0) * 0.20
        shift = min(0.05, abs(hunger_support - discomfort_support) * 0.08)
        if hunger_support > discomfort_support:
            blended["hunger"] = blended.get("hunger", 0.0) + shift
            blended["discomfort"] = max(0.0, blended.get("discomfort", 0.0) - shift * 0.7)
            calibration["applied"].append("hunger_over_discomfort")
        elif discomfort_support > hunger_support:
            blended["discomfort"] = blended.get("discomfort", 0.0) + shift
            blended["hunger"] = max(0.0, blended.get("hunger", 0.0) - shift * 0.7)
            calibration["applied"].append("discomfort_over_hunger")

    # Normalize
    blended = normalize_probability_distribution(blended)
    top_intents = sorted(blended.items(), key=lambda x: -x[1])[:3]
    best_key = top_intents[0][0] if top_intents else probable_intent.get("key", "distress_unknown")
    best_conf = float(probable_intent.get("confidence", 0.0) or 0.0)

    # 4) Lexical mismatch penalty for infant stages.
    mismatch_score = float((speech_evidence.get("age_mismatch_evidence") or {}).get("score", 0.0) or 0.0)
    presence_score = float(speech_evidence.get("speech_presence_score", 0.0) or 0.0)
    if infant_stage and mismatch_score >= 0.35:
        penalty = min(0.28, 0.10 + mismatch_score * 0.20 + max(0.0, presence_score - 0.45) * 0.08)
        best_conf *= max(0.55, 1.0 - penalty)
        calibration["applied"].append("lexical_mismatch_confidence_penalty")
        calibration["mismatch_penalty"] = round(penalty, 3)

    best_conf = round(max(0.10, min(0.92, best_conf)), 3)
    label = INTENT_LABELS.get(best_key, best_key.replace("_", " ").title())

    evidence["blended"] = {k: round(v, 3) for k, v in blended.items()}
    evidence["calibration"] = calibration
    return {
        **probable_intent,
        "key": best_key,
        "label": label,
        "confidence": best_conf,
        "top_intents": [
            {
                "key": k,
                "label": INTENT_LABELS.get(k, k.replace("_", " ").title()),
                "weight": round(v, 3),
            }
            for k, v in top_intents
        ],
        "evidence": evidence,
    }


# =============================================================================
# Rule-Based Insight Sections (used when Bedrock is off or fails)
# =============================================================================

INTENT_SECTIONS = {
    "hunger": {
        "what_i_hear": "Baby's sounds show rhythmic, building intensity, a classic hunger-like signal.",
        "what_it_means": "This pattern often suggests hunger or feeding need.",
        "what_to_try": [
            "Offer feeding and watch hand-to-mouth cues",
            "Check time since last feeding",
            "Try gentle tummy comfort if needed",
        ],
    },
    "fatigue": {
        "what_i_hear": "Baby's sounds are repetitive with short fussy bursts, often a tiredness profile.",
        "what_it_means": "This pattern commonly appears when baby is sleepy or overtired.",
        "what_to_try": [
            "Start a calm sleep routine",
            "Reduce light and noise",
            "Use consistent soothing rhythm",
        ],
    },
    "pain": {
        "what_i_hear": "Baby's sounds are sharp and highly strained, which may indicate pain-like distress.",
        "what_it_means": "This profile can occur with acute discomfort and needs prompt calming checks.",
        "what_to_try": [
            "Check immediate pain triggers",
            "Use close soothing contact",
            "Seek medical advice if distress remains high",
        ],
    },
    "discomfort": {
        "what_i_hear": "Baby's sounds are intense and irregular, often linked to physical discomfort.",
        "what_it_means": "This pattern may reflect gas, wet diaper, temperature discomfort, or position issues.",
        "what_to_try": [
            "Check diaper, temperature, and clothing",
            "Try a different hold or position",
            "Use gentle belly soothing",
        ],
    },
    "closeness": {
        "what_i_hear": "Baby's sounds are socially directed and softer, often asking for closeness.",
        "what_it_means": "Many babies use this pattern when they want cuddle, reassurance, and responsive contact.",
        "what_to_try": [
            "Hold baby close and respond warmly",
            "Mirror sounds and pause for turn-taking",
            "Use skin-to-skin if comfortable",
        ],
    },
    "frustration": {
        "what_i_hear": "Baby's sounds are tense and irregular with rising effort, a frustration-like profile.",
        "what_it_means": "This can happen when baby is overloaded or blocked and needs regulation support.",
        "what_to_try": [
            "Reduce stimulation and simplify the scene",
            "Use slow rhythmic soothing",
            "Allow a short calm reset",
        ],
    },
    "happy": {
        "what_i_hear": "Baby's sounds are clear and flowing with social energy, often happy/content.",
        "what_it_means": "This pattern is commonly associated with comfort and positive engagement.",
        "what_to_try": [
            "Continue warm interaction",
            "Reinforce with smiles and mirroring",
            "Use this moment for playful language input",
        ],
    },
    "exploration": {
        "what_i_hear": "Baby's sounds are varied and playful, typical of neutral/cooing exploration.",
        "what_it_means": "This often means baby is alert and experimenting with vocal control.",
        "what_to_try": [
            "Mirror sounds back gently",
            "Offer simple visual focus objects",
            "Keep interactive vocal play going",
        ],
    },
    "distress_unknown": {
        "what_i_hear": "This distress pattern is currently mixed and still being learned.",
        "what_it_means": "The system cannot yet separate this cleanly into one need, so it stays as fallback distress.",
        "what_to_try": [
            "Use a calm checklist: feeding, rest, comfort",
            "Record again in lower-noise conditions",
            "Continue feedback so this pattern gets personalized",
        ],
    },
    "non_baby_spoof_noise": {
        "what_i_hear": "The recording looks non-baby, spoof-like, or mostly background/noise.",
        "what_it_means": "This sample is treated as technical/non-baby and not used for baby intent interpretation.",
        "what_to_try": [
            "Record closer to the baby",
            "Reduce adult speech and TV/background noise",
            "Retry when baby is actively vocalizing",
        ],
    },
    # Backward compatibility aliases
    "connection": {
        "what_i_hear": "Baby's sounds are socially directed.",
        "what_it_means": "This maps to closeness/comfort seeking.",
        "what_to_try": ["Hold baby close", "Use warm voice", "Mirror sounds"],
    },
    "overstimulation": {
        "what_i_hear": "Baby's sounds are intense and irregular.",
        "what_it_means": "This maps to frustration/regulation support needs.",
        "what_to_try": ["Reduce stimulation", "Use calming rhythm", "Allow reset"],
    },
    "unknown": {
        "what_i_hear": "Pattern still uncertain.",
        "what_it_means": "This maps to distress-unknown fallback.",
        "what_to_try": ["Record more", "Use calm checklist", "Share feedback"],
    },
}
def _age_band_from_stage(stage: str) -> str:
    stage = (stage or "").upper().strip()
    if stage in ("NEWBORN",):
        return "0-3m"
    if stage in ("EARLY_VOCAL",):
        return "3-6m"
    if stage in ("CANONICAL_BABBLE", "PROTO_WORDS"):
        return "6-12m"
    if stage in ("FIRST_WORDS", "WORD_COMBINATIONS"):
        return "12-24m"
    if stage in ("EARLY_SENTENCES",):
        return "24-36m"
    return "unknown"


_AGE_BAND_CONTEXT = {
    "0-3m": "At 0-3 months, most vocalizations are need-based and reflexive.",
    "3-6m": "At 3-6 months, social coos appear alongside need-based sounds.",
    "6-12m": "At 6-12 months, babbling and repetition become common.",
    "12-24m": "At 12-24 months, early words can appear alongside need-based sounds.",
    "24-36m": "At 24-36 months, short phrases emerge but need-based sounds still occur.",
}

_AGE_BAND_TRY = {
    "0-3m": "Use skin-to-skin or gentle rocking for regulation",
    "3-6m": "Pause and respond with soft coos to encourage turn-taking",
    "6-12m": "Echo their babbles and pause for a response",
    "12-24m": "Offer simple choices: 'milk or water?'",
    "24-36m": "Label needs with short phrases: 'you want water'",
}


def get_rule_based_sections(
    intent_key: str,
    developmental_stage: str = "UNKNOWN",
    feature_narrative: Optional[Dict[str, str]] = None,
    child_name: str = "",
) -> Dict:
    """Return structured rule-based insight sections with age-aware context."""
    base = INTENT_SECTIONS.get(intent_key, INTENT_SECTIONS["distress_unknown"])
    age_band = _age_band_from_stage(developmental_stage)
    age_context = _AGE_BAND_CONTEXT.get(age_band, "")
    age_try = _AGE_BAND_TRY.get(age_band)

    name = (child_name or "").strip()
    subject = f"{name}'s" if name else "Your baby's"

    feature_line = ""
    if feature_narrative:
        feature_line = (
            f"{subject} sounds are {feature_narrative.get('emotional_tone', 'expressive')} "
            f"and {feature_narrative.get('sound_pattern', 'varied')}, "
            f"with {feature_narrative.get('continuity', 'short bursts')}."
        )

    what_i_hear_parts = [feature_line, base["what_i_hear"]]
    what_i_hear = " ".join(p for p in what_i_hear_parts if p).strip()
    what_it_means_parts = [base["what_it_means"], age_context]
    what_it_means = " ".join(p for p in what_it_means_parts if p).strip()

    what_to_try = list(base["what_to_try"])
    if age_try:
        what_to_try = [age_try] + what_to_try

    return {
        "what_i_hear": what_i_hear,
        "what_it_means": what_it_means,
        "what_to_try": what_to_try[:3],
        "source": "rule-based",
        "age_band": age_band,
    }


# =============================================================================
# LINGUISTIC Mode Insight (Phase 7)
# =============================================================================

LINGUISTIC_FALLBACK_INSIGHTS = {
    "SOUNDS_ONLY": {
        "what_i_hear": "I mostly hear vocal sounds and emotional tone, not clear words in this recording.",
        "what_it_means": "This is common during busy or tired moments. It suggests their language signals weren't prominent here.",
        "what_to_try": [
            "Try a calm, face-to-face moment and wait for a response",
            "Use short, clear phrases and pause for their turn",
            "Record again during play or a routine they enjoy",
        ],
    },
    "FIRST_WORDS": {
        "what_i_hear": "Your child is producing clear, intentional word-like sounds with real communicative purpose.",
        "what_it_means": "Each session helps track their vocabulary growth. These are the building blocks of language.",
        "what_to_try": [
            "Respond to every word attempt - acknowledgement encourages more speech",
            "Name objects together during play to expand vocabulary",
            "Read simple picture books and point to objects as you name them",
        ],
    },
    "WORD_COMBINATIONS": {
        "what_i_hear": "Your child is linking sounds and words in multi-word patterns - a key leap in language.",
        "what_it_means": "Two-word combinations show the grammar system is developing. This is a major milestone.",
        "what_to_try": [
            "Expand what your child says - if they say 'more milk', respond 'yes, more cold milk'",
            "Ask open questions that need more than one word to answer",
            "Narrate everyday activities: 'We're washing the big red apple'",
        ],
    },
    "EARLY_SENTENCES": {
        "what_i_hear": "Your child is forming multi-word sentences with structure and intent.",
        "what_it_means": "Sentence formation at this stage reflects strong language development.",
        "what_to_try": [
            "Engage in back-and-forth conversation and give your child time to respond",
            "Model complete sentences in response to shorter ones they produce",
            "Introduce simple stories with cause and effect to build narrative thinking",
        ],
    },
}

def _speech_signal_level(rich_features: dict) -> str:
    """
    Estimate how speech-like the session is for LINGUISTIC-stage fallbacks.
    Returns: "non_speech" | "emerging" | "speech_like"
    """
    syllable_rate = float(rich_features.get("syllable_rate", 0.0))
    hnr_db = float(rich_features.get("hnr_db", 0.0))
    cbr = float(rich_features.get("cbr_estimate", 0.0))
    f0_range = float(rich_features.get("f0_range", 0.0))

    if syllable_rate < 1.2 and hnr_db < 8.0 and cbr < 0.10:
        return "non_speech"
    if syllable_rate < 2.0 and (hnr_db < 10.0 or f0_range < 80.0):
        return "emerging"
    return "speech_like"


def _generate_linguistic_insight_with_bedrock(
    developmental_stage: str,
    rich_features: dict,
    transcript: Optional[Dict[str, str]] = None,
) -> dict:
    """Generate language-development insight via Bedrock for LINGUISTIC mode sessions."""
    try:
        bedrock = boto3.client("bedrock-runtime")
        model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)

        syllable_rate = round(float(rich_features.get("syllable_rate", 0.0)), 2)
        pause_ratio = round(float(rich_features.get("pause_ratio", 0.5)), 2)
        f0_range = round(float(rich_features.get("f0_range", 0.0)), 1)
        hnr_db = round(float(rich_features.get("hnr_db", 0.0)), 1)
        cbr = round(float(rich_features.get("cbr_estimate", 0.0)), 3)
        stage_label = developmental_stage.replace("_", " ").title()
        transcript_note = ""
        if transcript and transcript.get("text"):
            snippet = transcript.get("text", "")[:220]
            lang = transcript.get("language_code", "")
            transcript_note = (
                "\nSPEECH TRANSCRIPT (AUTO):\n"
                f"- Language: {lang or 'unknown'}\n"
                f"- Transcript snippet: {snippet}"
            )

        prompt = f"""You are a warm, supportive language development analyst helping parents understand their child's speech progress.

CHILD'S DEVELOPMENTAL STAGE: {stage_label}

ACOUSTIC MEASUREMENTS FROM THIS SESSION:
- Syllable rate: {syllable_rate} syllables/second
- Pause ratio: {pause_ratio} (proportion of silence - higher = more pauses between utterances)
- Pitch range: {f0_range} Hz (wider = more expressive prosody)
- Voice clarity (HNR): {hnr_db} dB (higher = cleaner, more resonant speech)
- Canonical babbling ratio: {cbr} (residual babble - lower at this stage is normal)
{transcript_note}

Return ONLY a JSON object with exactly these three fields:
{{
  "what_i_hear": "1-2 sentences describing what the acoustic measurements show about this child's current speech. Focus on positive signals. Plain, warm language.",
  "what_it_means": "1-2 sentences about what this means for their language development. Use 'suggests', 'indicates', 'is consistent with'. Never diagnose.",
  "what_to_try": ["specific actionable language activity 1", "specific actionable language activity 2", "specific actionable language activity 3"]
}}

Guidelines:
- Write for a parent who wants practical language development support, not medical information
- Focus on language development, not cry interpretation
- Keep each sentence under 25 words
- The 3 activities must be immediately doable at home
- Return ONLY the JSON object"""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 450,
            "temperature": 0.35,
            "messages": [{"role": "user", "content": prompt}],
        })

        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        raw_text = result["content"][0]["text"]

        sections = _parse_bedrock_json(raw_text)
        if sections and "what_i_hear" in sections:
            if isinstance(sections.get("what_to_try"), str):
                sections["what_to_try"] = [sections["what_to_try"]]
            return {
                "what_i_hear": sections.get("what_i_hear", ""),
                "what_it_means": sections.get("what_it_means", ""),
                "what_to_try": sections.get("what_to_try", [])[:3],
                "source": "bedrock",
            }

        raise ValueError(f"Could not parse Bedrock JSON: {raw_text[:200]}")

    except Exception as e:
        logger.warning(f"Bedrock failed for LINGUISTIC insight, using rule-based: {e}")
        return None


def _build_dynamic_linguistic_fallback(
    developmental_stage: str,
    rich_features: dict,
    transcript: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Dynamic non-static fallback when Bedrock is unavailable.
    """
    syllable_rate = float(rich_features.get("syllable_rate", 0.0))
    pause_ratio = float(rich_features.get("pause_ratio", 0.5))
    hnr_db = float(rich_features.get("hnr_db", 0.0))
    f0_range = float(rich_features.get("f0_range", 0.0))
    stage_label = developmental_stage.replace("_", " ").title()
    transcript_text = str((transcript or {}).get("text", "") or "").strip()
    transcript_tokens = [t.lower() for t in _WORD_RE.findall(transcript_text)]
    transcript_preview = " ".join(transcript_tokens[:6]).strip()

    if transcript_text:
        what_i_hear = (
            "I can hear speech-like vocalization and detected words in this recording."
        )
        if transcript_preview:
            what_i_hear = (
                f"{what_i_hear} Transcript sample: {transcript_preview}."
            )
    elif syllable_rate >= 2.0 and hnr_db >= 9.0:
        what_i_hear = (
            "I can hear speech-like vocalization with clear syllable activity in this recording."
        )
    else:
        what_i_hear = (
            "I hear mostly vocal sounds with limited clear speech in this recording."
        )

    what_it_means = (
        f"This pattern is consistent with the {stage_label.lower()} stage, "
        "but confidence improves with repeated sessions."
    )
    if pause_ratio > 0.45:
        what_it_means += " There are notable pauses, so language clarity may be reduced in this sample."
    if f0_range < 90:
        what_it_means += " Prosody range is narrow in this recording."
    if len(transcript_tokens) >= 4:
        what_it_means += " Multi-word speech is present in this clip."

    actions: List[str] = []
    if len(transcript_tokens) >= 3:
        actions.append("Repeat detected key words back in short phrases")
    else:
        actions.append("Use short face-to-face phrases and wait for a reply")
    if pause_ratio > 0.45:
        actions.append("Record during calm play with lower background noise")
    else:
        actions.append("Keep 15-30 second clips focused on one activity")
    if syllable_rate < 1.5:
        actions.append("Use rhythmic turn-taking sounds and pauses")
    else:
        actions.append("Repeat key words slowly and consistently")
    return {
        "what_i_hear": what_i_hear,
        "what_it_means": what_it_means,
        "what_to_try": actions[:3],
        "source": "dynamic-fallback",
    }


def _generate_linguistic_insight(
    session_id: str,
    child_id: str,
    developmental_stage: str,
    rich_features: dict,
    feature_scores: Optional[Dict] = None,
    session: Optional[Dict] = None,
) -> dict:
    """
    Generate and store language-development insight for LINGUISTIC-mode sessions.
    Skips intent classification - focuses on language metrics instead.
    """
    use_bedrock = os.environ.get("USE_BEDROCK", str(USE_BEDROCK)).lower() == "true"
    speech_evidence = _collect_speech_evidence(session or {}, force_transcribe=True) if session else {}
    transcript = speech_evidence.get("transcript")
    detected_words = speech_evidence.get("detected_words", [])
    age_mismatch_evidence = speech_evidence.get("age_mismatch_evidence", {})
    segment_summary = speech_evidence.get("segment_summary") or ((session or {}).get("segment_evidence", {}) or {}).get("summary", {})
    secondary_signals = _infer_secondary_signals(feature_scores or {}, rich_features or {}, segment_summary=segment_summary)

    insight_sections = None
    if use_bedrock:
        insight_sections = _generate_linguistic_insight_with_bedrock(
            developmental_stage, rich_features, transcript=transcript
        )

    if not insight_sections:
        insight_sections = _build_dynamic_linguistic_fallback(
            developmental_stage, rich_features, transcript=transcript
        )
    insight_sections = _augment_sections_with_evidence(
        insight_sections,
        speech_evidence=speech_evidence,
        secondary_signals=secondary_signals,
    )

    # Build observed_pattern from feature_scores so the acoustic chart can render
    fs = feature_scores or {}
    observed_pattern = {
        "emotional_intensity": round(float(fs.get("emotional_intensity", 0)), 3),
        "rhythm":              round(float(fs.get("rhythm", 0)), 3),
        "repetition":          round(float(fs.get("repetition", 0)), 3),
        "expressive_flow":     round(float(fs.get("expressive_flow", 0)), 3),
    }

    insight = {
        "insight_type": "language_development",
        "developmental_stage": developmental_stage,
        "observed_pattern": observed_pattern,
        "insight_sections": insight_sections,
        "suggested_response": "  |  ".join(insight_sections.get("what_to_try", [])),
        "speech_transcript": transcript,
        "detected_words": detected_words,
        "age_mismatch_evidence": age_mismatch_evidence,
        "speech_evidence": {
            "presence_score": speech_evidence.get("speech_presence_score", 0.0),
            "presence_label": speech_evidence.get("speech_presence_label", "non_speech_or_cry"),
            "transcribe_attempted": bool(speech_evidence.get("transcribe_attempted", False)),
            "segment_summary": segment_summary,
        },
        "secondary_signals": secondary_signals,
        "speaker_authenticity": session.get("speaker_gate") if isinstance(session, dict) else None,
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    save_insight_to_session(session_id, insight)

    logger.info(
        f"LINGUISTIC insight generated for session {session_id}: "
        f"stage={developmental_stage} source={insight_sections['source']}"
    )
    return {
        "status": "insight_generated",
        "session_id": session_id,
        "insight": insight,
    }


# =============================================================================
# Acoustic Feature-Based Intent Classifier
# =============================================================================

def classify_intent_from_features(feature_scores: Dict[str, float]) -> Dict[str, float]:
    """
    Pure acoustic feature-based intent classification.
    Does NOT use parent feedback - derived entirely from audio signal.

    Feature semantics (all 0.0-1.0):
    - emotional_intensity: pitch variance + energy variance (0=calm, 1=distressed)
    - rhythm: regularity of sound bursts (1=very rhythmic, 0=irregular)
    - repetition: MFCC self-similarity (1=same sounds repeated, 0=varied)
    - expressive_flow: vocalization continuity (1=long/continuous, 0=short bursts)

    Pattern logic derived from infant vocalization research:
    - Hunger: rhythmic escalation with building intensity
    - Discomfort: intense, arrhythmic, persistent
    - Connection: calm, flowing, low intensity (babbling/cooing)
    - Fatigue: moderate intensity, repetitive fussing, fragmented
    - Overstimulation: high sustained intensity, irregular
    - Exploration: varied, calm, flowing
    """
    ei = feature_scores.get("emotional_intensity", 0.5)
    rh = feature_scores.get("rhythm", 0.5)
    rep = feature_scores.get("repetition", 0.5)
    ef = feature_scores.get("expressive_flow", 0.5)

    # Hunger: intense + rhythmic (feeding cry = rhythmic escalation)
    hunger = ei * 0.50 + rh * 0.40 + rep * 0.10

    # Discomfort: very intense + arrhythmic + persistent repetition
    discomfort = ei * 0.60 + (1.0 - rh) * 0.25 + rep * 0.15

    # Connection/Social: calm + flowing + slightly rhythmic (cooing, babbling)
    connection = (1.0 - ei) * 0.45 + ef * 0.45 + rh * 0.10

    # Fatigue: moderate intensity + repetitive + fragmented flow (fussing)
    # Moderate intensity peaks at ei=0.45 (not too calm, not too distressed)
    moderate_ei = max(0.0, 1.0 - abs(ei - 0.45) * 2.2)
    fatigue = rep * 0.35 + (1.0 - ef) * 0.35 + moderate_ei * 0.30

    # Overstimulation: high intensity + irregular + sustained cry
    overstimulation = ei * 0.50 + (1.0 - rh) * 0.30 + ef * 0.20

    # Exploration: calm + varied sounds + flowing
    exploration = (1.0 - ei) * 0.35 + (1.0 - rep) * 0.35 + ef * 0.30

    raw = {
        "hunger": max(0.0, hunger),
        "discomfort": max(0.0, discomfort),
        "connection": max(0.0, connection),
        "fatigue": max(0.0, fatigue),
        "overstimulation": max(0.0, overstimulation),
        "exploration": max(0.0, exploration),
    }

    return normalize_probability_distribution(raw)


def describe_features_in_words(feature_scores: Dict[str, float], deviation_level: str) -> Dict[str, str]:
    """Translate numeric feature scores into warm, parent-readable descriptions."""
    ei = feature_scores.get("emotional_intensity", 0.5)
    rh = feature_scores.get("rhythm", 0.5)
    rep = feature_scores.get("repetition", 0.5)
    ef = feature_scores.get("expressive_flow", 0.5)

    if ei < 0.30:
        tone = "calm and settled"
    elif ei < 0.55:
        tone = "mildly expressive"
    elif ei < 0.75:
        tone = "noticeably expressive"
    else:
        tone = "highly intense"

    if rh > 0.65:
        pattern = "very rhythmic and regular"
    elif rh > 0.40:
        pattern = "somewhat rhythmic"
    else:
        pattern = "irregular and varied"

    if rep > 0.65:
        repetition = "repeating the same sounds"
    elif rep > 0.40:
        repetition = "some repeated patterns"
    else:
        repetition = "varied, changing sounds"

    if ef > 0.60:
        flow = "long, continuous vocalizations"
    elif ef > 0.35:
        flow = "moderate length with some pauses"
    else:
        flow = "short bursts with pauses"

    baseline_map = {
        "none": "within baby's normal baseline",
        "low": "slightly different from usual",
        "moderate": "noticeably different from usual",
        "high": "significantly different from usual",
    }

    return {
        "emotional_tone": tone,
        "sound_pattern": pattern,
        "repetition": repetition,
        "continuity": flow,
        "vs_baseline": baseline_map.get(deviation_level, "within normal range"),
    }


def compute_emotion_profile(
    feature_scores: Dict[str, float],
    rich_features: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Build a richer emotional-state profile without changing the core intent classes.

    Output states are parent-facing descriptors (not medical labels):
      hungry_or_need, discomfort, sleepy, overstimulated, connection_seeking,
      curious, happy, cozy, frustrated, afraid_signal
    """
    rf = rich_features or {}
    ei = float(feature_scores.get("emotional_intensity", 0.5))
    rh = float(feature_scores.get("rhythm", 0.5))
    rep = float(feature_scores.get("repetition", 0.5))
    ef = float(feature_scores.get("expressive_flow", 0.5))

    cry_fraction = float(rf.get("cry_fraction", 0.0))
    jitter_pct = float(rf.get("jitter_percent", 0.0))
    hnr_db = float(rf.get("hnr_db", 0.0))
    syllable_rate = float(rf.get("syllable_rate", 0.0))
    pause_ratio = float(rf.get("pause_ratio", 0.5))

    hungry_or_need = ei * 0.45 + rh * 0.25 + rep * 0.10 + min(cry_fraction, 0.6) * 0.20
    discomfort = ei * 0.50 + (1.0 - rh) * 0.25 + min(jitter_pct / 20.0, 1.0) * 0.25
    sleepy = rep * 0.35 + (1.0 - ef) * 0.35 + max(0.0, 0.5 - ei) * 0.30
    overstimulated = ei * 0.55 + (1.0 - rh) * 0.20 + ef * 0.25
    connection_seeking = (1.0 - ei) * 0.35 + ef * 0.40 + min(hnr_db / 20.0, 1.0) * 0.25
    curious = (1.0 - ei) * 0.25 + (1.0 - rep) * 0.30 + min(syllable_rate / 6.0, 1.0) * 0.45
    happy = (1.0 - ei) * 0.30 + ef * 0.30 + min(hnr_db / 22.0, 1.0) * 0.40
    cozy = (1.0 - ei) * 0.40 + ef * 0.35 + max(0.0, 0.4 - pause_ratio) * 0.25
    frustrated = ei * 0.40 + rep * 0.20 + (1.0 - ef) * 0.20 + min(jitter_pct / 18.0, 1.0) * 0.20
    afraid_signal = ei * 0.45 + (1.0 - rh) * 0.20 + min(cry_fraction, 0.6) * 0.20 + min(jitter_pct / 20.0, 1.0) * 0.15

    states = {
        "hungry_or_need": max(0.0, min(1.0, hungry_or_need)),
        "discomfort": max(0.0, min(1.0, discomfort)),
        "sleepy": max(0.0, min(1.0, sleepy)),
        "overstimulated": max(0.0, min(1.0, overstimulated)),
        "connection_seeking": max(0.0, min(1.0, connection_seeking)),
        "curious": max(0.0, min(1.0, curious)),
        "happy": max(0.0, min(1.0, happy)),
        "cozy": max(0.0, min(1.0, cozy)),
        "frustrated": max(0.0, min(1.0, frustrated)),
        "afraid_signal": max(0.0, min(1.0, afraid_signal)),
    }

    ordered = sorted(states.items(), key=lambda x: -x[1])
    top = [{"key": k, "score": round(v, 3)} for k, v in ordered[:3]]
    return {
        "states": {k: round(v, 3) for k, v in states.items()},
        "top_states": top,
    }


def compute_private_language_signal(
    cluster: Dict,
    semantic_bridge: Optional[Dict],
    session_count: int,
) -> Dict[str, Any]:
    """
    Derive a parent-facing private-language signal.
    """
    cluster_freq = int(cluster.get("frequency_count") or 0)
    reinforce = float(cluster.get("reinforcement_weight") or 0.0)
    semantic_alignment = float(cluster.get("semantic_alignment_score") or 0.0)

    word = None
    word_conf = 0.0
    word_count = 0
    if semantic_bridge:
        word = semantic_bridge.get("word_token")
        word_conf = float(semantic_bridge.get("semantic_confidence_score") or 0.0)
        word_count = int(semantic_bridge.get("co_occurrence_count") or 0)

    if cluster_freq >= 8 and reinforce >= 0.65 and (word_count >= 3 or semantic_alignment >= 0.6):
        level = "established"
    elif cluster_freq >= 3 or word_count >= 2 or semantic_alignment >= 0.35:
        level = "emerging"
    else:
        level = "forming"

    if level == "established":
        message = "A stable personal sound pattern is forming. This is likely part of your baby's private communication system."
    elif level == "emerging":
        message = "A repeatable personal pattern is emerging. A few more sessions can make this mapping more reliable."
    else:
        if session_count <= 2:
            message = "This is an early estimate from limited data. Continue recording to personalize your baby's private-language map."
        else:
            message = "No stable private-language mapping yet for this pattern. More repeated sessions are needed."

    return {
        "level": level,
        "cluster_frequency": cluster_freq,
        "reinforcement_weight": round(reinforce, 3),
        "semantic_alignment_score": round(semantic_alignment, 3),
        "word_candidate": word,
        "word_candidate_confidence": round(word_conf, 3),
        "word_co_occurrence_count": word_count,
        "message": message,
    }


# =============================================================================
# [Phase 4] Three-Source Evidence Model - replaces 70/30 two-source model
# =============================================================================

def determine_cluster_stability(cluster: Dict) -> str:
    """Determine cluster stability label."""
    frequency_count = cluster.get("frequency_count", 1)
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    if frequency_count >= 10 and reinforcement_weight >= 0.7:
        return "stable"
    elif frequency_count >= 5 or reinforcement_weight >= 0.5:
        return "emerging"
    else:
        return "forming"


# =============================================================================
# Bedrock Insight Generation
# =============================================================================

def _parse_bedrock_json(text: str) -> Optional[Dict]:
    """Robustly parse JSON from Bedrock response."""
    text = text.strip()

    # Strip code block markers
    if "```" in text:
        parts = re.split(r'```(?:json)?', text)
        for part in parts:
            part = part.strip().rstrip('`').strip()
            if part.startswith('{'):
                text = part
                break

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract first {...} object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def generate_insight_with_bedrock(
    cluster: Dict,
    probable_intent: Dict,
    feature_narrative: Dict,
    semantic_bridge: Optional[Dict],
    emotion_profile: Optional[Dict] = None,
    private_language_signal: Optional[Dict] = None,
    session_count: int = 0,
    developmental_stage: str = "UNKNOWN",
    session_context: Optional[Dict] = None,
    child_name: str = "",
) -> Dict:
    """
    Generate structured 3-section parent insight using Amazon Bedrock Claude.
    Falls back to rule-based sections if Bedrock fails.
    """
    try:
        bedrock = boto3.client("bedrock-runtime")
        model_id = os.environ.get("BEDROCK_MODEL_ID", BEDROCK_MODEL_ID)

        cluster_count = cluster.get("frequency_count", 1)
        stability = determine_cluster_stability(cluster)
        confidence_pct = int(probable_intent["confidence"] * 100)
        intent_label = probable_intent["label"]

        alt_intents = probable_intent.get("top_intents", [])[1:3]
        alt_text = "\n".join(
            [f"- {i['label']} ({int(i['weight'] * 100)}%)" for i in alt_intents]
        ) if alt_intents else "- No strong alternatives"

        word_note = ""
        if semantic_bridge:
            word_note = (
                f"\n- Baby has said '{semantic_bridge.get('word_token')}' "
                f"near this pattern {semantic_bridge.get('co_occurrence_count', 1)} time(s)"
            )

        # Context note for Bedrock
        ctx_notes = []
        if session_context:
            fma = session_context.get("feeding_minutes_ago")
            if isinstance(fma, (int, float)):
                ctx_notes.append(f"last feeding approximately {int(fma)} minutes ago")
            health = session_context.get("health_state", "")
            if health and health not in ("unknown", ""):
                ctx_notes.append(f"health state: {health}")
        context_note = (
            "\nSESSION CONTEXT:\n- " + "\n- ".join(ctx_notes)
            if ctx_notes else ""
        )

        stage_label = developmental_stage.replace("_", " ").title()
        name_line = f"\nBABY'S NAME: {child_name}" if child_name else ""
        is_first_session = session_count <= 1
        first_session_note = (
            "\nCOLD START NOTE:\n- This appears to be this baby's first analyzed session. "
            "Provide an initial best estimate and clearly mention uncertainty."
            if is_first_session else ""
        )

        emotion_note = ""
        if emotion_profile and emotion_profile.get("top_states"):
            e = emotion_profile["top_states"]
            emotion_note = (
                "\nEMOTION PROFILE:\n"
                f"- Top state 1: {e[0]['key']} ({int(e[0]['score'] * 100)}%)\n"
                f"- Top state 2: {e[1]['key']} ({int(e[1]['score'] * 100)}%)\n"
                f"- Top state 3: {e[2]['key']} ({int(e[2]['score'] * 100)}%)"
            )

        private_note = ""
        if private_language_signal:
            private_note = (
                "\nPRIVATE LANGUAGE SIGNAL:\n"
                f"- Level: {private_language_signal.get('level', 'forming')}\n"
                f"- Message: {private_language_signal.get('message', '')}"
            )

        prompt = f"""You are Qleam, a supportive baby communication assistant helping parents understand their infant's sounds.

AUDIO ANALYSIS FROM THIS SESSION:
- Emotional tone: {feature_narrative['emotional_tone']}
- Sound pattern: {feature_narrative['sound_pattern']}
- Repetition: {feature_narrative['repetition']}
- Continuity: {feature_narrative['continuity']}
- Compared to baby's usual: {feature_narrative['vs_baseline']}

BABY'S DEVELOPMENTAL STAGE: {stage_label}{name_line}{context_note}
{emotion_note}
{private_note}
{first_session_note}

PATTERN HISTORY:
- This sound pattern has been recorded {cluster_count} time(s) for this baby
- Pattern maturity: {stability} (forming -> emerging -> stable)
- Primary signal: {intent_label} ({confidence_pct}% confidence){word_note}

Alternative possibilities:
{alt_text}

Return ONLY a JSON object with exactly these three fields:
{{
  "what_i_hear": "1-2 sentences describing what the audio shows. Mention specific sound characteristics. Warm and plain language.",
  "what_it_means": "1-2 sentences about what this often suggests. Use uncertain language: 'often suggests', 'may indicate', 'many babies do this when'. Never diagnose.",
  "what_to_try": ["specific actionable step 1", "specific actionable step 2", "specific actionable step 3"]
}}

Guidelines:
- Write for a new parent who needs clear, warm, reassuring support
- Never use medical or clinical terms
- Keep each sentence under 20 words
- Each action step: max 10 words, start with a verb, immediately doable
- If baby's name is provided, use it naturally 1-2 times (e.g., "Emma's sounds suggest...")
- If confidence is low or pattern is still forming, acknowledge gently
- If first session, explicitly say this is an initial estimate that improves with more recordings
- Return ONLY the JSON object, no other text"""

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 450,
            "temperature": 0.35,
            "messages": [{"role": "user", "content": prompt}]
        })

        response = bedrock.invoke_model(modelId=model_id, body=body)
        result = json.loads(response["body"].read())
        raw_text = result["content"][0]["text"]

        sections = _parse_bedrock_json(raw_text)
        if sections and "what_i_hear" in sections:
            if isinstance(sections.get("what_to_try"), str):
                sections["what_to_try"] = [sections["what_to_try"]]
            return {
                "what_i_hear": sections.get("what_i_hear", ""),
                "what_it_means": sections.get("what_it_means", ""),
                "what_to_try": sections.get("what_to_try", [])[:3],
                "source": "bedrock",
            }

        raise ValueError(f"Could not parse Bedrock JSON: {raw_text[:200]}")

    except Exception as e:
        logger.warning(f"Bedrock failed, using rule-based: {e}")
        return get_rule_based_sections(
            probable_intent.get("key", "distress_unknown"),
            developmental_stage=developmental_stage,
            feature_narrative=feature_narrative,
            child_name=child_name,
        )


# =============================================================================
# Build Insight
# =============================================================================

def _estimate_acoustic_reliability(session: Dict) -> float:
    """
    Estimate how much to trust acoustic evidence for this session.
    Uses quality gate + diarization mix indicators.
    """
    reliability = 1.0

    qg = session.get("quality_gate") or {}
    snr_db = float(qg.get("snr_db", 0.0) or 0.0)
    silence_ratio = float(qg.get("silence_ratio", 0.0) or 0.0)
    clipping_ratio = float(qg.get("clipping_ratio", 0.0) or 0.0)

    if snr_db > 0:
        if snr_db < 8:
            reliability *= 0.72
        elif snr_db < 12:
            reliability *= 0.82
        elif snr_db < 16:
            reliability *= 0.92

    if silence_ratio > 0.80:
        reliability *= 0.82
    elif silence_ratio > 0.65:
        reliability *= 0.90

    if clipping_ratio > 0.02:
        reliability *= 0.88

    diar = session.get("diarization") or {}
    adult_fraction = float(diar.get("adult_audio_fraction", 0.0) or 0.0)
    baby_fraction = float(diar.get("baby_audio_fraction", 1.0) or 1.0)

    if adult_fraction > 0.20:
        reliability *= max(0.70, 1.0 - (adult_fraction - 0.20) * 0.55)
    if baby_fraction < 0.45:
        reliability *= 0.85

    return round(max(0.45, min(1.0, reliability)), 3)


def build_insight(
    session: Dict,
    profile: Dict,
    cluster: Dict,
    semantic_bridge: Optional[Dict],
) -> Dict:
    """Build the enhanced structured insight output (Phase 4 - Three-Source Evidence Model)."""

    feature_scores  = session.get("feature_scores", {})
    deviation_level = session.get("deviation_level", "none")
    deviation_score = session.get("deviation_score", 0.0)

    # Phase 3 data stored in session by feature_extraction Lambda
    rich_features     = session.get("rich_features") or {}
    session_context   = session.get("session_context") or {}
    speech_evidence   = session.get("speech_evidence") or _collect_speech_evidence(session, force_transcribe=True)
    transcript        = speech_evidence.get("transcript")
    detected_words    = speech_evidence.get("detected_words", [])
    age_mismatch      = speech_evidence.get("age_mismatch_evidence", {})
    segment_summary   = speech_evidence.get("segment_summary") or ((session.get("segment_evidence") or {}).get("summary") or {})

    # Developmental stage: prefer session-level (recorded at analysis time), fall back to profile
    developmental_stage = (
        session.get("developmental_stage")
        or profile.get("developmental_stage")
        or "UNKNOWN"
    )

    # Phase 4: pull session count, trust scores, and baby name from child profile
    session_count        = int(profile.get("session_count") or 0)
    parent_trust_score   = float(profile.get("parent_trust_score") or 0.5)
    context_reliability  = float(profile.get("context_reliability") or 0.8)
    acoustic_reliability = _estimate_acoustic_reliability(session)
    child_name           = str(profile.get("name") or "")

    # 1. Feature narrative - always computed from audio data, no feedback involved
    feature_narrative = describe_features_in_words(feature_scores, deviation_level)
    emotion_profile = compute_emotion_profile(feature_scores, rich_features)
    secondary_signals = _infer_secondary_signals(
        feature_scores,
        rich_features,
        segment_summary=segment_summary,
    )

    # 2. [Phase 4] Three-source evidence model: 60% acoustic + 15% research + 25% feedback
    #    [Phase 8] Research prior replaced by FL population prior when available + reliable
    #    Confidence capped by session count; feedback weight scaled by parent trust score (FRS)
    population_prior = get_population_prior(developmental_stage)
    training_dataset = get_training_dataset_profile(developmental_stage)
    managed_inference = invoke_sagemaker_intent_endpoint(session, developmental_stage)
    if not (managed_inference.get("acoustic_scores") or {}):
        internal_inference = invoke_internal_stage_model(session, developmental_stage)
        if internal_inference.get("acoustic_scores"):
            managed_inference = internal_inference
    managed_acoustic_scores = managed_inference.get("acoustic_scores") or {}
    managed_acoustic_meta = managed_inference.get("acoustic_meta") or {}
    managed_emotion_profile = managed_inference.get("emotion_profile")
    if isinstance(managed_emotion_profile, dict):
        emotion_profile = managed_emotion_profile

    probable_intent = determine_probable_intent_v2(
        cluster=cluster,
        feature_scores=feature_scores,
        rich_features=rich_features,
        external_acoustic_scores=managed_acoustic_scores,
        external_acoustic_meta=managed_acoustic_meta,
        developmental_stage=developmental_stage,
        session_context=session_context,
        session_count=session_count,
        parent_trust_score=parent_trust_score,
        context_reliability=context_reliability,
        acoustic_reliability=acoustic_reliability,
        population_prior=population_prior,
        training_dataset_prior=training_dataset.get("prior"),
        training_dataset_n=int(training_dataset.get("n") or 0),
        training_dataset_reliable=bool(training_dataset.get("is_reliable")),
    )
    probable_intent = _calibrate_probable_intent_with_phase_rules(
        probable_intent=probable_intent,
        developmental_stage=developmental_stage,
        feature_scores=feature_scores,
        rich_features=rich_features,
        speech_evidence=speech_evidence,
        secondary_signals=secondary_signals,
    )
    cluster_stability = determine_cluster_stability(cluster)
    private_language_signal = compute_private_language_signal(
        cluster=cluster,
        semantic_bridge=semantic_bridge,
        session_count=session_count,
    )

    # 3. Generate insight sections (Bedrock or rule-based)
    use_bedrock = os.environ.get("USE_BEDROCK", str(USE_BEDROCK)).lower() == "true"
    if use_bedrock:
        insight_sections = generate_insight_with_bedrock(
            cluster, probable_intent, feature_narrative, semantic_bridge,
            emotion_profile=emotion_profile,
            private_language_signal=private_language_signal,
            session_count=session_count,
            developmental_stage=developmental_stage,
            session_context=session_context,
            child_name=child_name,
        )
    else:
        insight_sections = get_rule_based_sections(
            probable_intent["key"],
            developmental_stage=developmental_stage,
            feature_narrative=feature_narrative,
            child_name=child_name,
        )
    insight_sections = _augment_sections_with_evidence(
        insight_sections,
        speech_evidence=speech_evidence,
        secondary_signals=secondary_signals,
    )

    # First-session hardening: never overstate confidence on cold start text.
    if session_count <= 1:
        cold_start_line = "This is an initial estimate from the first recording and will personalize with more sessions."
        if cold_start_line not in insight_sections.get("what_it_means", ""):
            insight_sections["what_it_means"] = (
                (insight_sections.get("what_it_means", "") + " " + cold_start_line).strip()
            )

    # 4. Semantic alignment (if word detected)
    semantic_alignment = None
    if semantic_bridge:
        semantic_alignment = {
            "word_detected": semantic_bridge.get("word_token"),
            "alignment_confidence": round(float(semantic_bridge.get("semantic_confidence_score", 0)), 3),
            "co_occurrence_count": semantic_bridge.get("co_occurrence_count", 0),
        }

    insight = {
        "observed_pattern": {
            "emotional_intensity": round(feature_scores.get("emotional_intensity", 0), 3),
            "rhythm": round(feature_scores.get("rhythm", 0), 3),
            "repetition": round(feature_scores.get("repetition", 0), 3),
            "expressive_flow": round(feature_scores.get("expressive_flow", 0), 3),
            "deviation": deviation_level,
            "deviation_score": round(deviation_score, 3),
            "cluster_stability": cluster_stability,
            "cluster_frequency": cluster.get("frequency_count", 1),
        },
        "feature_narrative": feature_narrative,
        "emotion_profile": emotion_profile,
        "probable_intent": probable_intent,
        "speaker_gate": session.get("speaker_gate"),
        "speaker_warning": session.get("speaker_warning"),
        "semantic_alignment": semantic_alignment,
        "private_language_signal": private_language_signal,
        "speech_transcript": transcript,
        "detected_words": detected_words,
        "age_mismatch_evidence": age_mismatch,
        "speech_evidence": {
            "presence_score": speech_evidence.get("speech_presence_score", 0.0),
            "presence_label": speech_evidence.get("speech_presence_label", "non_speech_or_cry"),
            "transcribe_attempted": bool(speech_evidence.get("transcribe_attempted", False)),
            "segment_summary": segment_summary,
        },
        "speaker_authenticity": {
            "status": (session.get("speaker_gate") or {}).get("status", "UNKNOWN"),
            "speaker_type": (session.get("speaker_gate") or {}).get("speaker_type", "unknown"),
            "speaker_category": (session.get("speaker_gate") or {}).get("speaker_category", "unknown"),
            "bio_confidence": (session.get("speaker_gate") or {}).get("bio_confidence", 0.0),
            "spoof_likelihood": (session.get("speaker_gate") or {}).get("spoof_likelihood", 0.0),
            "adult_fraction": (session.get("speaker_gate") or {}).get("adult_fraction", 0.0),
            "baby_fraction": (session.get("speaker_gate") or {}).get("baby_fraction", 0.0),
        },
        "secondary_signals": secondary_signals,
        "segment_evidence": session.get("segment_evidence") or {},
        "managed_inference": managed_inference.get("managed_model"),
        "training_dataset_profile": {
            "n": int(training_dataset.get("n") or 0),
            "is_reliable": bool(training_dataset.get("is_reliable")),
        },
        "acoustic_reliability": acoustic_reliability,
        "insight_sections": insight_sections,
        # Backward-compat flat text
        "suggested_response": "  |  ".join(insight_sections.get("what_to_try", [])),
        "readiness_score": round(profile.get("readiness_score", 0.5), 3),
        "language_maturity_level": profile.get("language_maturity_level", "pre-linguistic"),
        "developmental_stage": developmental_stage,
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return insight


# =============================================================================
# Save Insight
# =============================================================================

def _build_rejection_insight(
    session: Dict, 
    reason: str = "quality",
    speaker_type: str = "unknown",
    speaker_category: str = "unknown",
    expected_stage: str = "",
) -> Dict:
    """
    Lightweight insight returned when recording cannot be analysed.

    reason values:
      "quality"     - no signal / no vocal activity / too short
      "adult"       - biological validation flagged adult voice
      "mismatch"    - speaker type doesn't match expected child
    """
    speech_evidence = _collect_speech_evidence(session, force_transcribe=True)
    transcript = speech_evidence.get("transcript")
    detected_words = speech_evidence.get("detected_words", [])
    age_mismatch = speech_evidence.get("age_mismatch_evidence", {})

    source = "quality-rejection"
    if reason == "adult" or reason == "mismatch":
        source = "speaker-rejection"
        transcript_note = ""
        if transcript and transcript.get("text"):
            transcript_note = f" Detected speech snippet: \"{transcript.get('text', '')[:120]}\"."

        # Build specific message based on detected speaker category
        if speaker_category in ("adult_male", "adult_female") or speaker_type == "adult":
            what_i_hear = (
                "This recording contains an adult voice, not baby sounds. "
                "I detected adult vocal characteristics: low pitch and stable voice quality."
            )
            what_it_means = (
                "The audio patterns clearly match an adult speaker. "
                "For accurate analysis, the recording needs to capture your baby's actual vocalizations."
            )
            label = "Adult voice detected"
        elif speaker_category == "child" or speaker_type == "child":
            what_i_hear = (
                "This recording sounds like an older child (2-5 years), not a baby. "
                "The voice has characteristics of a child who can already speak in sentences."
            )
            what_it_means = (
                "The audio patterns match a child with developed speech, "
                "which is different from the baby's expected developmental stage. "
                "Please ensure you're recording the correct child."
            )
            label = "Older child voice detected"
        elif speaker_category == "toddler" or speaker_type == "toddler":
            what_i_hear = (
                "This recording sounds like a toddler (1-2 years), not a younger baby. "
                "The voice patterns show early word formation and more developed vocalization."
            )
            what_it_means = (
                "The audio suggests a toddler who is learning to talk, "
                "which may be different from the registered child's age. "
                "If your child is younger, please ensure you're recording the right child."
            )
            label = "Toddler voice detected"
        else:
            what_i_hear = "This recording contains a voice that doesn't match the expected child profile."
            what_it_means = (
                "The voice characteristics don't match what we expect for this child's age. "
                "Please ensure you're recording the correct child."
            )
            label = "Voice mismatch detected"

        if transcript_note:
            what_it_means = (what_it_means + transcript_note).strip()
        if detected_words:
            detected_preview = ", ".join([w.get("word", "") for w in detected_words[:4] if w.get("word")])
            if detected_preview:
                what_it_means = (
                    f"{what_it_means} Detected words: {detected_preview}."
                ).strip()
        
        what_to_try = [
            "Wait for your baby to make sounds naturally, then record",
            "Make sure you're close to your baby (20-30 cm) during recording",
            "Stay quiet yourself - only record the baby's vocalizations",
            "If someone else was speaking, try a new recording with just the baby",
        ]
    else:
        what_i_hear = "We couldn't detect clear baby sounds in this recording."
        what_it_means = (
            "This usually means the recording was too quiet, too short, or "
            "captured background noise rather than your baby's voice."
        )
        if transcript and transcript.get("text"):
            what_it_means = (
                f"{what_it_means} Speech was detected in the clip: \"{str(transcript.get('text', ''))[:120]}\"."
            ).strip()
        if detected_words:
            detected_preview = ", ".join([w.get("word", "") for w in detected_words[:4] if w.get("word")])
            if detected_preview:
                what_it_means = (
                    f"{what_it_means} Detected words: {detected_preview}."
                ).strip()
        what_to_try = [
            "Hold the phone 20-30 cm from your baby's mouth",
            "Record somewhere quieter if possible",
            "Try again when baby is actively making sounds",
            "Make sure baby is cooing, babbling, or crying - not silent",
        ]
        label = "No baby sounds detected"

    return {
        "probable_intent": {
            "key": "non_baby_spoof_noise",
            "label": label,
            "confidence": 0.0,
            "confidence_tier": "low",
        },
        "insight_sections": {
            "what_i_hear": what_i_hear,
            "what_it_means": what_it_means,
            "what_to_try": what_to_try,
            "source": source,
        },
        "speaker_type_detected": speaker_type,
        "speaker_category_detected": speaker_category,
        "speaker_gate": (session.get("speaker_gate") or {}).get("status"),
        "speech_transcript": transcript,
        "detected_words": detected_words,
        "age_mismatch_evidence": age_mismatch,
        "speech_evidence": {
            "presence_score": speech_evidence.get("speech_presence_score", 0.0),
            "presence_label": speech_evidence.get("speech_presence_label", "non_speech_or_cry"),
            "transcribe_attempted": bool(speech_evidence.get("transcribe_attempted", False)),
            "segment_summary": speech_evidence.get("segment_summary", {}),
        },
        "segment_evidence": session.get("segment_evidence") or {},
        # No developmental_stage - don't show a misleading stage label on rejected sessions
        "note": DISCLAIMER,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_insight_to_session(session_id: str, insight: Dict, efp: Optional[Dict] = None):
    """Save generated insight (and EFP) to session record.

    EFP (Expected Feedback Profile) is stored separately on the session so the
    feedback_processor can retrieve it without parsing the full insight blob.
    """
    update_expr = "SET insight = :ins, insight_generated_at = :iga"
    expr_values: Dict = {
        ":ins": _float_to_decimal(insight),
        ":iga": datetime.now(timezone.utc).isoformat(),
    }
    if efp:
        update_expr += ", efp = :efp"
        expr_values[":efp"] = _float_to_decimal(efp)

    session_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression=update_expr,
        ExpressionAttributeValues=expr_values,
    )


def _evaluate_speaker_gate(session: Dict) -> Dict[str, Any]:
    """
    Three-way gate for speaker authenticity:
      - BABY_PASS
      - UNCERTAIN
      - ADULT_REJECT
    """
    biological = session.get("biological", {}) or {}
    diarization = session.get("diarization", {}) or {}
    quality_gate = session.get("quality_gate", {}) or {}

    speaker_type = biological.get("speaker_type", "unknown")
    speaker_category = biological.get("speaker_category", "unknown")
    bio_confidence = float(biological.get("bio_confidence", 0.0) or 0.0)
    spoof_likelihood = float(biological.get("spoof_likelihood", 0.0) or 0.0)

    adult_segments = int(diarization.get("adult_segments_detected", 0) or 0)
    primary_speaker = diarization.get("primary_speaker", "unknown")
    total_segments = int(diarization.get("total_segments", 0) or 0)
    baby_fraction = float(diarization.get("baby_audio_fraction", 1.0) or 1.0)
    adult_fraction = float(diarization.get("adult_audio_fraction", 0.0) or 0.0)
    snr_db = float(quality_gate.get("snr_db", 0.0) or 0.0)
    age_days = session.get("age_days_at_recording")
    age_classification = session.get("age_classification", {}) or {}
    age_class = str(age_classification.get("final_class", "") or "").lower().strip()
    age_conf = float(age_classification.get("confidence", 0.0) or 0.0)
    segment_summary = ((session.get("segment_evidence") or {}).get("summary") or {})
    segment_adult_speech_ratio = float(segment_summary.get("adult_speech_ratio", 0.0) or 0.0)
    segment_speech_ratio = float(segment_summary.get("speech_ratio", 0.0) or 0.0)
    segment_count = int(segment_summary.get("segments_analyzed", 0) or 0)
    speech_evidence = session.get("speech_evidence") or {}
    age_mismatch_evidence = speech_evidence.get("age_mismatch_evidence") or {}
    speech_presence_score = float(speech_evidence.get("speech_presence_score", 0.0) or 0.0)
    mismatch_score = float(age_mismatch_evidence.get("score", 0.0) or 0.0)
    lexical_complexity = float(age_mismatch_evidence.get("lexical_complexity", 0.0) or 0.0)
    transcript_word_count = int(age_mismatch_evidence.get("transcript_word_count", 0) or 0)
    bio_f0 = float(biological.get("f0_hz", 0.0) or 0.0)

    if (
        isinstance(age_days, (int, float))
        and age_days <= 270
        and age_class in ("toddler", "child")
        and age_conf >= 0.72
    ):
        return {
            "status": "AGE_MISMATCH_REJECT",
            "speaker_type": "child",
            "speaker_category": age_class,
            "bio_confidence": round(max(bio_confidence, age_conf), 3),
            "spoof_likelihood": round(spoof_likelihood, 3),
            "adult_fraction": round(adult_fraction, 3),
            "baby_fraction": round(baby_fraction, 3),
            "age_days": int(age_days),
            "age_class_confidence": round(age_conf, 3),
        }

    adult_bio_suspected = (
        biological.get("mimicry_suspected") is True
        or speaker_type == "adult"
        or speaker_category in ("adult_male", "adult_female")
        or spoof_likelihood >= 0.65
    )
    adult_hard_by_age_classifier = (
        age_class in ("adult_female", "adult_male")
        and age_conf >= 0.68
    )
    adult_hard_by_bio = adult_bio_suspected and max(bio_confidence, spoof_likelihood) >= 0.75
    adult_hard_by_primary = (
        primary_speaker in ("adult_male", "adult_female")
        and adult_fraction >= 0.55
        and baby_fraction <= 0.35
    )
    adult_hard_by_dominance = (
        total_segments > 0
        and adult_segments >= 2
        and adult_fraction >= 0.65
        and baby_fraction < 0.25
    )
    adult_hard_by_spoof = spoof_likelihood >= 0.82 and adult_fraction >= 0.15
    adult_hard_by_segments = (
        segment_count >= 2
        and segment_adult_speech_ratio >= 0.45
        and (adult_fraction >= 0.25 or segment_speech_ratio >= 0.35)
    )
    adult_hard_by_lexical_voice = (
        transcript_word_count >= 5
        and speech_presence_score >= 0.72
        and lexical_complexity >= 0.55
        and (
            (bio_f0 > 0 and bio_f0 < 235 and spoof_likelihood >= 0.40)
            or (age_class in ("adult_female", "adult_male") and age_conf >= 0.55)
        )
    )
    lexical_hard_mismatch = False
    if isinstance(age_days, (int, float)) and transcript_word_count >= 2:
        if age_days < 180 and mismatch_score >= 0.58:
            lexical_hard_mismatch = True
        elif age_days < 366 and mismatch_score >= 0.72:
            lexical_hard_mismatch = True

    if (
        adult_hard_by_age_classifier
        or adult_hard_by_bio
        or adult_hard_by_primary
        or adult_hard_by_dominance
        or adult_hard_by_spoof
        or adult_hard_by_segments
        or adult_hard_by_lexical_voice
    ):
        return {
            "status": "ADULT_REJECT",
            "speaker_type": speaker_type,
            "speaker_category": speaker_category,
            "bio_confidence": round(bio_confidence, 3),
            "spoof_likelihood": round(spoof_likelihood, 3),
            "adult_fraction": round(adult_fraction, 3),
            "baby_fraction": round(baby_fraction, 3),
            "age_mismatch_score": round(mismatch_score, 3),
            "speech_presence_score": round(speech_presence_score, 3),
            "lexical_complexity": round(lexical_complexity, 3),
            "segment_adult_speech_ratio": round(segment_adult_speech_ratio, 3),
        }

    if lexical_hard_mismatch:
        return {
            "status": "AGE_MISMATCH_REJECT",
            "speaker_type": speaker_type,
            "speaker_category": speaker_category or "child",
            "bio_confidence": round(max(bio_confidence, age_conf), 3),
            "spoof_likelihood": round(spoof_likelihood, 3),
            "adult_fraction": round(adult_fraction, 3),
            "baby_fraction": round(baby_fraction, 3),
            "age_days": int(age_days),
            "age_class_confidence": round(age_conf, 3),
            "age_mismatch_score": round(mismatch_score, 3),
            "message": "Detected lexical speech appears too advanced for the registered age profile.",
        }

    # Soft-warning gate: require corroborating evidence (not spoof-only) to
    # reduce false "adult imitation" warnings on laptop/headset recordings.
    soft_signals = 0
    if adult_bio_suspected and max(bio_confidence, spoof_likelihood) >= 0.62:
        soft_signals += 1
    if spoof_likelihood >= 0.62:
        soft_signals += 1
    if adult_segments > 0 and adult_fraction >= 0.30:
        soft_signals += 1
    if primary_speaker in ("adult_male", "adult_female") and adult_fraction >= 0.35:
        soft_signals += 1
    if mismatch_score >= 0.60 and transcript_word_count >= 2:
        soft_signals += 1
    if segment_adult_speech_ratio >= 0.30:
        soft_signals += 1
    if transcript_word_count >= 4 and speech_presence_score >= 0.62 and lexical_complexity >= 0.45:
        soft_signals += 1

    # In lower-SNR recordings, raise bar for uncertain warnings unless
    # diarization also supports adult presence.
    if snr_db < 12.0 and soft_signals > 0 and adult_fraction < 0.25:
        soft_signals = max(0, soft_signals - 1)

    uncertain = bool(
        soft_signals >= 2
        or (spoof_likelihood >= 0.75 and adult_fraction >= 0.10)
    )

    if uncertain:
        if mismatch_score >= 0.60 and transcript_word_count >= 2:
            msg = "Speech complexity appears age-mismatched; recording may include an older speaker."
        elif spoof_likelihood >= 0.55:
            msg = "Possible adult imitation pattern detected; insight is based on isolated baby-like segments."
        else:
            msg = "Mixed speakers detected; insight is based on baby-segment analysis."
        return {
            "status": "UNCERTAIN",
            "speaker_type": speaker_type,
            "speaker_category": speaker_category,
            "message": msg,
            "bio_confidence": round(bio_confidence, 3),
            "spoof_likelihood": round(spoof_likelihood, 3),
            "adult_fraction": round(adult_fraction, 3),
            "baby_fraction": round(baby_fraction, 3),
            "soft_signal_count": soft_signals,
            "age_mismatch_score": round(mismatch_score, 3),
            "segment_adult_speech_ratio": round(segment_adult_speech_ratio, 3),
        }

    return {
        "status": "BABY_PASS",
        "speaker_type": speaker_type,
        "speaker_category": speaker_category,
        "bio_confidence": round(bio_confidence, 3),
        "spoof_likelihood": round(spoof_likelihood, 3),
        "adult_fraction": round(adult_fraction, 3),
        "baby_fraction": round(baby_fraction, 3),
        "age_mismatch_score": round(mismatch_score, 3),
        "segment_adult_speech_ratio": round(segment_adult_speech_ratio, 3),
    }


def _critical_quality_reject(session: Dict) -> Dict[str, Any]:
    """
    Decide whether quality should hard-reject in insight stage.

    no_vocal_activity_detected is treated as hard-reject only when there is
    very weak signal evidence and no downstream vocal evidence.
    """
    quality_gate = session.get("quality_gate", {}) or {}
    issues = quality_gate.get("issues", []) or []
    passed = bool(quality_gate.get("passed", True))
    if passed or not issues:
        return {"reject": False, "critical_issues": []}

    critical_issues = [
        i for i in issues
        if any(str(i).startswith(p) for p in _CRITICAL_GATE_ISSUES)
    ]

    if "no_vocal_activity_detected" in issues:
        diar = session.get("diarization", {}) or {}
        bio = session.get("biological", {}) or {}
        rich = session.get("rich_features", {}) or {}
        try:
            voiced_fraction = float(quality_gate.get("voiced_energy_fraction", 0.0) or 0.0)
            silence_ratio = float(quality_gate.get("silence_ratio", 1.0) or 1.0)
        except Exception:
            voiced_fraction = 0.0
            silence_ratio = 1.0

        has_voice_evidence = bool(
            int(diar.get("total_segments", 0) or 0) > 0
            or float(diar.get("baby_audio_fraction", 0.0) or 0.0) >= 0.10
            or float(diar.get("adult_audio_fraction", 0.0) or 0.0) >= 0.10
            or str(bio.get("speaker_type", "") or "").strip().lower() in ("infant", "toddler", "child", "adult")
            or float(rich.get("f0_voiced_fraction", 0.0) or 0.0) >= 0.08
            or float(rich.get("cry_fraction", 0.0) or 0.0) >= 0.06
        )
        # Escalate only for near-silence with no vocal evidence at all.
        if (
            voiced_fraction <= 0.02
            and silence_ratio >= 0.95
            and not has_voice_evidence
        ):
            critical_issues.append("no_vocal_activity_detected")

    critical_issues = list(dict.fromkeys(critical_issues))
    return {"reject": bool(critical_issues), "critical_issues": critical_issues}


# =============================================================================
# Lambda Handler
# =============================================================================

def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Insight Generator Lambda handler.

    Args:
        event: {
            "child_id": str,
            "session_id": str,
            "cluster_id": str  # optional only for fast-reject sessions
        }
    """
    logger.info(f"Insight generator started for session {event.get('session_id')}")

    child_id = event["child_id"]
    session_id = event["session_id"]
    cluster_id = event.get("cluster_id")

    # 1. Fetch all required data
    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    # 1a. Reject only on critical quality issues.
    quality_decision = _critical_quality_reject(session)
    if quality_decision.get("reject"):
        logger.warning(
            f"Quality gate failed for session {session_id}, critical issues: "
            f"{quality_decision.get('critical_issues', [])}"
        )
        rejection_insight = _build_rejection_insight(session, reason="quality")
        save_insight_to_session(session_id, rejection_insight)
        return {
            "status": "insight_generated",
            "session_id": session_id,
            "insight": rejection_insight,
        }

    # 1b. Speech evidence bundle for transcript/word/mismatch-aware decisions.
    speech_evidence = _collect_speech_evidence(session, force_transcribe=True)
    session["speech_evidence"] = speech_evidence

    # 1b. Speaker authenticity gate.
    speaker_gate = _evaluate_speaker_gate(session)
    session["speaker_gate"] = speaker_gate

    if speaker_gate.get("status") == "ADULT_REJECT":
        logger.warning(
            f"Speaker gate rejected session {session_id}: "
            f"type={speaker_gate.get('speaker_type')} cat={speaker_gate.get('speaker_category')} "
            f"adult_fraction={speaker_gate.get('adult_fraction', 0.0):.2f} "
            f"baby_fraction={speaker_gate.get('baby_fraction', 0.0):.2f} "
            f"bio_conf={speaker_gate.get('bio_confidence', 0.0):.2f} "
            f"spoof={speaker_gate.get('spoof_likelihood', 0.0):.2f}"
        )
        rejection_insight = _build_rejection_insight(
            session,
            reason="adult",
            speaker_type=speaker_gate.get("speaker_type", "unknown"),
            speaker_category=speaker_gate.get("speaker_category", "unknown"),
        )
        save_insight_to_session(session_id, rejection_insight)
        return {
            "status": "insight_generated",
            "session_id": session_id,
            "insight": rejection_insight,
        }

    if speaker_gate.get("status") == "AGE_MISMATCH_REJECT":
        logger.warning(
            f"Speaker gate mismatch for session {session_id}: "
            f"registered_age_days={speaker_gate.get('age_days')} "
            f"detected={speaker_gate.get('speaker_category')} "
            f"conf={speaker_gate.get('age_class_confidence', 0.0):.2f}"
        )
        rejection_insight = _build_rejection_insight(
            session,
            reason="mismatch",
            speaker_type=speaker_gate.get("speaker_type", "child"),
            speaker_category=speaker_gate.get("speaker_category", "child"),
        )
        save_insight_to_session(session_id, rejection_insight)
        return {
            "status": "insight_generated",
            "session_id": session_id,
            "insight": rejection_insight,
        }

    if speaker_gate.get("status") == "UNCERTAIN":
        session["speaker_warning"] = {
            "message": speaker_gate.get("message"),
            "adult_fraction": speaker_gate.get("adult_fraction"),
            "baby_fraction": speaker_gate.get("baby_fraction"),
            "bio_confidence": speaker_gate.get("bio_confidence"),
            "spoof_likelihood": speaker_gate.get("spoof_likelihood"),
            "age_mismatch_score": speaker_gate.get("age_mismatch_score"),
            "segment_adult_speech_ratio": speaker_gate.get("segment_adult_speech_ratio"),
        }

    # Branch: LINGUISTIC mode sessions get language-development insight
    developmental_mode = session.get("developmental_mode", "")
    age_days = session.get("age_days_at_recording")
    if developmental_mode == "LINGUISTIC" and isinstance(age_days, (int, float)) and age_days < 366:
        logger.warning(
            f"Linguistic mode guard in insight generator: session={session_id} age_days={age_days} "
            "forcing pre-linguistic insight flow"
        )
        developmental_mode = "PRE_LINGUISTIC"
    if developmental_mode == "LINGUISTIC":
        developmental_stage = session.get("developmental_stage", "WORD_COMBINATIONS")
        rich_features = session.get("rich_features", {})
        feature_scores = session.get("feature_scores", {})
        return _generate_linguistic_insight(
            session_id, child_id, developmental_stage, rich_features, feature_scores, session=session
        )

    profile = get_child_profile(child_id)
    if not profile:
        raise ValueError(f"Child profile {child_id} not found")

    if not cluster_id:
        raise ValueError("cluster_id is required for non-rejection sessions")

    cluster = get_cluster(cluster_id)
    if not cluster:
        raise ValueError(f"Cluster {cluster_id} not found")

    semantic_bridge = get_semantic_bridge(cluster_id)

    # 2. Build enhanced insight
    insight = build_insight(session, profile, cluster, semantic_bridge)

    # 3. Extract EFP (Expected Feedback Profile) from insight for delta scoring later
    efp = insight.get("probable_intent", {}).get("evidence", {}).get("blended")

    # 4. Save insight + EFP to session
    save_insight_to_session(session_id, insight, efp=efp)

    logger.info(
        f"Insight generated for session {session_id}: "
        f"intent={insight['probable_intent']['label']} "
        f"confidence={insight['probable_intent']['confidence']:.2%} "
        f"source={insight['insight_sections']['source']}"
    )

    return {
        "status": "insight_generated",
        "session_id": session_id,
        "insight": insight,
    }
