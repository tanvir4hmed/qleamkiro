"""
Qleam — Cry Analyzer
Display text provider for cry emotion insights.

Phase 7: Age-variant display text for all developmental stages.
This module provides:
  - Emotion display dictionaries with age-specific variants
  - Dunstan Baby Language lookup for 0-3m display text
  - Age-appropriate language selection

Dunstan Baby Language (0-3 months only):
- Neh  = Hungry (sucking reflex, tongue on palate)
- Owh  = Tired  (yawning reflex, oval mouth)
- Heh  = Discomfort (skin/physical discomfort reflex)
- Eairh = Gas/Colic (lower abdomen tensing)
- Eh   = Burp (trapped air in chest rising)
"""
import logging
from typing import Any, Dict, Optional

from cry_rules import analyze_cry_rules

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Phase 7: Emotion display text with age variants
# ---------------------------------------------------------------------------

EMOTIONS = {
    "hungry": {
        "label": "Hungry",
        "icon": "\U0001f37c",
        "dunstan": "neh",
        "variants": {
            "0_90": {
                "description": "A 'neh' sound created by the sucking reflex pushing the tongue to the roof of the mouth",
                "what_hearing": "Rhythmic, repetitive cry with a nasal 'neh' quality — rising and falling in a regular pattern",
                "what_means": "This cry pattern is commonly associated with the feeding reflex. Your baby may be signaling readiness to eat",
                "what_try": [
                    "Offer a feed and watch for rooting cues (turning head, opening mouth)",
                    "If recently fed, try a different feeding position",
                    "Check if baby is latching properly or if bottle flow is adequate",
                ],
            },
            "91_180": {
                "description": "Persistent fussing that builds in intensity, often with reaching or mouthing behaviors",
                "what_hearing": "Escalating cry that becomes more insistent, may include fussing and squirming",
                "what_means": "Your baby is communicating hunger. At this age, they're developing more varied ways to express this need",
                "what_try": [
                    "Offer a feed — hunger cues are becoming more sophisticated",
                    "Watch for early hunger signs: increased alertness, hand-to-mouth movements",
                    "Consider if growth spurts might be increasing appetite",
                ],
            },
            "181_365": {
                "description": "Fussing or crying that may be accompanied by reaching toward food or caregiver",
                "what_hearing": "Cry that may alternate with vocalizations, pointing, or reaching behaviors",
                "what_means": "Your baby is expressing hunger and may be starting to communicate it in multiple ways beyond crying",
                "what_try": [
                    "Offer food or milk — your baby may be ready for solids if age-appropriate",
                    "Watch for non-cry hunger cues: reaching, pointing, vocalizing",
                    "Establish regular meal times to help anticipate hunger",
                ],
            },
            "366_730": {
                "description": "Fussing or words expressing hunger, may say 'eat' or 'hungry'",
                "what_hearing": "May use words, gestures, or crying to express hunger",
                "what_means": "Your toddler is communicating hunger through multiple channels — words, gestures, and sometimes crying",
                "what_try": [
                    "Respond to verbal cues when possible to encourage language use",
                    "Offer healthy snacks or meals at regular intervals",
                    "Teach hunger-related words to expand communication options",
                ],
            },
        },
    },
    "tired": {
        "label": "Tired / Sleepy",
        "icon": "\U0001f634",
        "dunstan": "owh",
        "variants": {
            "0_90": {
                "description": "An 'owh' sound with an oval-shaped mouth, similar to a yawn reflex",
                "what_hearing": "Soft, slow, breathy cry with a yawn-like quality — often near sleep, with long pauses between cries",
                "what_means": "This pattern resembles the yawning reflex. Your baby may be ready for sleep or showing early signs of tiredness",
                "what_try": [
                    "Start a calming sleep routine — dim lights, reduce stimulation",
                    "Try gentle rocking, swaddling, or white noise",
                    "Watch for other sleep cues: eye rubbing, ear pulling, looking away",
                ],
            },
            "91_180": {
                "description": "Whiny, escalating cry with increased fussiness and decreased tolerance",
                "what_hearing": "Cry that becomes more irritable and less consolable as tiredness increases",
                "what_means": "Your baby is overtired and needs help settling down for sleep",
                "what_try": [
                    "Begin sleep routine before overtiredness sets in",
                    "Create a calm, dark environment",
                    "Use consistent sleep associations (pacifier, lovey, white noise)",
                ],
            },
            "181_365": {
                "description": "Fussy crying with resistance to activities, rubbing eyes, decreased coordination",
                "what_hearing": "Irritable crying that may include tantrums or resistance to normal activities",
                "what_means": "Your baby is tired and may be fighting sleep. This is common as they become more aware of their surroundings",
                "what_try": [
                    "Maintain consistent nap and bedtime routines",
                    "Watch for sleep windows and act quickly",
                    "Reduce stimulation 30 minutes before sleep time",
                ],
            },
            "366_730": {
                "description": "Whining, crying, or saying 'tired' or 'sleepy', with decreased self-regulation",
                "what_hearing": "May express tiredness through words, whining, or emotional outbursts",
                "what_means": "Your toddler is tired and may lack the self-regulation skills to settle independently",
                "what_try": [
                    "Maintain consistent sleep schedules",
                    "Offer quiet time even if they resist naps",
                    "Teach tiredness vocabulary to help them communicate needs",
                ],
            },
        },
    },
    "discomfort": {
        "label": "Uncomfortable",
        "icon": "\U0001f61f",
        "dunstan": "heh",
        "variants": {
            "0_90": {
                "description": "A 'heh' sound triggered by skin or physical discomfort",
                "what_hearing": "Short, breathy cries with a 'heh' quality — intermittent, not sustained",
                "what_means": "This pattern often relates to physical discomfort — something about the body or environment feels wrong",
                "what_try": [
                    "Check diaper, clothing tightness, temperature (too hot/cold)",
                    "Try repositioning — baby might need a change of position",
                    "Check for any tags, seams, or rough fabric touching skin",
                ],
            },
            "91_180": {
                "description": "Fussing or crying with squirming, arching, or attempts to move away from discomfort",
                "what_hearing": "Intermittent crying with physical movements suggesting discomfort",
                "what_means": "Your baby is uncomfortable and trying to communicate or move away from the source",
                "what_try": [
                    "Check for physical causes: diaper, clothing, temperature",
                    "Look for teething signs: drooling, gum swelling, chewing",
                    "Try different positions or environments",
                ],
            },
            "181_365": {
                "description": "Crying with pointing, pulling at clothing, or showing the source of discomfort",
                "what_hearing": "Cry accompanied by gestures or attempts to show what's wrong",
                "what_means": "Your baby is uncomfortable and may be trying to show you the problem",
                "what_try": [
                    "Follow their cues — they may point to or touch the problem area",
                    "Check for common issues: diaper rash, tight clothing, teething",
                    "Respond to their communication attempts to build trust",
                ],
            },
            "366_730": {
                "description": "May use words like 'ow', 'hurt', or point to discomfort source",
                "what_hearing": "Crying with verbal or gestural communication about the problem",
                "what_means": "Your toddler is uncomfortable and trying to tell you what's wrong",
                "what_try": [
                    "Listen to their words and validate their feelings",
                    "Help them identify and name the discomfort",
                    "Address the physical cause and teach coping strategies",
                ],
            },
        },
    },
    "gas": {
        "label": "Gas / Colic",
        "icon": "\U0001f4a8",
        "dunstan": "eairh",
        "variants": {
            "0_90": {
                "description": "An 'eairh' sound from lower abdomen tensing with trapped gas",
                "what_hearing": "Intense, straining cry with a grunting quality — baby may draw legs up",
                "what_means": "This pattern may indicate trapped gas or digestive discomfort. The straining quality suggests lower abdominal pressure",
                "what_try": [
                    "Try gentle tummy massage in clockwise circles",
                    "Bicycle legs gently to help release trapped gas",
                    "Hold baby upright and gently pat or rub the back",
                ],
            },
            "91_180": {
                "description": "Crying with leg drawing, arching, or visible abdominal discomfort",
                "what_hearing": "Intense crying with physical signs of digestive discomfort",
                "what_means": "Your baby may have gas or digestive discomfort, common as their system matures",
                "what_try": [
                    "Continue tummy massage and bicycle legs",
                    "Try different feeding positions to reduce air intake",
                    "Consider dietary factors if breastfeeding or formula sensitivity",
                ],
            },
            "181_365": {
                "description": "Fussing or crying with holding stomach, refusing food, or showing digestive distress",
                "what_hearing": "Crying that may be related to meals or specific foods",
                "what_means": "Your baby may have gas or digestive discomfort, possibly related to new foods",
                "what_try": [
                    "Track foods and symptoms to identify triggers",
                    "Offer smaller, more frequent meals",
                    "Ensure adequate fiber and hydration as solids increase",
                ],
            },
            "366_730": {
                "description": "May say 'tummy hurt' or show signs of digestive discomfort",
                "what_hearing": "Crying or verbal complaints about stomach or digestive issues",
                "what_means": "Your toddler has digestive discomfort and may be able to describe it",
                "what_try": [
                    "Ask simple questions to understand the problem",
                    "Offer comfort and appropriate remedies",
                    "Monitor for patterns and consult pediatrician if persistent",
                ],
            },
        },
    },
    "burp": {
        "label": "Needs Burp",
        "icon": "\U0001fab7",
        "dunstan": "eh",
        "variants": {
            "0_90": {
                "description": "An 'eh' sound from trapped air in the chest trying to rise",
                "what_hearing": "Short, repetitive 'eh' sounds — often after feeding, with a pushing quality",
                "what_means": "This pattern is associated with trapped air in the upper digestive tract. Your baby may need to release a burp",
                "what_try": [
                    "Hold baby upright against your shoulder and gently pat the back",
                    "Try sitting baby upright with chin support and gentle back rubs",
                    "If breastfeeding, try burping between switching sides",
                ],
            },
            "91_180": {
                "description": "Fussing after feeding with squirming or arching",
                "what_hearing": "Post-feeding discomfort with restless movements",
                "what_means": "Your baby may need to burp or has swallowed air during feeding",
                "what_try": [
                    "Burp more frequently during and after feeds",
                    "Try different burping positions",
                    "Ensure proper latch or bottle nipple flow",
                ],
            },
            "181_365": {
                "description": "Post-meal fussiness, less common as burping becomes more independent",
                "what_hearing": "Occasional discomfort after eating",
                "what_means": "Your baby may still need help with burping, though this becomes less common",
                "what_try": [
                    "Offer gentle back pats if they seem uncomfortable after eating",
                    "Encourage upright time after meals",
                    "Most babies this age burp independently",
                ],
            },
            "366_730": {
                "description": "Rare at this age, may indicate overeating or eating too quickly",
                "what_hearing": "Uncommon, but may occur after large meals",
                "what_means": "If present, may indicate eating too quickly or overeating",
                "what_try": [
                    "Encourage slower eating",
                    "Offer smaller portions",
                    "Teach to recognize fullness cues",
                ],
            },
        },
    },
    "pain": {
        "label": "Pain",
        "icon": "\U0001fa79",
        "variants": {
            "0_90": {
                "description": "High-pitched, sudden onset cry with intense sustained periods",
                "what_hearing": "Sudden, high-pitched, intense cry — often with long, sustained wails and brief pauses for breath",
                "what_means": "This cry pattern has characteristics often associated with pain or acute discomfort. The sudden onset and intensity suggest something beyond routine needs",
                "what_try": [
                    "Check for obvious pain sources: hair tourniquet, pinching, rash",
                    "Gently examine fingers, toes, and body for anything unusual",
                    "If crying persists or seems unusual, consult your pediatrician",
                ],
            },
            "91_180": {
                "description": "Intense, inconsolable crying with sudden onset",
                "what_hearing": "High-pitched, urgent crying that doesn't respond to usual soothing",
                "what_means": "Your baby may be in pain. The intensity and inconsolability are key indicators",
                "what_try": [
                    "Check for injury, illness symptoms, or unusual physical signs",
                    "Try gentle comfort while assessing the situation",
                    "Seek medical attention if pain seems severe or unexplained",
                ],
            },
            "181_365": {
                "description": "Intense crying with guarding, favoring a body part, or showing pain location",
                "what_hearing": "Crying with physical signs of pain or injury",
                "what_means": "Your baby is in pain and may show you where it hurts",
                "what_try": [
                    "Observe for injury, swelling, or unusual movements",
                    "Offer comfort and assess severity",
                    "Contact pediatrician for guidance on pain management",
                ],
            },
            "366_730": {
                "description": "May say 'hurt', 'ow', or point to pain location while crying",
                "what_hearing": "Crying with verbal communication about pain",
                "what_means": "Your toddler is in pain and trying to tell you about it",
                "what_try": [
                    "Listen to their description and validate their pain",
                    "Assess the injury or illness",
                    "Provide appropriate comfort and medical care as needed",
                ],
            },
        },
    },
    "content": {
        "label": "Content / Settling",
        "icon": "\U0001f60a",
        "variants": {
            "0_90": {
                "description": "Low-intensity vocalizations without distress signals",
                "what_hearing": "Soft, low-level fussing or cooing — no urgent quality, may include babbling",
                "what_means": "Your baby doesn't seem to be in distress. These sounds may be self-soothing or exploratory vocalizations",
                "what_try": [
                    "Continue what you're doing — baby seems settled",
                    "Respond with gentle voice to encourage communication",
                    "Observe for any changes that might indicate a shift in mood",
                ],
            },
            "91_180": {
                "description": "Happy vocalizations, cooing, or quiet contentment",
                "what_hearing": "Pleasant sounds or quiet alertness without distress",
                "what_means": "Your baby is content and may be exploring their voice or environment",
                "what_try": [
                    "Engage in gentle play or conversation",
                    "Allow independent exploration time",
                    "Respond to vocalizations to encourage communication",
                ],
            },
            "181_365": {
                "description": "Babbling, playing, or quiet contentment with occasional vocalizations",
                "what_hearing": "Happy babbling, playing sounds, or peaceful quiet",
                "what_means": "Your baby is content and engaged in play or exploration",
                "what_try": [
                    "Support their play and exploration",
                    "Respond to babbling to encourage language development",
                    "Enjoy this peaceful time together",
                ],
            },
            "366_730": {
                "description": "Playing, talking, or quiet contentment",
                "what_hearing": "Happy play, conversation, or peaceful quiet",
                "what_means": "Your toddler is content and engaged",
                "what_try": [
                    "Support their independent play",
                    "Engage in conversation when they initiate",
                    "Enjoy their growing independence",
                ],
            },
        },
    },
}
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
    debug_trace: Dict[str, Any] = {}
    if classifier_result and classifier_result.get("using_model"):
        primary_key = classifier_result.get("primary_emotion", "discomfort")
        confidence = float(classifier_result.get("confidence", 0.5))
        emotion_scores = classifier_result.get("emotion_probabilities", {})
        top_emotions_raw = classifier_result.get("top_emotions", [])
        debug_trace = {
            "model_version": classifier_result.get("model_version", "unknown"),
            "ml_classifier": classifier_result,
        }
    else:
        # Basic-mode / ML-failure path: use handmade rule scoring (not constant discomfort).
        rule_result = analyze_cry_rules(features or {}, age_days=age_days or 45)
        primary_key = rule_result.get("primary_emotion", "discomfort")
        confidence = float(rule_result.get("confidence", 0.35))
        emotion_scores = rule_result.get("emotion_probabilities", {})
        top_emotions_raw = rule_result.get("top_emotions", [])
        debug_trace = {
            "model_version": rule_result.get("model_version", "rule_based_basic"),
            "rule_debug": rule_result.get("debug_trace", {}),
        }

    if primary_key not in EMOTIONS:
        primary_key = "discomfort"

    emotion_info = EMOTIONS.get(primary_key, {})
    
    # Phase 7: Select age-appropriate variant
    age_variant = _get_age_variant(age_days)
    variant_info = emotion_info.get("variants", {}).get(age_variant, {})
    
    # Use variant if available, otherwise fall back to base emotion info
    what_hearing = variant_info.get("what_hearing", emotion_info.get("what_hearing", "Cry sounds detected"))
    what_means = variant_info.get("what_means", emotion_info.get("what_means", "Your baby is expressing a need"))
    what_try = variant_info.get("what_try", emotion_info.get("what_try", ["Observe and respond to your baby's cues"]))
    description = variant_info.get("description", emotion_info.get("description", ""))

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
    dunstan_description = description if dunstan_sound else ""
    secondary_emotion = top_emotions[1] if len(top_emotions) > 1 else None

    return {
        "primary_emotion": primary_key,
        "emotion_label": emotion_info.get("label", primary_key),
        "emotion_icon": emotion_info.get("icon", "\U0001f622"),
        "confidence": round(confidence, 3),
        "emotion_scores": {k: round(float(v), 3) for k, v in emotion_scores.items()},
        "top_emotions": top_emotions,
        "secondary_emotion": secondary_emotion,
        "age_bracket": age_variant,
        "what_hearing": what_hearing,
        "what_means": what_means,
        "what_try": what_try,
        "dunstan_sound": dunstan_sound,
        "dunstan_description": dunstan_description,
        "debug_trace": debug_trace,
    }


def _get_age_variant(age_days: Optional[int]) -> str:
    """
    Get age variant key for display text selection.
    
    Args:
        age_days: Baby's age in days
    
    Returns:
        Age variant key: "0_90", "91_180", "181_365", or "366_730"
    """
    if age_days is None or age_days <= 90:
        return "0_90"
    elif age_days <= 180:
        return "91_180"
    elif age_days <= 365:
        return "181_365"
    else:
        return "366_730"
        "what_means": emotion_info.get("what_means", "Your baby is expressing a need"),
        "what_try": emotion_info.get("what_try", ["Observe and respond to your baby's cues"]),
        "dunstan_sound": dunstan_sound,
        "dunstan_description": dunstan_description,
        "debug_trace": debug_trace,
    }
