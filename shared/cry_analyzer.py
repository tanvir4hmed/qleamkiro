"""
Qleam — Cry Analyzer
Age-specific cry emotion detection using Dunstan Baby Language research
and acoustic pattern analysis.

Dunstan Baby Language (0-3 months, applicable up to 6 months):
- Neh  = Hungry (sucking reflex, tongue on palate)
- Owh  = Tired  (yawning reflex, oval mouth)
- Heh  = Discomfort (skin/physical discomfort reflex)
- Eairh = Gas/Colic (lower abdomen tensing)
- Eh   = Burp (trapped air in chest rising)

Beyond 6 months, cry analysis shifts to acoustic pattern analysis:
- Pitch (high = pain/fear, medium = frustration, low = tired/bored)
- Duration (sustained = hunger, short bursts = frustration, sudden onset = pain)
- Intensity patterns (escalating = unmet need, steady = discomfort, fluctuating = attention)
- Rhythmicity (rhythmic = self-soothing attempt, arrhythmic = acute distress)

Research sources:
- Dunstan Baby Language (Priscilla Dunstan, 2006)
- Infant Cry Analysis (LaGasse et al., 2005)
- Acoustic Features of Infant Cries (Michelsson et al., 2002)
- Cry perception studies (Soltis, 2004)
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Emotion definitions by age bracket
# ---------------------------------------------------------------------------

# 0-6 months: Dunstan Baby Language reflexive sounds + basic emotions
EMOTIONS_0_6M = {
    "hungry": {
        "label": "Hungry",
        "icon": "🍼",
        "dunstan": "neh",
        "description": "A 'neh' sound created by the sucking reflex pushing the tongue to the roof of the mouth",
        "what_hearing": "Rhythmic, repetitive cry with a nasal 'neh' quality — rising and falling in a regular pattern",
        "what_means": "This cry pattern is commonly associated with the feeding reflex. Your baby may be signaling readiness to eat",
        "what_try": [
            "Offer a feed and watch for rooting cues (turning head, opening mouth)",
            "If recently fed, try a different feeding position",
            "Check if baby is latching properly or if bottle flow is adequate",
        ],
    },
    "tired": {
        "label": "Tired / Sleepy",
        "icon": "😴",
        "dunstan": "owh",
        "description": "An 'owh' sound with an oval-shaped mouth, similar to a yawn reflex",
        "what_hearing": "Breathy, drawn-out cry with a yawn-like quality — often with long pauses between cries",
        "what_means": "This pattern resembles the yawning reflex. Your baby may be ready for sleep or showing early signs of tiredness",
        "what_try": [
            "Start a calming sleep routine — dim lights, reduce stimulation",
            "Try gentle rocking, swaddling, or white noise",
            "Watch for other sleep cues: eye rubbing, ear pulling, looking away",
        ],
    },
    "discomfort": {
        "label": "Uncomfortable",
        "icon": "😟",
        "dunstan": "heh",
        "description": "A 'heh' sound triggered by skin or physical discomfort",
        "what_hearing": "Short, breathy cries with a 'heh' quality — intermittent, not sustained",
        "what_means": "This pattern often relates to physical discomfort — something about the body or environment feels wrong",
        "what_try": [
            "Check diaper, clothing tightness, temperature (too hot/cold)",
            "Try repositioning — baby might need a change of position",
            "Check for any tags, seams, or rough fabric touching skin",
        ],
    },
    "gas": {
        "label": "Gas / Colic",
        "icon": "💨",
        "dunstan": "eairh",
        "description": "An 'eairh' sound from lower abdomen tensing with trapped gas",
        "what_hearing": "Intense, straining cry with a grunting quality — baby may draw legs up",
        "what_means": "This pattern may indicate trapped gas or digestive discomfort. The straining quality suggests lower abdominal pressure",
        "what_try": [
            "Try gentle tummy massage in clockwise circles",
            "Bicycle legs gently to help release trapped gas",
            "Hold baby upright and gently pat or rub the back",
        ],
    },
    "burp": {
        "label": "Needs Burp",
        "icon": "🫧",
        "dunstan": "eh",
        "description": "An 'eh' sound from trapped air in the chest trying to rise",
        "what_hearing": "Short, repetitive 'eh' sounds — often after feeding, with a pushing quality",
        "what_means": "This pattern is associated with trapped air in the upper digestive tract. Your baby may need to release a burp",
        "what_try": [
            "Hold baby upright against your shoulder and gently pat the back",
            "Try sitting baby upright with chin support and gentle back rubs",
            "If breastfeeding, try burping between switching sides",
        ],
    },
    "pain": {
        "label": "Pain",
        "icon": "🩹",
        "description": "High-pitched, sudden onset cry with intense sustained periods",
        "what_hearing": "Sudden, high-pitched, intense cry — often with long, sustained wails and brief pauses for breath",
        "what_means": "This cry pattern has characteristics often associated with pain or acute discomfort. The sudden onset and intensity suggest something beyond routine needs",
        "what_try": [
            "Check for obvious pain sources: hair tourniquet, pinching, rash",
            "Gently examine fingers, toes, and body for anything unusual",
            "If crying persists or seems unusual, consult your pediatrician",
        ],
    },
    "closeness": {
        "label": "Wants Closeness",
        "icon": "🤗",
        "description": "Lower intensity, whimpering cry that stops when held",
        "what_hearing": "Softer, whimpering cry — more of a fuss than a full cry, often with breaks",
        "what_means": "This pattern often indicates your baby wants to be held and comforted. It typically responds well to physical closeness",
        "what_try": [
            "Pick up and hold baby close — skin-to-skin if possible",
            "Gentle rocking or swaying while making soft sounds",
            "Try a baby carrier or wrap for hands-free closeness",
        ],
    },
}

# 6-12 months: Dunstan reflexes fade, more intentional communication
EMOTIONS_6_12M = {
    "hungry": EMOTIONS_0_6M["hungry"],
    "tired": EMOTIONS_0_6M["tired"],
    "discomfort": EMOTIONS_0_6M["discomfort"],
    "pain": EMOTIONS_0_6M["pain"],
    "closeness": EMOTIONS_0_6M["closeness"],
    "frustration": {
        "label": "Frustrated",
        "icon": "😣",
        "description": "Intense, building cry with increasing volume and tempo",
        "what_hearing": "Building, escalating cry — starts moderate and gets louder, often with shouting quality",
        "what_means": "Your baby may be frustrated — they want something but can't get it or communicate it clearly yet",
        "what_try": [
            "Look for what they might be reaching for or trying to do",
            "Offer help with the task they seem stuck on",
            "Acknowledge their frustration with a calm, understanding voice",
        ],
    },
    "separation_anxiety": {
        "label": "Separation Anxiety",
        "icon": "😢",
        "description": "Cry that starts when caregiver leaves or is out of sight",
        "what_hearing": "Sudden onset cry when you leave the room or put baby down — often with arms reaching out",
        "what_means": "This is a normal developmental stage. Your baby understands object permanence and misses your presence",
        "what_try": [
            "Practice brief separations and always come back with a smile",
            "Play peek-a-boo to reinforce that you return",
            "Leave a comforting item with your scent nearby",
        ],
    },
    "boredom": {
        "label": "Bored / Understimulated",
        "icon": "😐",
        "description": "Low-intensity fussing that changes with new stimulation",
        "what_hearing": "On-and-off fussing, low intensity — not urgent, more like complaining",
        "what_means": "Your baby might be ready for something new. This age craves exploration and new experiences",
        "what_try": [
            "Change the environment — move to a different room or go outside",
            "Offer a new toy or activity appropriate for their age",
            "Engage in interactive play: singing, clapping, peek-a-boo",
        ],
    },
}

# 12-18 months: More complex emotions emerge
EMOTIONS_12_18M = {
    **EMOTIONS_6_12M,
    "tantrum": {
        "label": "Tantrum / Overwhelmed",
        "icon": "😤",
        "description": "Intense, uncontrollable crying often with physical thrashing",
        "what_hearing": "Very loud, sustained crying — possibly with screaming, body arching, or throwing",
        "what_means": "Your toddler is overwhelmed by emotions they can't yet regulate. This is a normal part of development",
        "what_try": [
            "Stay calm and present — your calm helps them regulate",
            "Offer comfort without trying to 'fix' it immediately",
            "Move to a quiet, safe space if possible",
        ],
    },
    "fear": {
        "label": "Scared / Startled",
        "icon": "😰",
        "description": "Sudden, alarmed cry with wide eyes and clinging behavior",
        "what_hearing": "Sharp, alarmed cry — sudden onset, often high-pitched with a startled quality",
        "what_means": "Something scared or startled your baby. At this age, many new things can seem frightening",
        "what_try": [
            "Hold your baby close and speak in a calm, reassuring voice",
            "Acknowledge the fear: 'That was loud! You're safe with me'",
            "Remove the scary stimulus if possible, or approach it together slowly",
        ],
    },
}

# 18-24 months: Emotional complexity increases
EMOTIONS_18_24M = {
    **EMOTIONS_12_18M,
    "jealousy": {
        "label": "Jealous / Wanting Attention",
        "icon": "😒",
        "description": "Whining or crying when caregiver attends to something/someone else",
        "what_hearing": "Whining, clingy cry that escalates when attention goes elsewhere",
        "what_means": "Your toddler wants your full attention. This is normal at this age as they develop a stronger sense of self",
        "what_try": [
            "Acknowledge them: 'I see you! I'll be with you in a moment'",
            "Include them in what you're doing when possible",
            "Set aside dedicated one-on-one time regularly",
        ],
    },
}

# 24-36 months: Full emotional range with verbal elements
EMOTIONS_24_36M = {
    **EMOTIONS_18_24M,
    "embarrassment": {
        "label": "Embarrassed / Self-conscious",
        "icon": "🙈",
        "description": "Cry or whimper after a social situation, hiding face",
        "what_hearing": "Soft crying or whimpering — often hiding face, turning away, or seeking comfort",
        "what_means": "Your child is developing self-awareness and may feel embarrassed. This shows emotional growth",
        "what_try": [
            "Comfort without drawing more attention to the moment",
            "Normalize the experience: 'Everyone has moments like that'",
            "Avoid laughing at or dismissing their feelings",
        ],
    },
}

# Age bracket mapping
AGE_EMOTION_MAP = {
    "0_6m": EMOTIONS_0_6M,
    "6_12m": EMOTIONS_6_12M,
    "12_18m": EMOTIONS_12_18M,
    "18_24m": EMOTIONS_18_24M,
    "24_36m": EMOTIONS_24_36M,
}


def get_age_bracket(age_days: Optional[int]) -> str:
    """Convert age in days to age bracket string."""
    if age_days is None or age_days < 0:
        return "0_6m"
    months = age_days / 30.44
    if months < 6:
        return "0_6m"
    elif months < 12:
        return "6_12m"
    elif months < 18:
        return "12_18m"
    elif months < 24:
        return "18_24m"
    else:
        return "24_36m"


def get_emotions_for_age(age_days: Optional[int]) -> Dict[str, Dict]:
    """Get the emotion set appropriate for the child's age."""
    bracket = get_age_bracket(age_days)
    return AGE_EMOTION_MAP.get(bracket, EMOTIONS_0_6M)


# ---------------------------------------------------------------------------
# Acoustic cry pattern analysis
# ---------------------------------------------------------------------------

# Age-specific cry frequency characteristics (research-based)
CRY_FREQUENCY_BY_AGE = {
    "0_6m": {"f0_range": (350, 650), "typical_f0": 500, "duration_typical": (1.0, 5.0)},
    "6_12m": {"f0_range": (300, 600), "typical_f0": 450, "duration_typical": (0.5, 4.0)},
    "12_18m": {"f0_range": (280, 550), "typical_f0": 400, "duration_typical": (0.5, 3.5)},
    "18_24m": {"f0_range": (250, 500), "typical_f0": 370, "duration_typical": (0.3, 3.0)},
    "24_36m": {"f0_range": (220, 480), "typical_f0": 340, "duration_typical": (0.3, 2.5)},
}


def _score_dunstan_sounds(features: Dict) -> Dict[str, float]:
    """
    Score Dunstan Baby Language sounds from acoustic features.

    Uses spectral and temporal patterns to estimate which reflexive
    sound pattern best matches the cry.
    """
    f0 = features.get("f0_mean", 0)
    f0_std = features.get("f0_std", 0)
    f0_instability = features.get("f0_instability", 0)
    spectral_centroid = features.get("spectral_centroid", 0)
    spectral_flatness = features.get("spectral_flatness", 0)
    syllable_rate = features.get("syllable_rate", 0)
    zcr = features.get("zcr", 0)
    energy_var = features.get("energy_variability", 0)
    rms_mean = features.get("rms_mean", 0)

    scores = {}

    # Neh (hungry): Rhythmic, nasal, moderate pitch, repetitive
    # "neh" has tongue-to-palate nasal quality → peaked spectrum (low flatness),
    # regular syllable repetition, and stable pitch.
    neh_score = 0.0
    if 300 < f0 < 550:
        neh_score += 0.30
    if f0_instability < 0.15:
        neh_score += 0.25  # Relatively stable pitch (rhythmic)
    if 800 < spectral_centroid < 2500:
        neh_score += 0.25  # Nasal resonance range
    if energy_var > 0.2:
        neh_score += 0.20  # Rhythmic on/off
    if spectral_flatness < 0.35:
        neh_score += 0.10  # Nasal = peaked spectrum (not breathy/flat)
    if syllable_rate > 1.5:
        neh_score += 0.10  # Rhythmic "neh neh neh" repetition
    scores["hungry"] = min(1.0, neh_score)

    # Owh (tired): Breathy, drawn out, lower intensity
    owh_score = 0.0
    if 250 < f0 < 450:
        owh_score += 0.25  # Lower pitch for tired
    if f0_instability < 0.12:
        owh_score += 0.25  # Relatively stable
    if rms_mean < 0.08:
        owh_score += 0.25  # Lower intensity
    if zcr < 0.04:
        owh_score += 0.25  # Less harsh
    scores["tired"] = min(1.0, owh_score)

    # Heh (discomfort): Breathy exhale, short random bursts, airy quality.
    # "heh" is an exhale reflex — flat/noisy spectrum (high spectral_flatness),
    # distinctly breathy zcr, irregular energy, and unstable pitch.
    heh_score = 0.0
    if zcr > 0.05:
        heh_score += 0.25  # Distinctly breathy/airy (raised from 0.03)
    if energy_var > 0.35:
        heh_score += 0.25  # More intermittent than hungry (raised from 0.3)
    if rms_mean < 0.08:
        heh_score += 0.15  # Softer than average cry (tightened from 0.10)
    if f0_instability > 0.12:
        heh_score += 0.15  # Less stable than hungry (raised from 0.08)
    if spectral_flatness > 0.3:
        heh_score += 0.20  # Breathy exhale = flat/noisy spectrum (new)
    scores["discomfort"] = min(1.0, heh_score)

    # Eairh (gas): Intense, straining, grunting, lower
    eairh_score = 0.0
    if f0 > 400:
        eairh_score += 0.25  # Can be high pitched
    if rms_mean > 0.06:
        eairh_score += 0.25  # Intense
    if f0_instability > 0.15:
        eairh_score += 0.25  # Strained, wavering
    if spectral_centroid > 2000:
        eairh_score += 0.25  # Strained quality
    scores["gas"] = min(1.0, eairh_score)

    # Eh (burp): Short, repetitive, pushing quality
    eh_score = 0.0
    if 300 < f0 < 500:
        eh_score += 0.25
    if energy_var > 0.25:
        eh_score += 0.30  # Repetitive short bursts
    if f0_instability < 0.10:
        eh_score += 0.25  # Relatively stable per burst
    if zcr < 0.05:
        eh_score += 0.20
    scores["burp"] = min(1.0, eh_score)

    # Pain: High-pitched, sudden, intense, sustained
    pain_score = 0.0
    if f0 > 500:
        pain_score += 0.35  # Very high pitch
    if rms_mean > 0.10:
        pain_score += 0.25  # High intensity
    if f0_instability > 0.20:
        pain_score += 0.20  # Wavering/strained
    if energy_var < 0.20:
        pain_score += 0.20  # Sustained (not rhythmic)
    scores["pain"] = min(1.0, pain_score)

    # Closeness: Lower intensity, genuine whimpering
    close_score = 0.0
    if f0 < 400:
        close_score += 0.30  # Lower pitch
    if rms_mean < 0.04:
        close_score += 0.30  # Very low intensity (tightened from 0.05)
    if energy_var > 0.35:
        close_score += 0.20  # Intermittent fussing (raised from 0.3)
    if f0_instability < 0.10:
        close_score += 0.20
    scores["closeness"] = min(1.0, close_score)

    return scores


def _score_older_baby_emotions(features: Dict, age_bracket: str) -> Dict[str, float]:
    """
    Score emotions for older babies (6m+) using acoustic patterns.
    Extends Dunstan-based scores with frustration, separation anxiety, etc.

    Thresholds are set to be discriminating — each emotion must have a
    distinctive acoustic fingerprint to score high.  Generic moderate cries
    should not accidentally dominate over Dunstan-based base scores.
    """
    # Start with Dunstan-like base scores
    scores = _score_dunstan_sounds(features)

    f0 = features.get("f0_mean", 0)
    f0_instability = features.get("f0_instability", 0)
    energy_var = features.get("energy_variability", 0)
    rms_mean = features.get("rms_mean", 0)
    spectral_centroid = features.get("spectral_centroid", 0)
    spectral_flatness = features.get("spectral_flatness", 0)

    # Frustration: Building, escalating, LOUD, high-energy.
    # Key distinction: frustration is LOUD (rms>0.10) and high centroid.
    # A soft cry should not score here.
    frustration_score = 0.0
    if rms_mean > 0.10:
        frustration_score += 0.30  # Must be loud (raised from 0.08)
    if f0_instability > 0.15:
        frustration_score += 0.25  # Pitch escalates (raised from 0.12)
    if energy_var > 0.30:
        frustration_score += 0.25
    if spectral_centroid > 2000:
        frustration_score += 0.20  # Harsh quality (raised from 1800)
    scores["frustration"] = min(1.0, frustration_score)

    # Separation anxiety: Sudden onset, clingy, INTENSE, higher-pitched.
    # Key distinction: separation cry is louder and more urgent than tired/hungry.
    # Must have clear intensity + pitch instability (calling out).
    sep_score = 0.0
    if 400 < f0 < 600:
        sep_score += 0.25  # Higher pitch range (narrowed from 350-550)
    if rms_mean > 0.08:
        sep_score += 0.25  # Must be clearly audible (raised from 0.06)
    if f0_instability > 0.14:
        sep_score += 0.25  # Pitch jumps — calling out (raised from 0.10)
    if energy_var > 0.30:
        sep_score += 0.15  # Intermittent but less than discomfort (raised from 0.25)
    if spectral_flatness < 0.35:
        sep_score += 0.10  # Voiced/resonant, not breathy
    scores["separation_anxiety"] = min(1.0, sep_score)

    # Boredom: Low intensity, on-off, LOW pitch
    bore_score = 0.0
    if rms_mean < 0.04:
        bore_score += 0.35  # Very quiet (tightened from 0.05)
    if energy_var > 0.40:
        bore_score += 0.30  # Very intermittent (raised from 0.35)
    if f0 < 350:
        bore_score += 0.20
    if f0_instability < 0.08:
        bore_score += 0.15
    scores["boredom"] = min(1.0, bore_score)

    # Tantrum (12m+)
    if age_bracket in ("12_18m", "18_24m", "24_36m"):
        tantrum_score = 0.0
        if rms_mean > 0.12:
            tantrum_score += 0.35
        if f0 > 450:
            tantrum_score += 0.25
        if f0_instability > 0.18:
            tantrum_score += 0.20
        if energy_var < 0.15:
            tantrum_score += 0.20  # Sustained intense
        scores["tantrum"] = min(1.0, tantrum_score)

    # Fear (12m+)
    if age_bracket in ("12_18m", "18_24m", "24_36m"):
        fear_score = 0.0
        if f0 > 500:
            fear_score += 0.35  # Very high pitch
        if rms_mean > 0.08:
            fear_score += 0.25
        if f0_instability > 0.15:
            fear_score += 0.20
        if energy_var < 0.20:
            fear_score += 0.20
        scores["fear"] = min(1.0, fear_score)

    return scores


# ---------------------------------------------------------------------------
# Enhanced scoring layers (formant, voice quality, temporal)
# These use rich_features extracted in feature_extraction but previously
# discarded before reaching cry analysis.
# ---------------------------------------------------------------------------

def _score_formant_dunstan(features: Dict) -> Dict[str, float]:
    """
    Layer 1: Formant-based Dunstan sound matcher.

    Each Dunstan reflex sound corresponds to a specific mouth shape which
    produces a characteristic vowel-space position (F1 = jaw openness,
    F2 = tongue front/back).  Returns empty dict if formant data is missing
    so the layer's weight can be redistributed.
    """
    f1 = features.get("formant_f1", 0)
    f2 = features.get("formant_f2", 0)
    jitter = features.get("jitter_percent", 0)

    # If formant data missing, skip this layer entirely
    if f1 < 50 or f2 < 50:
        return {}

    scores = {}

    # Neh (hungry): tongue forward/up → high F2, nasal resonance
    # Vowel space: F1 600-1000, F2 1800-2800
    neh = 0.0
    if 600 <= f1 <= 1000:
        neh += 0.50
    elif 450 <= f1 <= 1100:
        neh += 0.25
    if 1800 <= f2 <= 2800:
        neh += 0.50
    elif 1500 <= f2 <= 3000:
        neh += 0.25
    scores["hungry"] = min(1.0, neh)

    # Owh (tired): round mouth → low F1, low F2 (back vowel)
    # Vowel space: F1 300-600, F2 700-1400
    owh = 0.0
    if 300 <= f1 <= 600:
        owh += 0.50
    elif 200 <= f1 <= 750:
        owh += 0.25
    if 700 <= f2 <= 1400:
        owh += 0.50
    elif 500 <= f2 <= 1600:
        owh += 0.25
    scores["tired"] = min(1.0, owh)

    # Heh (discomfort): open exhale → high F1, neutral F2
    # Vowel space: F1 600-1000, F2 1300-1900
    heh = 0.0
    if 600 <= f1 <= 1000:
        heh += 0.50
    elif 500 <= f1 <= 1100:
        heh += 0.25
    if 1300 <= f2 <= 1900:
        heh += 0.50
    elif 1100 <= f2 <= 2100:
        heh += 0.25
    scores["discomfort"] = min(1.0, heh)

    # Eairh (gas): tense abdominal → mid range, high jitter
    # Vowel space: F1 500-900, F2 1400-2200
    eairh = 0.0
    if 500 <= f1 <= 900:
        eairh += 0.35
    if 1400 <= f2 <= 2200:
        eairh += 0.35
    if jitter > 3.0:
        eairh += 0.30  # Strain marker
    scores["gas"] = min(1.0, eairh)

    # Eh (burp): short push → mid F1, neutral F2
    # Vowel space: F1 400-700, F2 1400-1900
    eh = 0.0
    if 400 <= f1 <= 700:
        eh += 0.50
    if 1400 <= f2 <= 1900:
        eh += 0.50
    scores["burp"] = min(1.0, eh)

    # Pain: high tension → high F1, spread F2
    pain = 0.0
    if f1 > 800:
        pain += 0.40
    if f2 > 2200:
        pain += 0.30
    if jitter > 4.0:
        pain += 0.30
    scores["pain"] = min(1.0, pain)

    # Closeness: relaxed whimper → low-mid F1, mid F2
    close = 0.0
    if 300 <= f1 <= 600:
        close += 0.50
    if 1200 <= f2 <= 1800:
        close += 0.50
    scores["closeness"] = min(1.0, close)

    return scores


def _score_voice_quality(features: Dict) -> Dict[str, float]:
    """
    Layer 2: Voice quality discriminator using HNR, jitter, shimmer.

    Tonal/melodic cries (high HNR, low jitter) → hungry, tired, closeness.
    Strained/rough cries (low HNR, high jitter) → gas, pain, tantrum.
    Returns empty dict if all voice quality features are zero/missing.
    """
    hnr = features.get("hnr_db", 0)
    jitter = features.get("jitter_percent", 0)
    shimmer = features.get("shimmer_db", 0)

    # Skip if no voice quality data available
    if hnr == 0 and jitter == 0 and shimmer == 0:
        return {}

    scores = {}

    # Tonal/melodic: HNR > 10, jitter < 2.0, shimmer < 0.5
    tonal = 0.0
    if hnr > 10:
        tonal += 0.40
    elif hnr > 6:
        tonal += 0.20
    if jitter < 2.0:
        tonal += 0.30
    if shimmer < 0.5:
        tonal += 0.30

    # Breathy/airy: HNR < 8, jitter 1-3, shimmer 0.3-0.8
    breathy = 0.0
    if hnr < 8:
        breathy += 0.35
    if 1.0 <= jitter <= 3.0:
        breathy += 0.35
    if 0.3 <= shimmer <= 0.8:
        breathy += 0.30

    # Strained/rough: HNR < 6, jitter > 3.0, shimmer > 0.8
    strained = 0.0
    if hnr < 6:
        strained += 0.35
    if jitter > 3.0:
        strained += 0.35
    if shimmer > 0.8:
        strained += 0.30

    # Calling/urgent: HNR > 8, jitter 2-4, shimmer 0.5-1.0
    calling = 0.0
    if hnr > 8:
        calling += 0.30
    if 2.0 <= jitter <= 4.0:
        calling += 0.40
    if 0.5 <= shimmer <= 1.0:
        calling += 0.30

    # Map voice patterns to emotions
    scores["hungry"] = min(1.0, tonal * 0.7 + calling * 0.3)
    scores["tired"] = min(1.0, tonal * 0.6 + breathy * 0.4)
    scores["discomfort"] = min(1.0, breathy * 0.7 + strained * 0.3)
    scores["gas"] = min(1.0, strained * 0.8 + breathy * 0.2)
    scores["burp"] = min(1.0, strained * 0.5 + breathy * 0.5)
    scores["pain"] = min(1.0, strained * 0.9 + calling * 0.1)
    scores["closeness"] = min(1.0, tonal * 0.5 + breathy * 0.5)

    # Older baby emotions (present even for 0-6m in case scores blend)
    scores["frustration"] = min(1.0, strained * 0.6 + calling * 0.4)
    scores["separation_anxiety"] = min(1.0, calling * 0.7 + tonal * 0.3)
    scores["boredom"] = min(1.0, breathy * 0.6 + tonal * 0.4)
    scores["fear"] = min(1.0, strained * 0.5 + calling * 0.5)
    scores["tantrum"] = min(1.0, strained * 0.8 + calling * 0.2)

    return scores


def _score_temporal_pattern(features: Dict) -> Dict[str, float]:
    """
    Layer 3: Temporal pattern scorer using cry rhythm and duration.

    Uses cry_fraction, pause_ratio, syllable_rate from rich_features.
    Returns empty dict if temporal data is not available.
    """
    cry_frac = features.get("cry_fraction", 0)
    pause_ratio = features.get("pause_ratio", 0)
    syl_rate = features.get("syllable_rate", 0)

    # Skip if no temporal data
    if cry_frac == 0 and pause_ratio == 0:
        return {}

    scores = {}

    # Hungry: rhythmic repetition — moderate cry, moderate pauses, high syllable rate
    hungry = 0.0
    if 0.4 <= cry_frac <= 0.7:
        hungry += 0.35
    elif 0.3 <= cry_frac <= 0.8:
        hungry += 0.15
    if 0.2 <= pause_ratio <= 0.5:
        hungry += 0.35
    if syl_rate > 1.5:
        hungry += 0.30
    scores["hungry"] = min(1.0, hungry)

    # Tired: drawn-out sustained — high cry fraction, few pauses, low syllable rate
    tired = 0.0
    if 0.6 <= cry_frac <= 0.9:
        tired += 0.35
    elif cry_frac > 0.5:
        tired += 0.15
    if pause_ratio < 0.2:
        tired += 0.35
    if syl_rate < 1.0:
        tired += 0.30
    scores["tired"] = min(1.0, tired)

    # Discomfort: short intermittent — low-mid cry, high pauses
    discomfort = 0.0
    if 0.2 <= cry_frac <= 0.5:
        discomfort += 0.35
    if 0.4 <= pause_ratio <= 0.7:
        discomfort += 0.35
    if syl_rate > 2.0:
        discomfort += 0.30
    scores["discomfort"] = min(1.0, discomfort)

    # Gas: intense straining — high cry, very few pauses
    gas = 0.0
    if cry_frac > 0.6:
        gas += 0.35
    if pause_ratio < 0.15:
        gas += 0.35
    if 1.0 <= syl_rate <= 2.0:
        gas += 0.30
    scores["gas"] = min(1.0, gas)

    # Burp: short repetitive — low-mid cry, moderate pauses
    burp = 0.0
    if 0.2 <= cry_frac <= 0.5:
        burp += 0.40
    if 0.3 <= pause_ratio <= 0.6:
        burp += 0.30
    if syl_rate > 2.0:
        burp += 0.30
    scores["burp"] = min(1.0, burp)

    # Pain: intense sustained — very high cry, minimal pauses
    pain = 0.0
    if cry_frac > 0.7:
        pain += 0.40
    if pause_ratio < 0.15:
        pain += 0.35
    if syl_rate < 1.5:
        pain += 0.25
    scores["pain"] = min(1.0, pain)

    # Closeness: fussy on-off — low cry, high pauses
    closeness = 0.0
    if 0.1 <= cry_frac <= 0.3:
        closeness += 0.40
    if 0.5 <= pause_ratio <= 0.8:
        closeness += 0.35
    scores["closeness"] = min(1.0, closeness)

    # Older baby emotions
    scores["frustration"] = min(1.0, max(0, cry_frac * 0.6 + (1.0 - pause_ratio) * 0.4))
    scores["separation_anxiety"] = min(1.0, max(0, cry_frac * 0.5 + pause_ratio * 0.3 + (syl_rate / 4.0) * 0.2))
    scores["boredom"] = min(1.0, max(0, (1.0 - cry_frac) * 0.5 + pause_ratio * 0.5))
    scores["fear"] = min(1.0, max(0, cry_frac * 0.7 + (1.0 - pause_ratio) * 0.3))
    scores["tantrum"] = min(1.0, max(0, cry_frac * 0.8 + (1.0 - pause_ratio) * 0.2))

    return scores


def _blend_layers(
    acoustic_scores: Dict[str, float],
    formant_scores: Dict[str, float],
    voice_scores: Dict[str, float],
    temporal_scores: Dict[str, float],
    age_bracket: str,
) -> Dict[str, float]:
    """
    Blend the 4 scoring layers with age-dependent weights.
    If a layer returned empty (features unavailable), its weight is
    redistributed proportionally to the remaining layers.
    """
    # Age-dependent base weights: [acoustic, formant, voice_quality, temporal]
    if age_bracket == "0_6m":
        weights = [0.30, 0.35, 0.20, 0.15]
    elif age_bracket == "6_12m":
        weights = [0.40, 0.20, 0.20, 0.20]
    else:  # 12m+
        weights = [0.45, 0.10, 0.25, 0.20]

    layers = [acoustic_scores, formant_scores, voice_scores, temporal_scores]

    # Identify available layers (non-empty)
    available = [(w, layer) for w, layer in zip(weights, layers) if layer]
    if not available:
        return acoustic_scores  # Fallback to acoustic only

    # Redistribute weights for missing layers
    total_available = sum(w for w, _ in available)
    if total_available <= 0:
        return acoustic_scores

    # Collect all emotion keys across available layers
    all_keys = set()
    for _, layer in available:
        all_keys.update(layer.keys())

    blended = {}
    for key in all_keys:
        score = 0.0
        for w, layer in available:
            normalized_w = w / total_available
            score += normalized_w * layer.get(key, 0.0)
        blended[key] = min(1.0, score)

    return blended


def analyze_cry(
    features: Dict,
    age_days: Optional[int] = None,
    trained_model_result: Optional[Dict] = None,
) -> Dict[str, Any]:
    """
    Analyze cry sounds and determine probable emotion.

    Args:
        features: Acoustic features from sound_classifier
        age_days: Child's age in days
        trained_model_result: Optional output from cry training model

    Returns:
        {
            "primary_emotion": str,
            "emotion_label": str,
            "emotion_icon": str,
            "confidence": float,
            "emotion_scores": {"hungry": 0.8, "tired": 0.3, ...},
            "age_bracket": str,
            "what_hearing": str,
            "what_means": str,
            "what_try": [str, ...],
            "dunstan_sound": str or None,
            "age_cry_match": {
                "matches": bool,
                "expected_f0_range": (float, float),
                "actual_f0": float,
                "probable_age_bracket": str,
            }
        }
    """
    age_bracket = get_age_bracket(age_days)
    emotions_map = get_emotions_for_age(age_days)

    # --- 4-layer scoring ---
    # Layer 0: Acoustic heuristic (existing scorers)
    if age_bracket == "0_6m":
        acoustic_scores = _score_dunstan_sounds(features)
    else:
        acoustic_scores = _score_older_baby_emotions(features, age_bracket)

    # Layer 1: Formant-based Dunstan matcher (F1 + F2 vowel space)
    formant_scores = _score_formant_dunstan(features)

    # Layer 2: Voice quality (HNR + jitter + shimmer)
    voice_scores = _score_voice_quality(features)

    # Layer 3: Temporal pattern (cry_fraction + pause_ratio + syllable_rate)
    temporal_scores = _score_temporal_pattern(features)

    # Blend layers with age-dependent weights
    emotion_scores = _blend_layers(
        acoustic_scores, formant_scores, voice_scores, temporal_scores,
        age_bracket,
    )

    # Blend with trained model if available.
    # weight scales from 0.40 (low confidence) to 0.80 (high confidence):
    #   confidence=0.2 → weight=0.48 → 52% acoustic, 48% model
    #   confidence=0.5 → weight=0.60 → 40% acoustic, 60% model
    #   confidence=0.9 → weight=0.76 → 24% acoustic, 76% model
    if trained_model_result and isinstance(trained_model_result, dict):
        model_scores = trained_model_result.get("emotion_scores", {})
        model_confidence = trained_model_result.get("confidence", 0.5)
        weight = min(0.80, 0.40 + 0.40 * model_confidence)
        for key in emotion_scores:
            if key in model_scores:
                emotion_scores[key] = (1.0 - weight) * emotion_scores[key] + weight * model_scores[key]
        # Include any emotions the trained model knows that acoustic scoring doesn't cover
        for key in model_scores:
            if key not in emotion_scores:
                emotion_scores[key] = weight * model_scores[key]

    # Filter to only emotions available for this age
    available_emotions = set(emotions_map.keys())
    filtered_scores = {k: v for k, v in emotion_scores.items() if k in available_emotions}

    if not filtered_scores:
        filtered_scores = {"discomfort": 0.5}

    # Determine primary emotion
    ranked = sorted(filtered_scores.items(), key=lambda x: x[1], reverse=True)
    primary_key = ranked[0][0]
    primary_score = ranked[0][1]
    second_score = ranked[1][1] if len(ranked) > 1 else 0

    # Confidence based on margin
    confidence = min(0.92, primary_score * (1.0 + (primary_score - second_score) * 0.5))

    # Get emotion details
    emotion_info = emotions_map.get(primary_key, {})

    # Age-based cry frequency matching
    f0_actual = features.get("f0_mean", 0)
    age_cry_match = _check_cry_age_match(f0_actual, age_bracket, age_days)

    # Top 3 emotions for display
    top_emotions = []
    for key, score in ranked[:3]:
        if score > 0.1:
            emo = emotions_map.get(key, {})
            top_emotions.append({
                "key": key,
                "label": emo.get("label", key),
                "icon": emo.get("icon", ""),
                "score": round(score, 3),
            })

    return {
        "primary_emotion": primary_key,
        "emotion_label": emotion_info.get("label", primary_key),
        "emotion_icon": emotion_info.get("icon", "😢"),
        "confidence": round(confidence, 3),
        "emotion_scores": {k: round(v, 3) for k, v in filtered_scores.items()},
        "top_emotions": top_emotions,
        "age_bracket": age_bracket,
        "what_hearing": emotion_info.get("what_hearing", "Cry sounds detected"),
        "what_means": emotion_info.get("what_means", "Your baby is expressing a need"),
        "what_try": emotion_info.get("what_try", ["Observe and respond to your baby's cues"]),
        "dunstan_sound": emotion_info.get("dunstan") if age_bracket == "0_6m" else None,
        "age_cry_match": age_cry_match,
    }


def _check_cry_age_match(
    f0_actual: float,
    age_bracket: str,
    age_days: Optional[int],
) -> Dict[str, Any]:
    """Check if the cry frequency matches the registered age."""
    if f0_actual <= 0:
        return {"matches": True, "reason": "insufficient_data"}

    expected = CRY_FREQUENCY_BY_AGE.get(age_bracket, CRY_FREQUENCY_BY_AGE["0_6m"])
    f0_min, f0_max = expected["f0_range"]

    matches = f0_min <= f0_actual <= f0_max

    # Find which age bracket the cry actually matches
    probable_bracket = age_bracket
    if not matches:
        best_fit = None
        best_distance = float("inf")
        for bracket, params in CRY_FREQUENCY_BY_AGE.items():
            mid = params["typical_f0"]
            dist = abs(f0_actual - mid)
            if dist < best_distance:
                best_distance = dist
                best_fit = bracket
        if best_fit:
            probable_bracket = best_fit

    bracket_labels = {
        "0_6m": "0-6 months",
        "6_12m": "6-12 months",
        "12_18m": "12-18 months",
        "18_24m": "18-24 months",
        "24_36m": "24-36 months",
    }

    return {
        "matches": matches,
        "expected_f0_range": [f0_min, f0_max],
        "actual_f0": round(f0_actual, 1),
        "registered_age_bracket": bracket_labels.get(age_bracket, age_bracket),
        "probable_age_bracket": bracket_labels.get(probable_bracket, probable_bracket),
        "mismatch": not matches,
    }
