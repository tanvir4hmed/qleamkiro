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
    BEHAVIORAL_FLAG_UNKNOWN,
    CHILD_PROFILE_TABLE,
    CONCEPT_GRAPH_TABLE,
    DISCLAIMER,
    ENVIRONMENT_TO_LOCATION,
    ENVIRONMENT_TO_NOISE,
    FEEDING_STATUS_EARLY,
    FEEDING_STATUS_LATE,
    FEEDING_STATUS_MUCH_EARLY,
    FEEDING_STATUS_MUCH_LATE,
    FEEDING_STATUS_NORMAL,
    FEEDING_STATUS_UNKNOWN,
    HEALTH_STATE_ENCODING,
    MODEL_REGISTRY_TABLE,
    S3_BUCKET_NAME,
    SESSION_TABLE,
    SLEEP_STATUS_UNKNOWN,
    TRAINING_CANDIDATE_TABLE,
    TRIGGER_UNKNOWN,
)
from cry_analyzer import analyze_cry, get_age_bracket
from speech_transcriber import transcribe_audio, analyze_words_for_display
from word_analyzer import analyze_words_by_age
from private_language_model import match_private_language
from cry_training_model import predict_cry_emotion

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
concept_graph_table = dynamodb.Table(CONCEPT_GRAPH_TABLE)
model_registry_table = dynamodb.Table(MODEL_REGISTRY_TABLE)
training_candidate_table = dynamodb.Table(TRAINING_CANDIDATE_TABLE)

# ---------------------------------------------------------------------------
# Word → emotion hint mapping (for cry + word correlation)
# ---------------------------------------------------------------------------
_WORD_EMOTION_MAP = {
    # Hunger
    "neh":    ("hungry",            "Dunstan 'neh' sound — classic hunger signal"),
    "milk":   ("hungry",            "Said 'milk' — possible hunger signal"),
    "eat":    ("hungry",            "Said 'eat' — possible hunger signal"),
    "food":   ("hungry",            "Said 'food' — possible hunger signal"),
    "more":   ("hungry",            "Said 'more' — may be asking for more food"),
    "hungry": ("hungry",            "Said 'hungry' — strong hunger signal"),
    "bottle": ("hungry",            "Said 'bottle' — possible hunger signal"),
    "num":    ("hungry",            "Feeding sound detected"),
    # Tiredness
    "owh":    ("tired",             "Dunstan 'owh' sound — classic tiredness signal"),
    "sleepy": ("tired",             "Said 'sleepy' — strong tiredness signal"),
    "tired":  ("tired",             "Said 'tired' — strong tiredness signal"),
    "night":  ("tired",             "'Night night' detected — wanting sleep"),
    "nap":    ("tired",             "Said 'nap' — wanting sleep"),
    # Separation / caregiver
    "mama":   ("separation_anxiety","Calling for mama — wants reassurance"),
    "mommy":  ("separation_anxiety","Calling for mommy — wants reassurance"),
    "mummy":  ("separation_anxiety","Calling for mummy — wants reassurance"),
    "dada":   ("separation_anxiety","Calling for dada — wants reassurance"),
    "daddy":  ("separation_anxiety","Calling for daddy — wants reassurance"),
    # Pain
    "ow":    ("pain",               "Said 'ow' — possible pain signal"),
    "ouch":  ("pain",               "Said 'ouch' — possible pain signal"),
    "hurt":  ("pain",               "Said 'hurt' — possible pain signal"),
    # Frustration / wanting
    "no":    ("frustration",        "Said 'no' — expressing refusal or frustration"),
    "mine":  ("frustration",        "Said 'mine' — frustration or assertion"),
    "want":  ("frustration",        "Expressing 'want' — possible frustration"),
    "give":  ("frustration",        "Requesting something — possible frustration"),
    # Discomfort
    "stop":  ("discomfort",         "Said 'stop' — expressing discomfort"),
    "hot":   ("discomfort",         "Said 'hot' — temperature discomfort"),
    "cold":  ("discomfort",         "Said 'cold' — temperature discomfort"),
}

# ---------------------------------------------------------------------------
# Laugh descriptions by age bracket
# ---------------------------------------------------------------------------
_LAUGH_DESCRIPTIONS = {
    "0_6m": {
        "term": "baby",
        "headline": "Your baby is laughing!",
        "description": "Happy, joyful sounds detected! Early laughter is one of the most precious developmental moments.",
        "milestone_note": "First social laughs typically appear around 3–4 months — a wonderful sign of social and emotional development!",
        "milestone_age_range_days": (60, 150),
    },
    "6_12m": {
        "term": "baby",
        "headline": "Your baby is laughing!",
        "description": "Joyful belly laughs detected! Your baby is fully engaged, delighted, and socially thriving.",
        "milestone_note": None,
        "milestone_age_range_days": None,
    },
    "12_18m": {
        "term": "little one",
        "headline": "Your toddler is laughing!",
        "description": "Pure joy! Your toddler is expressing delight — play and laughter are central to their development right now.",
        "milestone_note": None,
        "milestone_age_range_days": None,
    },
    "18_24m": {
        "term": "toddler",
        "headline": "Your toddler is laughing!",
        "description": "Playful laughter detected — humor and social joy are blossoming. Laugh along to reinforce this wonderful bond!",
        "milestone_note": None,
        "milestone_age_range_days": None,
    },
    "24_36m": {
        "term": "child",
        "headline": "Your child is laughing!",
        "description": "Laughter and play are core to emotional and social development at this stage. Your child is thriving!",
        "milestone_note": None,
        "milestone_age_range_days": None,
    },
}


# ---------------------------------------------------------------------------
# Multimodal feature assembly for cry prediction
# ---------------------------------------------------------------------------

def _encode_feeding(minutes_ago) -> int:
    if minutes_ago is None:
        return FEEDING_STATUS_UNKNOWN
    try:
        m = int(minutes_ago)
    except (TypeError, ValueError):
        return FEEDING_STATUS_UNKNOWN
    if m < -90: return FEEDING_STATUS_MUCH_EARLY
    if m < -30: return FEEDING_STATUS_EARLY
    if m <= 30:  return FEEDING_STATUS_NORMAL
    if m <= 90:  return FEEDING_STATUS_LATE
    return FEEDING_STATUS_MUCH_LATE


def _encode_behavioral_flag(raw) -> int:
    if raw is None:
        return BEHAVIORAL_FLAG_UNKNOWN
    try:
        v = int(raw)
        if v in (0, 1):
            return v
    except (TypeError, ValueError):
        pass
    return BEHAVIORAL_FLAG_UNKNOWN


def _encode_sleep(sleep_status_raw) -> int:
    """Convert sleep_status (int or None) to sleep_status code."""
    if sleep_status_raw is None:
        return SLEEP_STATUS_UNKNOWN
    try:
        v = int(sleep_status_raw)
        if 0 <= v <= 3:
            return v
    except (TypeError, ValueError):
        pass
    return SLEEP_STATUS_UNKNOWN


def _encode_trigger(raw) -> int:
    """Convert trigger_code (int or None) to trigger code."""
    if raw is None:
        return TRIGGER_UNKNOWN
    try:
        v = int(raw)
        if 0 <= v <= 8:
            return v
    except (TypeError, ValueError):
        pass
    return TRIGGER_UNKNOWN


def _build_prediction_features(sound_features: Dict, session_context: Dict) -> Dict:
    """
    Merge acoustic sound_features with numerically-encoded context/behavioral
    fields into a single 22-feature dict for multimodal cry prediction.

    All context fields default to -1 (unknown) when absent — the model's
    Mahalanobis distance handles unknown values without bias.
    """
    env = session_context.get("environment", "unknown")
    context = {
        "feeding_status":     _encode_feeding(session_context.get("feeding_minutes_ago")),
        "sleep_status":       _encode_sleep(session_context.get("sleep_status")),
        "health_flag":        HEALTH_STATE_ENCODING.get(
                                  session_context.get("health_state", "unknown"), -1),
        "rooting_flag":       _encode_behavioral_flag(session_context.get("rooting_flag")),
        "hand_to_mouth_flag": _encode_behavioral_flag(session_context.get("hand_to_mouth_flag")),
        "eye_rub_flag":       _encode_behavioral_flag(session_context.get("eye_rub_flag")),
        "tantrum_body_flag":  _encode_behavioral_flag(session_context.get("tantrum_body_flag")),
        "location_code":      ENVIRONMENT_TO_LOCATION.get(env, -1),
        "noise_level":        ENVIRONMENT_TO_NOISE.get(env, -1),
        "trigger_code":       _encode_trigger(session_context.get("trigger_code")),
    }
    return {**sound_features, **context}


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
    age_days = event.get("age_days")
    s3_audio_path = event.get("s3_audio_path", "")
    fast_reject = event.get("fast_reject", False)
    session_context = event.get("session_context") or {}

    # Get child profile
    profile = _get_child_profile(child_id)

    # Build insight based on routing
    insight = {
        "sound_type": sound_type,
        "is_adult": is_adult,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "disclaimer": DISCLAIMER,
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
            transcript_result = transcribe_audio(s3_audio_path, os.environ.get("S3_BUCKET_NAME", S3_BUCKET_NAME))
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
        # Assemble multimodal features (acoustic + context) for trained model prediction
        prediction_features = (
            _build_prediction_features(sound_features, session_context)
            if session_context else sound_features
        )
        trained_cry = None
        age_bracket = get_age_bracket(age_days)
        try:
            trained_cry = predict_cry_emotion(prediction_features, age_bracket, model_registry_table)
        except Exception as e:
            logger.warning(f"Cry model prediction failed: {e}")

        insight = _build_cry_insight(
            insight, sound_features, age_days, is_adult,
            trained_cry, word_analysis, word_age_analysis, private_lang_match,
        )

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
    age_days: Optional[int],
    word_analysis: Optional[Dict],
    word_age_analysis: Optional[Dict],
    private_lang_match: Optional[Dict],
    cry_also_present: bool = False,
) -> Dict:
    insight["display_type"] = "laugh"

    if is_adult:
        insight["headline"] = "Laughing detected — Adult voice"
        insight["headline_icon"] = "😄"
        insight["description"] = "Laughter was detected but it appears to be from an adult speaker."
        insight["adult_detected"] = True
    else:
        age_bracket = get_age_bracket(age_days)
        desc = _LAUGH_DESCRIPTIONS.get(age_bracket, _LAUGH_DESCRIPTIONS["6_12m"])

        insight["headline"] = desc["headline"]
        insight["headline_icon"] = "😄"
        insight["description"] = desc["description"]

        # First-laugh milestone notice (3-5 months range)
        milestone_range = desc.get("milestone_age_range_days")
        if milestone_range and age_days is not None:
            if milestone_range[0] <= age_days <= milestone_range[1]:
                insight["laugh_milestone"] = {
                    "is_first_laugh_age": True,
                    "note": desc["milestone_note"],
                }

        # Mixed laugh + cry — overtired / overstimulation signal
        if cry_also_present:
            insight["mixed_emotional"] = True
            insight["mixed_note"] = (
                "Both laughter and crying were detected in this session. "
                "Joy turning to tears is a common sign of overstimulation or tiredness — "
                "a calm, quiet environment may help your " + desc["term"] + " settle."
            )

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
    alt_emotions = [e for e in cry_result.get("top_emotions", [])[1:3] if e.get("score", 0) > 0.15]
    if alt_emotions:
        insight["also_possible"] = alt_emotions

    # Words found during cry (baby might be crying + talking)
    _attach_word_info(insight, word_analysis, word_age_analysis)

    # Word → emotion hints: detected words that reinforce or contradict the primary emotion
    word_hints = _word_emotion_modifier(word_analysis, cry_result["primary_emotion"])
    if word_hints:
        insight["word_emotion_hints"] = word_hints

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

    # Priority: words > cry > laugh > noise
    if word_analysis and word_analysis.get("has_words"):
        return _build_speech_insight(
            insight, word_analysis, word_age_analysis, is_adult,
            age_days, private_lang_match, sound_features,
        )

    # Check for cry + laugh together — overtired / overstimulation pattern
    scores = sound_classification.get("scores", {})
    cry_score = scores.get("cry", 0)
    laugh_score = scores.get("laugh", 0)

    if cry_score > 0.3 and laugh_score > 0.3:
        return _build_laugh_insight(
            insight, is_adult, age_days, word_analysis, word_age_analysis,
            private_lang_match, cry_also_present=True,
        )

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


def _word_emotion_modifier(
    word_analysis: Optional[Dict],
    primary_emotion: str,
) -> List[Dict]:
    """
    Scan detected words for emotion signals during a cry session.

    Maps known words (milk, mama, ow, no, etc.) to emotion hints that
    enrich the insight display. Does not modify predictions — display only.

    Returns a list of hint dicts, deduplicated by emotion key.
    """
    if not word_analysis or not word_analysis.get("has_words"):
        return []

    display_words = word_analysis.get("display_words", [])
    hints: List[Dict] = []
    seen_emotions: set = set()

    for word_obj in display_words:
        word = word_obj.get("word", "").lower().strip(".,!?'\"")
        if word in _WORD_EMOTION_MAP:
            emotion_key, hint_text = _WORD_EMOTION_MAP[word]
            if emotion_key not in seen_emotions:
                seen_emotions.add(emotion_key)
                hints.append({
                    "word": word,
                    "emotion": emotion_key,
                    "hint": hint_text,
                    "confirms_primary": emotion_key == primary_emotion,
                })

    return hints


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
