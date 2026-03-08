"""
Qleam — Cry Analyzer
Display text provider for cry emotion insights.

Phase 4: All scoring is done by the ML classifier (emotion_classifier.py).
This module provides:
  - Emotion display dictionaries (label, icon, what_hearing, what_means, what_try)
  - Dunstan Baby Language lookup for 0-3m display text
  - Age bracket utility

Dunstan Baby Language (0-3 months, applicable up to 6 months):
- Neh  = Hungry (sucking reflex, tongue on palate)
- Owh  = Tired  (yawning reflex, oval mouth)
- Heh  = Discomfort (skin/physical discomfort reflex)
- Eairh = Gas/Colic (lower abdomen tensing)
- Eh   = Burp (trapped air in chest rising)
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emotion display text (0-3m scope — expand when ML model supports more ages)
# ---------------------------------------------------------------------------

EMOTIONS = {
    "hungry": {
        "label": "Hungry",
        "icon": "\U0001f37c",
        "dunstan": "neh",
        "description": "A 'neh' sound created by the sucking reflex pushing the tongue to the roof of the mouth",
        "what_hearing": "Rhythmic, repetitive cry with a nasal 'neh' quality \u2014 rising and falling in a regular pattern",
        "what_means": "This cry pattern is commonly associated with the feeding reflex. Your baby may be signaling readiness to eat",
        "what_try": [
            "Offer a feed and watch for rooting cues (turning head, opening mouth)",
            "If recently fed, try a different feeding position",
            "Check if baby is latching properly or if bottle flow is adequate",
        ],
    },
    "tired": {
        "label": "Tired / Sleepy",
        "icon": "\U0001f634",
        "dunstan": "owh",
        "description": "An 'owh' sound with an oval-shaped mouth, similar to a yawn reflex",
        "what_hearing": "Soft, slow, breathy cry with a yawn-like quality \u2014 often near sleep, with long pauses between cries",
        "what_means": "This pattern resembles the yawning reflex. Your baby may be ready for sleep or showing early signs of tiredness",
        "what_try": [
            "Start a calming sleep routine \u2014 dim lights, reduce stimulation",
            "Try gentle rocking, swaddling, or white noise",
            "Watch for other sleep cues: eye rubbing, ear pulling, looking away",
        ],
    },
    "discomfort": {
        "label": "Uncomfortable",
        "icon": "\U0001f61f",
        "dunstan": "heh",
        "description": "A 'heh' sound triggered by skin or physical discomfort",
        "what_hearing": "Short, breathy cries with a 'heh' quality \u2014 intermittent, not sustained",
        "what_means": "This pattern often relates to physical discomfort \u2014 something about the body or environment feels wrong",
        "what_try": [
            "Check diaper, clothing tightness, temperature (too hot/cold)",
            "Try repositioning \u2014 baby might need a change of position",
            "Check for any tags, seams, or rough fabric touching skin",
        ],
    },
    "gas": {
        "label": "Gas / Colic",
        "icon": "\U0001f4a8",
        "dunstan": "eairh",
        "description": "An 'eairh' sound from lower abdomen tensing with trapped gas",
        "what_hearing": "Intense, straining cry with a grunting quality \u2014 baby may draw legs up",
        "what_means": "This pattern may indicate trapped gas or digestive discomfort. The straining quality suggests lower abdominal pressure",
        "what_try": [
            "Try gentle tummy massage in clockwise circles",
            "Bicycle legs gently to help release trapped gas",
            "Hold baby upright and gently pat or rub the back",
        ],
    },
    "burp": {
        "label": "Needs Burp",
        "icon": "\U0001fab7",
        "dunstan": "eh",
        "description": "An 'eh' sound from trapped air in the chest trying to rise",
        "what_hearing": "Short, repetitive 'eh' sounds \u2014 often after feeding, with a pushing quality",
        "what_means": "This pattern is associated with trapped air in the upper digestive tract. Your baby may need to release a burp",
        "what_try": [
            "Hold baby upright against your shoulder and gently pat the back",
            "Try sitting baby upright with chin support and gentle back rubs",
            "If breastfeeding, try burping between switching sides",
        ],
    },
    "pain": {
        "label": "Pain",
        "icon": "\U0001fa79",
        "description": "High-pitched, sudden onset cry with intense sustained periods",
        "what_hearing": "Sudden, high-pitched, intense cry \u2014 often with long, sustained wails and brief pauses for breath",
        "what_means": "This cry pattern has characteristics often associated with pain or acute discomfort. The sudden onset and intensity suggest something beyond routine needs",
        "what_try": [
            "Check for obvious pain sources: hair tourniquet, pinching, rash",
            "Gently examine fingers, toes, and body for anything unusual",
            "If crying persists or seems unusual, consult your pediatrician",
        ],
    },
    "content": {
        "label": "Content / Settling",
        "icon": "\U0001f60a",
        "description": "Low-intensity vocalizations without distress signals",
        "what_hearing": "Soft, low-level fussing or cooing \u2014 no urgent quality, may include babbling",
        "what_means": "Your baby doesn't seem to be in distress. These sounds may be self-soothing or exploratory vocalizations",
        "what_try": [
            "Continue what you're doing \u2014 baby seems settled",
            "Respond with gentle voice to encourage communication",
            "Observe for any changes that might indicate a shift in mood",
        ],
    },
}

# ---------------------------------------------------------------------------
# Age bracket utility
# ---------------------------------------------------------------------------

AGE_BRACKET = "0_3m"


def get_age_bracket(age_days: Optional[int]) -> str:
    """Convert age in days to age bracket string."""
    return AGE_BRACKET


# ---------------------------------------------------------------------------
# Dunstan sound lookup (display text only — NOT used for scoring)
# ---------------------------------------------------------------------------

DUNSTAN_MAP = {
    "hungry": "neh",
    "tired": "owh",
    "discomfort": "heh",
    "gas": "eairh",
    "burp": "eh",
}


def get_dunstan_sound(emotion_key: str, age_days: Optional[int] = None) -> Optional[str]:
    """Get the Dunstan sound name for a given emotion. Only relevant for 0-6m."""
    if age_days is not None and age_days > 180:
        return None
    return DUNSTAN_MAP.get(emotion_key)


# ---------------------------------------------------------------------------
# analyze_cry — thin wrapper: classifier output -> display text
# ---------------------------------------------------------------------------

def analyze_cry(
    features: Dict,
    age_days: Optional[int] = None,
    classifier_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Build cry analysis result from ML classifier output + display text.

    The ML classifier (emotion_classifier.py) does all scoring. This function
    maps the classifier output to user-facing display text.

    Args:
        features: Acoustic features (passed through from pipeline)
        age_days: Child's age in days
        classifier_result: Output from emotion_classifier.predict_emotion()

    Returns:
        Full cry analysis result with display text for insight_generator.
    """
    if classifier_result and classifier_result.get("using_model"):
        primary_key = classifier_result.get("primary_emotion", "discomfort")
        confidence = float(classifier_result.get("confidence", 0.5))
        emotion_scores = classifier_result.get("emotion_probabilities", {})
        top_emotions_raw = classifier_result.get("top_emotions", [])
    else:
        primary_key = "discomfort"
        confidence = 0.35
        emotion_scores = {e: 1.0 / len(EMOTIONS) for e in EMOTIONS}
        top_emotions_raw = []

    if primary_key not in EMOTIONS:
        primary_key = "discomfort"

    emotion_info = EMOTIONS.get(primary_key, {})

    # Build top_emotions for display
    if top_emotions_raw:
        top_emotions = []
        for e in top_emotions_raw[:3]:
            emo_key = e.get("key", "")
            emo = EMOTIONS.get(emo_key, {})
            top_emotions.append({
                "key": emo_key,
                "label": emo.get("label", emo_key),
                "icon": emo.get("icon", ""),
                "score": e.get("score", 0),
            })
    else:
        available = {k: v for k, v in emotion_scores.items() if k in EMOTIONS}
        ranked = sorted(available.items(), key=lambda x: x[1], reverse=True)
        top_emotions = []
        for key, score in ranked[:3]:
            if len(top_emotions) >= 2 and score <= 0.1:
                continue
            emo = EMOTIONS.get(key, {})
            top_emotions.append({
                "key": key,
                "label": emo.get("label", key),
                "icon": emo.get("icon", ""),
                "score": round(float(score), 3),
            })

    dunstan_sound = get_dunstan_sound(primary_key, age_days)
    secondary_emotion = top_emotions[1] if len(top_emotions) > 1 else None

    return {
        "primary_emotion": primary_key,
        "emotion_label": emotion_info.get("label", primary_key),
        "emotion_icon": emotion_info.get("icon", "\U0001f622"),
        "confidence": round(confidence, 3),
        "emotion_scores": {k: round(float(v), 3) for k, v in emotion_scores.items()},
        "top_emotions": top_emotions,
        "secondary_emotion": secondary_emotion,
        "age_bracket": AGE_BRACKET,
        "what_hearing": emotion_info.get("what_hearing", "Cry sounds detected"),
        "what_means": emotion_info.get("what_means", "Your baby is expressing a need"),
        "what_try": emotion_info.get("what_try", ["Observe and respond to your baby's cues"]),
        "dunstan_sound": dunstan_sound,
        "debug_trace": {
            "model_version": classifier_result.get("model_version") if classifier_result else "none",
        },
    }
