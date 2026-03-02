"""
Qleam — Insight Generator Lambda (Redesigned)
Decision-tree routing: classify first, then only run what's needed.

Pipeline:
  1. Receive classified audio from feature_extraction
  2. Route based on sound type:
     - SPEECH → Transcribe → Show words → Age match → Baby/Adult
     - CRY → Emotion analysis (age-specific) → Show emotion + 3 cards
     - LAUGH → Show happy → Baby/Adult
     - SILENCE → "No sound detected"
     - NOISE → "Unrecognized sound"
  3. Always check: adult gate, words, private language, age mismatch
  4. Check training models (cry emotion, private language)
  5. Generate clean, simple insight for parent display

Trigger: Step Function (after audio classifier)
Input:  { child_id, session_id, ... from feature_extraction output }
Output: Structured insight JSON stored in Session table
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    CONCEPT_GRAPH_TABLE,
    DISCLAIMER,
    MODEL_REGISTRY_TABLE,
    POPULATION_MODEL_TABLE,
    S3_BUCKET_NAME,
    SESSION_TABLE,
    SOUND_CLUSTER_TABLE,
    TRAINING_CANDIDATE_TABLE,
)
from cry_analyzer import analyze_cry, get_age_bracket
from speech_transcriber import transcribe_audio, analyze_words_for_display
from word_analyzer import analyze_words_by_age
from private_language_model import match_private_language
from cry_training_model import predict_cry_emotion, store_vocalization_training_sample
from evidence_model import determine_probable_intent_v3

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE)
sound_cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
population_model_table = dynamodb.Table(POPULATION_MODEL_TABLE)


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
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return Decimal("0")
        return Decimal(str(obj))
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
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


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Insight Generator — decision tree routing.

    Receives classified audio data and generates parent-facing insight
    based on what type of sound was detected.
    """
    logger.info(f"Insight generator started: session={event.get('session_id')}")

    session_id = event["session_id"]
    child_id = event["child_id"]

    # Core classification from feature extraction
    sound_type = event.get("sound_type", "noise")
    is_adult = event.get("is_adult", False)
    routing = event.get("routing", {})
    sound_features = event.get("sound_features", {})
    sound_classification = event.get("sound_classification", {})
    embedding_vector = event.get("embedding_vector", [])
    feature_scores = event.get("feature_scores", {})
    session_context = event.get("session_context")
    age_days = event.get("age_days")
    s3_audio_path = event.get("s3_audio_path", "")
    fast_reject = event.get("fast_reject", False)

    # Get child profile
    profile = _get_child_profile(child_id)

    # Build insight based on routing
    # Include classification scores for the frontend graph
    classification_scores = sound_classification.get("scores", {})
    classification_confidence = sound_classification.get("confidence", 0)

    insight = {
        "sound_type": sound_type,
        "is_adult": is_adult,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER,
        "classification_scores": classification_scores,
        "classification_confidence": classification_confidence,
    }

    # --- Fast reject path ---
    if fast_reject:
        insight["display_type"] = "silence"
        insight["headline"] = "No sound detected to analyze"
        insight["headline_icon"] = "🔇"
        insight["description"] = "The recording was too short or too quiet. Try recording closer to your baby."
        _save_insight(session_id, insight)
        return {"status": "insight_generated", "session_id": session_id, "insight": insight}

    # --- ALWAYS: Check for words via transcription ---
    transcript_result = None
    word_analysis = None
    word_age_analysis = None

    if routing.get("run_transcription", False) or sound_type in ("speech", "mixed"):
        try:
            transcript_result = transcribe_audio(
                s3_audio_path,
                os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME),
                preferred_language="en-US",
            )
            word_analysis = analyze_words_for_display(transcript_result)
            if word_analysis.get("has_words"):
                word_age_analysis = analyze_words_by_age(word_analysis, age_days, is_adult)
                logger.info(f"Words detected: {word_analysis['word_count']} words, "
                           f"speaker={word_age_analysis.get('speaker_assessment', 'unknown')}")
        except Exception as e:
            logger.warning(f"Transcription failed: {e}")

    # --- ALWAYS: Check private baby language ---
    private_lang_match = None
    if embedding_vector and not is_adult:
        try:
            private_lang_match = match_private_language(
                embedding_vector, child_id, concept_graph_table
            )
        except Exception as e:
            logger.warning(f"Private language matching failed: {e}")

    # --- Route by sound type ---
    if sound_type == "silence":
        insight = _build_silence_insight(insight)

    elif sound_type == "noise":
        insight = _build_noise_insight(insight)

    elif sound_type == "laugh":
        insight = _build_laugh_insight(insight, is_adult, age_days,
                                       word_analysis, word_age_analysis, private_lang_match)

    elif sound_type == "cry":
        # Check trained cry model
        trained_cry = None
        age_bracket = get_age_bracket(age_days)
        try:
            trained_cry = predict_cry_emotion(sound_features, age_bracket, model_registry_table)
        except Exception as e:
            logger.warning(f"Cry model prediction failed: {e}")

        insight = _build_cry_insight(
            insight, sound_features, age_days, is_adult,
            trained_cry, word_analysis, word_age_analysis, private_lang_match,
        )

        # --- 4-Source Evidence Model (v3) for intent determination ---
        if not is_adult and feature_scores:
            try:
                # Get developmental stage from profile
                dev_stage = profile.get("developmental_stage", "UNKNOWN")
                session_count = int(profile.get("session_count", 0) or 0)
                parent_trust = float(profile.get("parent_trust_score", 0.5) or 0.5)
                ctx_reliability = float(profile.get("context_reliability", 0.8) or 0.8)

                # Get cluster for this session (if available)
                cluster = _get_sound_cluster(child_id, embedding_vector)

                # Get FL population prior (if available)
                pop_prior = _get_population_prior(dev_stage)

                evidence_result = determine_probable_intent_v3(
                    cluster=cluster,
                    feature_scores=feature_scores,
                    rich_features=sound_features,
                    developmental_stage=dev_stage,
                    session_context=session_context,
                    session_count=session_count,
                    parent_trust_score=parent_trust,
                    context_reliability=ctx_reliability,
                    acoustic_reliability=float(event.get("quality_gate", {}).get("acoustic_reliability", 1.0) or 1.0),
                    population_prior=pop_prior,
                    cry_model_result=trained_cry,
                )

                # Attach evidence model results to insight
                insight["probable_intent"] = evidence_result.get("key")
                insight["intent_label"] = evidence_result.get("label")
                insight["intent_confidence"] = evidence_result.get("confidence")
                insight["top_intents"] = evidence_result.get("top_intents", [])
                insight["evidence"] = evidence_result.get("evidence", {})
                insight["model_version"] = evidence_result.get("model_version", "v3_4source")

                # Store EFP for feedback comparison
                _store_evidence_fingerprint(session_id, evidence_result.get("evidence_fingerprint", {}))
            except Exception as e:
                logger.warning(f"Evidence model v3 failed (non-fatal): {e}")

    elif sound_type == "speech":
        insight = _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
            age_days, private_lang_match, sound_features,
        )

    else:  # mixed
        # For mixed: check which components are present
        insight = _build_mixed_insight(
            insight, sound_classification, sound_features,
            word_analysis, word_age_analysis, is_adult, age_days,
            private_lang_match,
        )

    # Attach language mismatch notice if applicable
    if transcript_result and transcript_result.get("language_mismatch"):
        detected_lang = transcript_result.get("detected_language", "unknown")
        insight["language_mismatch"] = True
        insight["detected_language"] = detected_lang
        insight["language_notice"] = f"Audio detected in {detected_lang}. Transcription may differ from expected language."

    # --- Unified Model A Feeding (Phase 11) ---
    # Feed vocalization emotion training model if emotion detected with confidence
    if not is_adult and sound_type in ("cry", "speech", "mixed", "laugh"):
        detected_emotion = insight.get("emotion")
        emotion_conf = float(insight.get("emotion_confidence", 0) or 0)
        parent_frs = float(profile.get("parent_trust_score", 0.5) or 0.5)

        if detected_emotion and emotion_conf >= 0.45:
            try:
                age_bracket = get_age_bracket(age_days)
                store_vocalization_training_sample(
                    features=sound_features,
                    confirmed_emotion=detected_emotion,
                    age_bracket=age_bracket,
                    sound_type=sound_type,
                    child_id=child_id,
                    session_id=session_id,
                    training_candidate_table=training_candidate_table,
                    frs=parent_frs,
                    emotion_confidence=emotion_conf,
                )
            except Exception as e:
                logger.debug(f"Model A feeding failed (non-fatal): {e}")

    # Save insight
    _save_insight(session_id, insight)

    logger.info(f"Insight generated: session={session_id} type={insight.get('display_type', 'unknown')}")
    return {"status": "insight_generated", "session_id": session_id, "insight": insight}


# ---------------------------------------------------------------------------
# Insight builders per sound type
# ---------------------------------------------------------------------------

def _build_silence_insight(insight: Dict) -> Dict:
    insight["display_type"] = "silence"
    insight["headline"] = "No sound detected"
    insight["headline_icon"] = "🔇"
    insight["description"] = "No sounds were detected in this recording. Try recording when your child is making sounds."
    return insight


def _build_noise_insight(insight: Dict) -> Dict:
    insight["display_type"] = "noise"
    insight["headline"] = "Unrecognized sound"
    insight["headline_icon"] = "🔊"
    insight["description"] = "Background noise or unrecognized sounds were detected. Try recording in a quieter environment, closer to your child."
    return insight


def _build_laugh_insight(
    insight: Dict,
    is_adult: bool,
    age_days: Optional[int],
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    private_lang_match: Optional[Dict],
) -> Dict:
    insight["display_type"] = "laugh"
    is_toddler = age_days is not None and age_days >= 730
    child_label = "child" if is_toddler else "baby"

    if is_adult:
        insight["headline"] = "Laughing detected — Not your baby"
        insight["headline_icon"] = "😄"
        insight["description"] = "Laughter was detected but it appears to be from another person, not your baby."
        insight["adult_detected"] = True
    else:
        insight["headline"] = f"Your {child_label} is laughing!"
        insight["headline_icon"] = "😄"
        insight["description"] = f"Happy, joyful laughter detected. Your {child_label} sounds content and delighted!"

    # Add words if found (always show)
    _attach_word_info(insight, word_analysis, word_age_analysis)

    # Add private language if matched
    _attach_private_language(insight, private_lang_match)

    return insight


def _build_cry_insight(
    insight: Dict,
    sound_features: Dict,
    age_days: Optional[int],
    is_adult: bool,
    trained_cry: Optional[Dict],
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    private_lang_match: Optional[Dict],
) -> Dict:
    insight["display_type"] = "cry"

    # Adult check — also trust word_age_analysis if feature extraction missed it
    word_speaker = (word_age_analysis or {}).get("speaker_assessment", "uncertain")
    if is_adult or word_speaker == "adult":
        insight["headline"] = "Crying detected — Adult voice"
        insight["headline_icon"] = "🔊"
        insight["description"] = "Crying or distress sounds were detected but they appear to be from an adult speaker."
        insight["adult_detected"] = True
        _attach_word_info(insight, word_analysis, word_age_analysis)
        return insight

    # Cry emotion analysis
    cry_result = analyze_cry(
        features=sound_features,
        age_days=age_days,
        trained_model_result=trained_cry,
    )

    insight["headline"] = f"{cry_result['emotion_icon']} {cry_result['emotion_label']}"
    insight["headline_icon"] = cry_result["emotion_icon"]
    insight["emotion"] = cry_result["primary_emotion"]
    insight["emotion_confidence"] = cry_result["confidence"]
    insight["top_emotions"] = cry_result.get("top_emotions", [])

    # Three insight cards
    insight["insight_sections"] = {
        "what_i_hear": cry_result["what_hearing"],
        "what_it_means": cry_result["what_means"],
        "what_to_try": cry_result["what_try"],
    }

    # Dunstan sound reference (0-6m only)
    if cry_result.get("dunstan_sound"):
        insight["dunstan_sound"] = cry_result["dunstan_sound"]

    # Age cry match — only show when brackets are actually different
    age_cry_match = cry_result.get("age_cry_match", {})
    probable_bracket = age_cry_match.get("probable_age_bracket", "")
    registered_bracket = age_cry_match.get("registered_age_bracket", "")
    if age_cry_match.get("mismatch") and probable_bracket and registered_bracket and probable_bracket != registered_bracket:
        insight["age_mismatch"] = {
            "type": "cry_frequency",
            "message": (
                f"Cry pattern suggests {probable_bracket} "
                f"but child is registered as {registered_bracket}"
            ),
            "details": age_cry_match,
        }

    # Also detected emotions (alternatives)
    alt_emotions = [e for e in cry_result.get("top_emotions", [])[1:3] if e.get("score", 0) > 0.15]
    if alt_emotions:
        insight["also_possible"] = alt_emotions

    # Words found during cry (baby might be crying + talking)
    _attach_word_info(insight, word_analysis, word_age_analysis)

    # Private language
    _attach_private_language(insight, private_lang_match)

    return insight


def _build_speech_insight(
    insight: Dict,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    is_adult: bool,
    age_days: Optional[int],
    private_lang_match: Optional[Dict],
    sound_features: Dict,
) -> Dict:
    insight["display_type"] = "speech"

    # Use "child" for 24m+, "baby" for younger
    is_toddler = age_days is not None and age_days >= 730  # ~24 months
    child_label = "child" if is_toddler else "baby"

    if not word_analysis or not word_analysis.get("has_words"):
        # Speech-like sounds but no clear words
        if is_adult:
            insight["headline"] = "Adult speech detected"
            insight["headline_icon"] = "🔊"
            insight["description"] = "Speech sounds were detected from an adult speaker but no clear words could be transcribed."
            insight["adult_detected"] = True
        else:
            insight["headline"] = f"Your {child_label} is vocalizing"
            insight["headline_icon"] = "🗣️"
            if is_toddler:
                insight["description"] = "Your child is making speech sounds! Vocal expression and practice are key to language growth."
            else:
                insight["description"] = "Your baby is making speech-like sounds! Babbling and vocal play are important steps in language development."
            # Check private language
            _attach_private_language(insight, private_lang_match)
        return insight

    # Words found
    words = word_analysis
    age_info = word_age_analysis or {}
    speaker = age_info.get("speaker_assessment", "uncertain")

    if is_adult or speaker == "adult":
        insight["headline"] = "Adult speech detected"
        insight["headline_icon"] = "🔊"
        insight["description"] = f"Speech detected with {words['word_count']} word(s). The voice characteristics suggest an adult speaker."
        insight["adult_detected"] = True
    else:
        if words.get("has_sentences"):
            if is_toddler:
                insight["headline"] = "Your child is speaking in sentences!"
            else:
                insight["headline"] = "Your baby is forming sentences!"
            insight["headline_icon"] = "🗣️"
        elif words["word_count"] > 1:
            insight["headline"] = f"Your {child_label} said {words['word_count']} words!"
            insight["headline_icon"] = "🗣️"
        else:
            insight["headline"] = "Word detected!"
            insight["headline_icon"] = "🗣️"

        insight["description"] = age_info.get("display_summary", f"{words['word_count']} word(s) detected")

    # Always attach word details
    _attach_word_info(insight, word_analysis, word_age_analysis)

    # Private language
    _attach_private_language(insight, private_lang_match)

    return insight


def _build_mixed_insight(
    insight: Dict,
    sound_classification: Dict,
    sound_features: Dict,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    is_adult: bool,
    age_days: Optional[int],
    private_lang_match: Optional[Dict],
) -> Dict:
    """Handle mixed sound types — prioritize what to show."""
    insight["display_type"] = "mixed"

    scores = sound_classification.get("scores", {})
    speech_score = scores.get("speech", 0)
    cry_score = scores.get("cry", 0)
    laugh_score = scores.get("laugh", 0)

    # Priority 1: words detected — always show speech path
    if word_analysis and word_analysis.get("has_words"):
        return _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
            age_days, private_lang_match, sound_features,
        )

    # Priority 2: speech score dominates over cry by a clear margin (>=0.15)
    # Handles case where transcription found no words (e.g. mixed-language speech)
    # but speech signal is clearly stronger than cry
    if speech_score >= cry_score + 0.15:
        return _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
            age_days, private_lang_match, sound_features,
        )

    # Priority 3: cry component present
    if cry_score > 0.3:
        return _build_cry_insight(
            insight, sound_features, age_days, is_adult,
            None, word_analysis, word_age_analysis, private_lang_match,
        )

    if laugh_score > 0.3:
        return _build_laugh_insight(
            insight, is_adult, age_days, word_analysis, word_age_analysis, private_lang_match,
        )

    # Fallback
    insight["headline"] = "Mixed sounds detected"
    insight["headline_icon"] = "🔊"
    insight["description"] = "Multiple sound types were detected. The recording contains a mix of sounds that couldn't be clearly classified."
    _attach_word_info(insight, word_analysis, word_age_analysis)
    _attach_private_language(insight, private_lang_match)
    return insight


# ---------------------------------------------------------------------------
# Helpers for attaching common info
# ---------------------------------------------------------------------------

def _attach_word_info(
    insight: Dict,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
):
    """Attach word/transcript info to insight if words were found."""
    if not word_analysis or not word_analysis.get("has_words"):
        return

    insight["words_detected"] = True
    insight["transcript"] = {
        "text": word_analysis.get("display_text", ""),
        "words": word_analysis.get("display_words", []),
        "word_count": word_analysis.get("word_count", 0),
        "unique_words": word_analysis.get("unique_word_count", 0),
        "has_sentences": word_analysis.get("has_sentences", False),
        "confidence": word_analysis.get("avg_word_confidence", 0),
    }

    if word_age_analysis:
        insight["word_age_match"] = {
            "speaker": word_age_analysis.get("speaker_assessment", "uncertain"),
            "age_match": word_age_analysis.get("age_match", True),
            "registered_age": word_age_analysis.get("registered_age_bracket", ""),
            "probable_age": word_age_analysis.get("probable_age_bracket", ""),
            "summary": word_age_analysis.get("display_summary", ""),
            "mismatch_warning": word_age_analysis.get("mismatch_warning"),
        }


def _attach_private_language(insight: Dict, match: Optional[Dict]):
    """Attach private baby language match info."""
    if not match or not match.get("matched"):
        return

    insight["private_language"] = {
        "matched": True,
        "parent_label": match.get("parent_label", ""),
        "parent_description": match.get("parent_description", ""),
        "similarity": match.get("similarity", 0),
        "times_heard": match.get("observation_count", 0),
        "confidence": match.get("confidence", 0),
    }


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_child_profile(child_id: str) -> Dict:
    try:
        response = child_profile_table.get_item(Key={"child_id": child_id})
        if "Item" in response:
            return _decimal_to_float(response["Item"])
    except Exception as e:
        logger.warning(f"Failed to get child profile: {e}")
    return {"child_id": child_id}


def _save_insight(session_id: str, insight: Dict):
    """Save insight to session record.

    The API handler (get_insight) reads ``session.get("insight")`` to determine
    whether processing is complete, so we must store under the key ``insight``.
    """
    try:
        session_table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET #ins = :ins, insight_generated_at = :ts",
            ExpressionAttributeNames={"#ins": "insight"},
            ExpressionAttributeValues={
                ":ins": _float_to_decimal(insight),
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )
        logger.info(f"Insight saved for session {session_id}")
    except Exception as e:
        logger.error(f"Failed to save insight: {e}")


def _get_sound_cluster(child_id: str, embedding_vector: list) -> Dict:
    """Get the most relevant sound cluster for this child.

    Falls back to an empty cluster dict if none found (evidence model
    handles missing cluster gracefully).
    """
    if not child_id:
        return {}
    try:
        resp = sound_cluster_table.query(
            KeyConditionExpression="child_id = :cid",
            ExpressionAttributeValues={":cid": child_id},
            Limit=1,
            ScanIndexForward=False,
        )
        items = resp.get("Items", [])
        if items:
            return _decimal_to_float(items[0])
    except Exception as e:
        logger.warning(f"Failed to get sound cluster: {e}")
    return {}


def _get_population_prior(developmental_stage: str) -> Optional[Dict[str, float]]:
    """Get FL population prior from PopulationModel table for the given stage."""
    stage = (developmental_stage or "UNKNOWN").upper().strip()
    try:
        resp = population_model_table.get_item(Key={"stage": stage})
        item = resp.get("Item")
        if item:
            prior = _decimal_to_float(item.get("intent_distribution", {}))
            if prior and len(prior) >= 3:
                return prior
    except Exception as e:
        logger.debug(f"No population prior for stage={stage}: {e}")
    return None


def _store_evidence_fingerprint(session_id: str, efp: Dict):
    """Store evidence fingerprint on the session record for feedback comparison."""
    if not efp:
        return
    try:
        session_table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET evidence_fingerprint = :efp",
            ExpressionAttributeValues={":efp": _float_to_decimal(efp)},
        )
    except Exception as e:
        logger.warning(f"Failed to store EFP: {e}")
