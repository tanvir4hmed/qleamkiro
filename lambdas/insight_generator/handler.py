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
  3. Always check: adult gate, words, age mismatch
  4. Check training models (cry emotion)
  5. Generate clean, simple insight for parent display

Trigger: Step Function (after audio classifier)
Input:  { child_id, session_id, ... from feature_extraction output }
Output: Structured insight JSON stored in Session table
"""
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    DISCLAIMER,
    MODEL_REGISTRY_TABLE,
    S3_BUCKET_NAME,
    SESSION_TABLE,
)
from cry_analyzer import analyze_cry, get_age_bracket
from speech_transcriber import transcribe_audio, analyze_words_for_display
from word_analyzer import analyze_words_by_age
from cry_training_model import predict_cry_emotion

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)
CRY_ONLY_MAX_AGE_DAYS = 90


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


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Insight Generator — decision tree routing.

    Receives classified audio data and generates parent-facing insight
    based on what type of sound was detected.
    """
    logger.info(f"Insight generator started: session={event.get('session_id')}")

    session_id = event["session_id"]
    # Core classification from feature extraction
    sound_type = event.get("sound_type", "noise")
    is_adult = event.get("is_adult", False)
    routing = event.get("routing", {})
    sound_features = event.get("sound_features", {})
    sound_classification = event.get("sound_classification", {})
    age_days = event.get("age_days")
    s3_audio_path = event.get("s3_audio_path", "")
    fast_reject = event.get("fast_reject", False)

    # Build insight based on routing
    insight = {
        "sound_type": sound_type,
        "is_adult": is_adult,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER,
    }

    # --- Fast reject path ---
    if fast_reject:
        # insight["display_type"] = "silence"
        insight["display_type"] = event.get("sound_type", "silence")
        # insight["headline"] = "No sound detected to analyze"
        insight["headline"] = event.get("fast_reject_title", "Recording rejected")
        # insight["headline_icon"] = "🔇"
        insight["headline_icon"] = "⚠️"
        # insight["description"] = "The recording was too short or too quiet. Try recording closer to your baby."
        insight["description"] = event.get(
            "fast_reject_message",
            "The recording could not be processed. Please try a clean baby recording.",
        )
        insight["fast_reject_reasons"] = event.get("fast_reject_reasons", [])
        _save_insight(session_id, insight)
        return {"status": "insight_generated", "session_id": session_id, "insight": insight}

    # --- Optional transcription path (disabled for 0-3 month cry-only mode) ---
    transcript_result = None
    word_analysis = None
    word_age_analysis = None

    if _should_run_transcription(sound_type, routing, age_days):
        try:
            transcript_result = transcribe_audio(s3_audio_path, os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME))
            word_analysis = analyze_words_for_display(transcript_result)
            if word_analysis.get("has_words"):
                word_age_analysis = analyze_words_by_age(word_analysis, age_days, is_adult)
                logger.info(f"Words detected: {word_analysis['word_count']} words, "
                           f"speaker={word_age_analysis.get('speaker_assessment', 'unknown')}")
        except Exception as e:
            logger.warning(f"Transcription failed: {e}")

    # --- Route by sound type ---
    if sound_type == "silence":
        insight = _build_silence_insight(insight)

    elif sound_type == "noise":
        insight = _build_noise_insight(insight)

    elif sound_type == "laugh":
        insight = _build_laugh_insight(insight, is_adult, word_analysis, word_age_analysis)

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
            trained_cry, word_analysis, word_age_analysis,
        )

    elif sound_type == "speech":
        insight = _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
        )

    else:  # mixed
        # For mixed: check which components are present
        insight = _build_mixed_insight(
            insight, sound_classification, sound_features,
            word_analysis, word_age_analysis, is_adult, age_days,
        )

    # Save insight
    _save_insight(session_id, insight)

    logger.info(f"Insight generated: session={session_id} type={insight.get('display_type', 'unknown')}")
    return {"status": "insight_generated", "session_id": session_id, "insight": insight}


def _should_run_transcription(sound_type: str, routing: Dict, age_days: Optional[int]) -> bool:
    """Enable transcription only outside strict 0-3 month cry-only runtime."""
    if isinstance(age_days, int) and age_days <= CRY_ONLY_MAX_AGE_DAYS:
        return False
    return bool(routing.get("run_transcription", False) or sound_type in ("speech", "mixed"))


# ---------------------------------------------------------------------------
# Insight builders per sound type
# ---------------------------------------------------------------------------

def _build_silence_insight(insight: Dict) -> Dict:
    insight["display_type"] = "silence"
    insight["headline"] = "No sound detected"
    insight["headline_icon"] = "🔇"
    insight["description"] = "No baby sounds were detected in this recording. Try recording when your baby is making sounds."
    return insight


def _build_noise_insight(insight: Dict) -> Dict:
    insight["display_type"] = "noise"
    insight["headline"] = "Unrecognized sound"
    insight["headline_icon"] = "🔊"
    insight["description"] = "Background noise or unrecognized sounds were detected. Try recording in a quieter environment, closer to your baby."
    return insight


def _build_laugh_insight(
    insight: Dict,
    is_adult: bool,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
) -> Dict:
    insight["display_type"] = "laugh"

    if is_adult:
        insight["headline"] = "Laughing detected — Adult voice"
        insight["headline_icon"] = "😄"
        insight["description"] = "Laughter was detected but it appears to be from an adult speaker."
        insight["adult_detected"] = True
    else:
        insight["headline"] = "Your baby is laughing!"
        insight["headline_icon"] = "😄"
        insight["description"] = "Happy, joyful laughter detected. Your baby sounds content and delighted!"

    # Add words if found (always show)
    _attach_word_info(insight, word_analysis, word_age_analysis)

    return insight


def _build_cry_insight(
    insight: Dict,
    sound_features: Dict,
    age_days: Optional[int],
    is_adult: bool,
    trained_cry: Optional[Dict],
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
) -> Dict:
    insight["display_type"] = "cry"

    # Adult check
    if is_adult:
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
    debug_trace = cry_result.get("debug_trace", {})
    if debug_trace:
        logger.info(
            "Cry debug: primary=%s conf=%.3f rules=%s triggers=%s snapshot=%s",
            cry_result.get("primary_emotion"),
            float(cry_result.get("confidence", 0.0)),
            debug_trace.get("applied_conflict_rules", []),
            debug_trace.get("top_feature_triggers", {}),
            debug_trace.get("feature_snapshot", {}),
        )
        top_emotions = cry_result.get("top_emotions", [])
        second_key = top_emotions[1].get("key") if len(top_emotions) > 1 else None
        margin = float(debug_trace.get("margin", 0.0))
        dunstan_candidates = [
            f"{c.get('sound')}:{c.get('score')}"
            for c in cry_result.get("dunstan_candidates", [])[:3]
        ]
        logger.info(
            "Cry decision: primary=%s second=%s margin=%.3f dunstan_candidates=%s",
            cry_result.get("primary_emotion"),
            second_key,
            margin,
            dunstan_candidates,
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
    if cry_result.get("hungry_discomfort_overlap"):
        insight["insight_sections"]["note"] = (
            "Hungry and discomfort signals overlap. Feeding cues appear stronger in this recording."
        )
    if cry_result.get("decision_close_call"):
        base_note = insight["insight_sections"].get("note", "")
        close_note = "Signals are mixed and close. Please use this as a guidance signal with your direct observation."
        insight["insight_sections"]["note"] = f"{base_note} {close_note}".strip()

    # Dunstan sound reference (0-3m runtime scope)
    if cry_result.get("dunstan_sound"):
        insight["dunstan_sound"] = cry_result["dunstan_sound"]
    if cry_result.get("dunstan_ambiguous"):
        insight["dunstan_ambiguous"] = True

    # Age cry match
    age_cry_match = cry_result.get("age_cry_match", {})
    if age_cry_match.get("mismatch"):
        insight["age_mismatch"] = {
            "type": "cry_frequency",
            "message": (
                f"Cry pattern suggests {age_cry_match.get('probable_age_bracket', 'unknown')} "
                f"but child is registered as {age_cry_match.get('registered_age_bracket', 'unknown')}"
            ),
            "details": age_cry_match,
        }

    # Also detected emotions (alternatives)
    top_emotions = cry_result.get("top_emotions", [])
    alt_emotions = []
    if len(top_emotions) > 1:
        # Always show second-best as "also possible".
        alt_emotions.append(top_emotions[1])
    for e in top_emotions[2:3]:
        if e.get("score", 0) > 0.15:
            alt_emotions.append(e)
    if alt_emotions:
        insight["also_possible"] = alt_emotions

    # Words found during cry (baby might be crying + talking)
    _attach_word_info(insight, word_analysis, word_age_analysis)

    return insight


def _build_speech_insight(
    insight: Dict,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    is_adult: bool,
) -> Dict:
    insight["display_type"] = "speech"

    if not word_analysis or not word_analysis.get("has_words"):
        # Speech-like sounds but no clear words
        if is_adult:
            insight["headline"] = "Adult speech detected"
            insight["headline_icon"] = "🔊"
            insight["description"] = "Speech sounds were detected from an adult speaker but no clear words could be transcribed."
            insight["adult_detected"] = True
        else:
            insight["headline"] = "Baby vocalizing"
            insight["headline_icon"] = "🗣️"
            insight["description"] = "Your baby is making speech-like sounds. Babbling and vocal play are normal early vocal behaviors."
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
            insight["headline"] = "Your baby is forming sentences!"
            insight["headline_icon"] = "🗣️"
        elif words["word_count"] > 1:
            insight["headline"] = f"Your baby said {words['word_count']} words!"
            insight["headline_icon"] = "🗣️"
        else:
            insight["headline"] = "Word detected!"
            insight["headline_icon"] = "🗣️"

        insight["description"] = age_info.get("display_summary", f"{words['word_count']} word(s) detected")

    # Always attach word details
    _attach_word_info(insight, word_analysis, word_age_analysis)

    return insight


def _build_mixed_insight(
    insight: Dict,
    sound_classification: Dict,
    sound_features: Dict,
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    is_adult: bool,
    age_days: Optional[int],
) -> Dict:
    """Handle mixed sound types — prioritize what to show."""
    insight["display_type"] = "mixed"

    # Priority: words > cry > laugh > noise
    if word_analysis and word_analysis.get("has_words"):
        return _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
        )

    # Check for cry component
    scores = sound_classification.get("scores", {})
    if scores.get("cry", 0) > 0.3:
        return _build_cry_insight(
            insight, sound_features, age_days, is_adult,
            None, word_analysis, word_age_analysis,
        )

    if scores.get("laugh", 0) > 0.3:
        return _build_laugh_insight(
            insight, is_adult, word_analysis, word_age_analysis,
        )

    # Fallback
    insight["headline"] = "Mixed sounds detected"
    insight["headline_icon"] = "🔊"
    insight["description"] = "Multiple sound types were detected. The recording contains a mix of sounds that couldn't be clearly classified."
    _attach_word_info(insight, word_analysis, word_age_analysis)
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
