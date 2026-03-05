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
        "what_hearing": "Soft, slow, breathy cry with a yawn-like quality — often near sleep, with long pauses between cries",
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

# Age bracket mapping (system scope: 0-24 months)
# Active runtime scope is trimmed to 0-3 months.
CANONICAL_AGE_BRACKET = "0_3m"
LEGACY_AGE_BRACKET = "0_6m"

AGE_EMOTION_MAP = {
    CANONICAL_AGE_BRACKET: EMOTIONS_0_6M,
    # "6_12m": EMOTIONS_6_12M,
    # "12_18m": EMOTIONS_12_18M,
    # "18_24m": EMOTIONS_18_24M,
}


def get_age_bracket(age_days: Optional[int]) -> str:
    """Convert age in days to age bracket string."""
    if age_days is None or age_days < 0:
        return CANONICAL_AGE_BRACKET
    months = age_days / 30.44
    # if months < 6:
    if months <= 3:
        return CANONICAL_AGE_BRACKET
    # elif months < 12:
    #     return "6_12m"
    # elif months < 18:
    #     return "12_18m"
    # elif months < 24:
    #     return "18_24m"
    # else:
    #     # Hard cap to supported range (0-24 months).
    #     return "18_24m"
    # Hard cap to active 0-3 month runtime path.
    return CANONICAL_AGE_BRACKET


def get_emotions_for_age(age_days: Optional[int]) -> Dict[str, Dict]:
    """Get the emotion set appropriate for the child's age."""
    bracket = get_age_bracket(age_days)
    return AGE_EMOTION_MAP.get(bracket, AGE_EMOTION_MAP[CANONICAL_AGE_BRACKET])


# ---------------------------------------------------------------------------
# Acoustic cry pattern analysis
# ---------------------------------------------------------------------------

# Age-specific cry frequency characteristics (research-based)
CRY_FREQUENCY_BY_AGE = {
    CANONICAL_AGE_BRACKET: {"f0_range": (350, 650), "typical_f0": 500, "duration_typical": (1.0, 5.0)},
    # "6_12m": {"f0_range": (300, 600), "typical_f0": 450, "duration_typical": (0.5, 4.0)},
    # "12_18m": {"f0_range": (280, 550), "typical_f0": 400, "duration_typical": (0.5, 3.5)},
    # "18_24m": {"f0_range": (250, 500), "typical_f0": 370, "duration_typical": (0.3, 3.0)},
}


EMOTION_PROFILES_0_6M = {
    "hungry": {
        "prior": 0.08,
        "rules": [
            {"feature": "f0", "min": 300.0, "max": 560.0, "weight": 0.20},
            {"feature": "f0_instability", "min": 0.0, "max": 0.16, "weight": 0.14},
            {"feature": "spectral_centroid", "min": 800.0, "max": 2500.0, "weight": 0.16},
            {"feature": "energy_var", "min": 0.20, "max": 0.65, "weight": 0.12},
            {"feature": "voiced_fraction", "min": 0.30, "max": 0.95, "weight": 0.10},
            {"feature": "rms_mean", "min": 0.055, "max": 0.16, "weight": 0.10},
            {"feature": "duration_s", "min": 2.0, "max": 8.0, "weight": 0.08},
        ],
        "compound_rules": [
            {
                "label": "voiced_variable_pattern",
                "weight": 0.08,
                "all": [
                    {"feature": "voiced_fraction", "min": 0.30},
                    {"feature": "energy_var", "min": 0.20},
                ],
            },
        ],
    },
    "tired": {
        "prior": 0.03,
        "rules": [
            {"feature": "f0", "min": 220.0, "max": 430.0, "weight": 0.20},
            {"feature": "f0_instability", "min": 0.0, "max": 0.11, "weight": 0.18},
            {"feature": "rms_mean", "min": 0.015, "max": 0.08, "weight": 0.22},
            {"feature": "zcr", "min": 0.0, "max": 0.032, "weight": 0.16},
            {"feature": "duration_s", "min": 2.2, "max": 8.0, "weight": 0.12},
            {"feature": "voiced_fraction", "min": 0.15, "max": 0.70, "weight": 0.12},
        ],
        "compound_rules": [
            {
                "label": "sleepy_signature",
                "weight": 0.10,
                "all": [
                    {"feature": "rms_mean", "max": 0.07},
                    {"feature": "zcr", "max": 0.035},
                    {"feature": "f0_instability", "max": 0.11},
                    {"feature": "duration_s", "min": 2.0},
                ],
            },
        ],
    },
    "discomfort": {
        "prior": 0.06,
        "rules": [
            {"feature": "zcr", "min": 0.03, "max": 0.09, "weight": 0.20},
            {"feature": "energy_var", "min": 0.28, "max": 0.60, "weight": 0.20},
            {"feature": "rms_mean", "min": 0.03, "max": 0.11, "weight": 0.16},
            {"feature": "f0_instability", "min": 0.10, "max": 0.22, "weight": 0.16},
            {"feature": "duration_s", "min": 0.4, "max": 3.0, "weight": 0.12},
            {"feature": "spectral_centroid", "min": 1200.0, "max": 2800.0, "weight": 0.12},
        ],
    },
    "gas": {
        "prior": 0.00,
        "rules": [
            {"feature": "f0", "min": 400.0, "max": 660.0, "weight": 0.08},
            {"feature": "rms_mean", "min": 0.085, "max": 0.18, "weight": 0.12},
            {"feature": "f0_instability", "min": 0.20, "max": 0.35, "weight": 0.13},
            {"feature": "spectral_centroid", "min": 2200.0, "max": 4200.0, "weight": 0.14},
            {"feature": "voiced_fraction", "min": 0.45, "max": 0.95, "weight": 0.10},
            {"feature": "energy_var", "min": 0.38, "max": 0.80, "weight": 0.10},
            {"feature": "duration_s", "min": 1.0, "max": 4.5, "weight": 0.06},
        ],
        "compound_rules": [
            {
                "label": "strain_signature",
                "weight": 0.06,
                "all": [
                    {"feature": "rms_mean", "min": 0.07},
                    {"feature": "energy_var", "min": 0.30},
                    {"feature": "f0_instability", "min": 0.14},
                    {"feature": "spectral_centroid", "min": 1800.0},
                ],
            },
        ],
    },
    "burp": {
        "prior": 0.00,
        "rules": [
            {"feature": "f0", "min": 280.0, "max": 520.0, "weight": 0.18},
            {"feature": "energy_var", "min": 0.22, "max": 0.55, "weight": 0.24},
            {"feature": "f0_instability", "min": 0.0, "max": 0.13, "weight": 0.18},
            {"feature": "zcr", "min": 0.0, "max": 0.05, "weight": 0.14},
            {"feature": "duration_s", "min": 0.2, "max": 2.5, "weight": 0.12},
            {"feature": "rms_mean", "min": 0.03, "max": 0.10, "weight": 0.14},
        ],
    },
    "pain": {
        "prior": 0.00,
        "rules": [
            {"feature": "f0", "min": 500.0, "max": 1000.0, "weight": 0.20},
            {"feature": "rms_mean", "min": 0.11, "max": 0.40, "weight": 0.24},
            {"feature": "voiced_fraction", "min": 0.45, "max": 1.00, "weight": 0.14},
            {"feature": "spectral_centroid", "min": 2100.0, "max": 5000.0, "weight": 0.12},
            {"feature": "f0_instability", "min": 0.18, "max": 0.50, "weight": 0.10},
            {"feature": "duration_s", "min": 1.2, "max": 8.0, "weight": 0.10},
            {"feature": "energy_var", "min": 0.0, "max": 0.22, "weight": 0.10},
        ],
        "compound_rules": [
            {
                "label": "pain_signature",
                "weight": 0.10,
                "all": [
                    {"feature": "rms_mean", "min": 0.11},
                    {"feature": "f0", "min": 520.0},
                    {"feature": "voiced_fraction", "min": 0.45},
                ],
            },
        ],
    },
    "closeness": {
        "prior": 0.00,
        "rules": [
            {"feature": "f0", "min": 120.0, "max": 420.0, "weight": 0.20},
            {"feature": "rms_mean", "min": 0.0, "max": 0.055, "weight": 0.24},
            {"feature": "energy_var", "min": 0.24, "max": 0.70, "weight": 0.14},
            {"feature": "f0_instability", "min": 0.0, "max": 0.12, "weight": 0.16},
            {"feature": "zcr", "min": 0.0, "max": 0.045, "weight": 0.12},
            {"feature": "duration_s", "min": 1.2, "max": 8.0, "weight": 0.10},
            {"feature": "voiced_fraction", "min": 0.05, "max": 0.70, "weight": 0.08},
        ],
    },
}


# Keep conflict rules empty in current mode: winner should come from natural profile score.
CONFLICT_RULES_0_6M: List[Dict[str, Any]] = []


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _extract_scoring_features(features: Dict) -> Dict[str, float]:
    return {
        "f0": _to_float(features.get("f0_mean", 0.0)),
        "f0_instability": _to_float(features.get("f0_instability", 0.0)),
        "spectral_centroid": _to_float(features.get("spectral_centroid", 0.0)),
        "zcr": _to_float(features.get("zcr", 0.0)),
        "energy_var": _to_float(features.get("energy_variability", 0.0)),
        "rms_mean": _to_float(features.get("rms_mean", 0.0)),
        "voiced_fraction": _to_float(features.get("voiced_fraction", 0.0)),
        "duration_s": _to_float(features.get("duration_s", 0.0)),
    }


def _soft_range_match(value: float, min_v: Optional[float], max_v: Optional[float], tol_ratio: float = 0.20) -> float:
    """Smooth range match score in [0,1] with soft edges."""
    if min_v is None and max_v is None:
        return 1.0
    if min_v is not None and max_v is not None and max_v < min_v:
        min_v, max_v = max_v, min_v

    if min_v is None:
        if value <= max_v:
            return 1.0
        span = max(abs(max_v), 1e-6)
        tol = span * tol_ratio
        return max(0.0, min(1.0, (max_v + tol - value) / max(tol, 1e-6)))

    if max_v is None:
        if value >= min_v:
            return 1.0
        span = max(abs(min_v), 1e-6)
        tol = span * tol_ratio
        return max(0.0, min(1.0, (value - (min_v - tol)) / max(tol, 1e-6)))

    span = max(max_v - min_v, 1e-6)
    tol = span * tol_ratio
    if min_v <= value <= max_v:
        return 1.0
    if value < min_v:
        return max(0.0, min(1.0, (value - (min_v - tol)) / max(tol, 1e-6)))
    return max(0.0, min(1.0, (max_v + tol - value) / max(tol, 1e-6)))


def _evaluate_condition(values: Dict[str, float], cond: Dict[str, Any]) -> float:
    feature = cond.get("feature")
    if not feature or feature not in values:
        return 0.0
    value = values[feature]
    return _soft_range_match(
        value=value,
        min_v=cond.get("min"),
        max_v=cond.get("max"),
        tol_ratio=_to_float(cond.get("tol_ratio", 0.20), 0.20),
    )


def _derive_signatures(values: Dict[str, float]) -> Dict[str, bool]:
    strain = (
        values["rms_mean"] > 0.07
        and values["energy_var"] > 0.30
        and values["f0_instability"] > 0.14
        and values["spectral_centroid"] > 1800
    )
    return {
        "sleepy": (
            values["rms_mean"] < 0.07
            and values["zcr"] < 0.035
            and values["f0_instability"] < 0.11
            and values["duration_s"] >= 2.0
        ),
        "strain": strain,
        "hungry": (
            280 <= values["f0"] <= 620
            and values["f0_instability"] <= 0.16
            and 0.18 <= values["energy_var"] <= 0.55
            and values["spectral_centroid"] <= 2600
            and 0.04 <= values["rms_mean"] <= 0.16
        ),
        "discomfort": (
            values["zcr"] > 0.03
            and values["energy_var"] > 0.26
            and values["rms_mean"] < 0.12
            and values["f0_instability"] > 0.09
            and not strain
        ),
        "pain": (
            values["rms_mean"] > 0.11
            and values["f0"] > 520
            and values["voiced_fraction"] > 0.45
        ),
    }


def _score_profiles(values: Dict[str, float], profiles: Dict[str, Dict]) -> tuple:
    scores: Dict[str, float] = {}
    trigger_map: Dict[str, List[Dict[str, Any]]] = {}

    for emotion, cfg in profiles.items():
        score = _to_float(cfg.get("prior", 0.0), 0.0)
        triggers: List[Dict[str, Any]] = []

        for rule in cfg.get("rules", []):
            weight = _to_float(rule.get("weight", 0.0), 0.0)
            if weight <= 0:
                continue
            match = _evaluate_condition(values, rule)
            gain = weight * match
            score += gain
            if gain >= max(0.04, 0.45 * weight):
                feat = rule.get("feature", "unknown")
                triggers.append({
                    "rule": f"{feat}:{rule.get('min', '-inf')}..{rule.get('max', '+inf')}",
                    "gain": round(gain, 3),
                    "value": round(values.get(feat, 0.0), 4),
                })

        for crule in cfg.get("compound_rules", []):
            weight = _to_float(crule.get("weight", 0.0), 0.0)
            conds = crule.get("all", [])
            if weight <= 0 or not conds:
                continue
            match_scores = [_evaluate_condition(values, c) for c in conds]
            match = min(match_scores) if match_scores else 0.0
            gain = weight * match
            score += gain
            if gain >= max(0.03, 0.40 * weight):
                triggers.append({
                    "rule": str(crule.get("label", "compound_rule")),
                    "gain": round(gain, 3),
                    "value": 1.0 if match >= 0.99 else round(match, 3),
                })

        scores[emotion] = min(1.0, max(0.0, score))
        triggers.sort(key=lambda x: x.get("gain", 0.0), reverse=True)
        trigger_map[emotion] = triggers[:4]

    return scores, trigger_map


def _apply_conflict_rules(scores: Dict[str, float], signatures: Dict[str, bool], rules: List[Dict[str, Any]]) -> Dict[str, Any]:
    resolved = dict(scores)
    applied_rules: List[str] = []
    preferred_primary = None
    overlap_flags: Dict[str, bool] = {}

    for rule in rules:
        apply_now = True
        has_condition = False

        signature_key = rule.get("if_signature")
        if signature_key:
            has_condition = True
            apply_now = apply_now and bool(signatures.get(signature_key, False))

        overlap_cfg = rule.get("if_scores_overlap")
        if overlap_cfg:
            has_condition = True
            a = overlap_cfg.get("a")
            b = overlap_cfg.get("b")
            min_score = _to_float(overlap_cfg.get("min_score", 0.0), 0.0)
            max_b_minus_a = _to_float(overlap_cfg.get("max_b_minus_a", 0.0), 0.0)
            overlap_match = False
            if a in resolved and b in resolved:
                overlap_match = (
                    resolved[a] >= min_score
                    and resolved[b] >= min_score
                    and (resolved[b] - resolved[a]) < max_b_minus_a
                )
            apply_now = apply_now and overlap_match

        if not has_condition:
            apply_now = False

        if not apply_now:
            continue

        for emotion, scale in rule.get("scale", {}).items():
            if emotion in resolved:
                resolved[emotion] = min(1.0, max(0.0, resolved[emotion] * _to_float(scale, 1.0)))

        rule_name = str(rule.get("name", "conflict_rule"))
        applied_rules.append(rule_name)
        if "hungry_discomfort_overlap" in rule_name or "discomfort_hungry_overlap" in rule_name:
            overlap_flags["hungry_discomfort_overlap"] = True
        prefer = rule.get("prefer_primary")
        if prefer:
            preferred_primary = str(prefer)

    return {
        "scores": resolved,
        "applied_rules": applied_rules,
        "preferred_primary": preferred_primary,
        "overlap_flags": overlap_flags,
    }


def _score_dunstan_sounds(features: Dict, return_debug: bool = False) -> Any:
    """
    Uniform, profile-driven scoring for 0-3 month cry emotions.
    """
    values = _extract_scoring_features(features)
    signatures = _derive_signatures(values)
    raw_scores, trigger_map = _score_profiles(values, EMOTION_PROFILES_0_6M)
    resolved = _apply_conflict_rules(raw_scores, signatures, CONFLICT_RULES_0_6M)

    scores = resolved["scores"]
    if not return_debug:
        return scores

    debug = {
        "applied_conflict_rules": resolved.get("applied_rules", []),
        "preferred_primary": resolved.get("preferred_primary"),
        "signatures": signatures,
        "emotion_triggers": trigger_map,
        "feature_snapshot": {
            "f0": round(values["f0"], 2),
            "rms_mean": round(values["rms_mean"], 5),
            "energy_var": round(values["energy_var"], 3),
            "zcr": round(values["zcr"], 4),
            "duration_s": round(values["duration_s"], 2),
        },
        "overlap_flags": resolved.get("overlap_flags", {}),
    }
    return scores, debug


def _select_dunstan_info(
    primary_key: str,
    filtered_scores: Dict[str, float],
    emotions_map: Dict[str, Dict],
) -> Dict[str, Any]:
    """Choose Dunstan sound with ambiguity handling from top cry candidates."""
    candidates = []
    for emotion, score in filtered_scores.items():
        dunstan = emotions_map.get(emotion, {}).get("dunstan")
        if dunstan and score >= 0.20:
            candidates.append((emotion, float(score), str(dunstan)))

    if not candidates:
        return {
            "sound": None,
            "ambiguous": False,
            "candidates": [],
        }

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_emotion, best_score, best_sound = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0.0
    ambiguous = (best_score - second_score) < 0.08 if len(candidates) > 1 else False

    primary_sound = emotions_map.get(primary_key, {}).get("dunstan")
    primary_score = float(filtered_scores.get(primary_key, 0.0))
    chosen_sound = best_sound
    chosen_emotion = best_emotion
    if primary_sound and primary_score + 0.03 >= best_score:
        chosen_sound = str(primary_sound)
        chosen_emotion = primary_key

    out_candidates = [
        {
            "emotion": emo,
            "sound": snd,
            "score": round(sc, 3),
        }
        for emo, sc, snd in candidates[:3]
    ]

    return {
        "sound": chosen_sound,
        "emotion": chosen_emotion,
        "ambiguous": ambiguous,
        "candidates": out_candidates,
    }


def _score_older_baby_emotions(features: Dict, age_bracket: str) -> Dict[str, float]:
    """
    Score emotions for older babies (6m+) using acoustic patterns.
    Extends Dunstan-based scores with frustration, separation anxiety, etc.
    """
    # Start with Dunstan-like base scores
    scores = _score_dunstan_sounds(features)

    f0 = features.get("f0_mean", 0)
    f0_instability = features.get("f0_instability", 0)
    energy_var = features.get("energy_variability", 0)
    rms_mean = features.get("rms_mean", 0)
    spectral_centroid = features.get("spectral_centroid", 0)

    # Frustration: Building, escalating, loud
    frustration_score = 0.0
    if rms_mean > 0.08:
        frustration_score += 0.30
    if f0_instability > 0.12:
        frustration_score += 0.25
    if energy_var > 0.30:
        frustration_score += 0.25
    if spectral_centroid > 1800:
        frustration_score += 0.20
    scores["frustration"] = min(1.0, frustration_score)

    # Separation anxiety: Sudden onset, clingy quality
    sep_score = 0.0
    if 350 < f0 < 550:
        sep_score += 0.30
    if rms_mean > 0.06:
        sep_score += 0.25
    if f0_instability > 0.10:
        sep_score += 0.25
    if energy_var > 0.25:
        sep_score += 0.20
    scores["separation_anxiety"] = min(1.0, sep_score)

    # Boredom: Low intensity, on-off
    bore_score = 0.0
    if rms_mean < 0.05:
        bore_score += 0.35
    if energy_var > 0.35:
        bore_score += 0.30
    if f0 < 350:
        bore_score += 0.20
    if f0_instability < 0.08:
        bore_score += 0.15
    scores["boredom"] = min(1.0, bore_score)

    # Tantrum (12m+)
    if age_bracket in ("12_18m", "18_24m"):
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
    if age_bracket in ("12_18m", "18_24m"):
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
    scoring_debug: Dict[str, Any] = {}

    # Score emotions based on age
    if age_bracket == CANONICAL_AGE_BRACKET:
        emotion_scores, scoring_debug = _score_dunstan_sounds(features, return_debug=True)
    # else:
    #     emotion_scores = _score_older_baby_emotions(features, age_bracket)
    else:
        emotion_scores = _score_dunstan_sounds(features)

    # Blend with trained model if available
    if trained_model_result and isinstance(trained_model_result, dict):
        model_scores = trained_model_result.get("emotion_scores", {})
        model_confidence = trained_model_result.get("confidence", 0.5)
        model_samples = _to_float(trained_model_result.get("total_training_samples", 0), 0.0)
        sample_factor = min(1.0, model_samples / 120.0)
        # Adaptive blending: low-data models stay supportive; mature models contribute more.
        model_weight = min(0.45, 0.10 + 0.22 * _to_float(model_confidence, 0.5) + 0.13 * sample_factor)
        acoustic_weight = 1.0 - model_weight
        for key in emotion_scores:
            if key in model_scores:
                acoustic_val = emotion_scores[key]
                model_val = model_scores[key]
                emotion_scores[key] = acoustic_weight * acoustic_val + model_weight * model_val

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
    preferred_primary = scoring_debug.get("preferred_primary")
    hungry_discomfort_overlap = bool(
        scoring_debug.get("overlap_flags", {}).get("hungry_discomfort_overlap", False)
    )

    if preferred_primary in filtered_scores:
        primary_key = preferred_primary
        primary_score = filtered_scores[preferred_primary]
        second_score = max([v for k, v in filtered_scores.items() if k != preferred_primary] or [0.0])

    # Confidence from top score + margin; avoids constant 92% plateaus.
    margin = max(0.0, primary_score - second_score)
    confidence = min(0.90, max(0.35, 0.55 * primary_score + 0.45 * margin))
    if margin < 0.07:
        confidence = min(confidence, 0.72 + margin)
    is_close_call = margin < 0.10 and second_score > 0.35

    # Get emotion details
    emotion_info = emotions_map.get(primary_key, {})

    # Age-based cry frequency matching
    f0_actual = features.get("f0_mean", 0)
    age_cry_match = _check_cry_age_match(f0_actual, age_bracket, age_days)

    # Top emotions for display:
    # - Always include top 2 so UI can show "also possible" guidance consistently.
    # - Include 3rd only if it has meaningful signal.
    display_ranked = ranked
    if preferred_primary in filtered_scores:
        display_ranked = [(preferred_primary, filtered_scores[preferred_primary])] + [
            item for item in ranked if item[0] != preferred_primary
        ]

    top_emotions = []
    for idx, (key, score) in enumerate(display_ranked[:3]):
        if idx >= 2 and score <= 0.1:
            continue
        emo = emotions_map.get(key, {})
        top_emotions.append({
            "key": key,
            "label": emo.get("label", key),
            "icon": emo.get("icon", ""),
            "score": round(score, 3),
        })

    dunstan_info = _select_dunstan_info(primary_key, filtered_scores, emotions_map)

    debug_trace = {
        "applied_conflict_rules": scoring_debug.get("applied_conflict_rules", []),
        "feature_snapshot": scoring_debug.get("feature_snapshot", {}),
        "margin": round(margin, 3),
        "close_call": is_close_call,
        "dunstan_info": dunstan_info,
        "top_feature_triggers": {
            emo_key: scoring_debug.get("emotion_triggers", {}).get(emo_key, [])[:2]
            for emo_key, _ in display_ranked[:3]
        },
    }

    secondary_emotion = top_emotions[1] if len(top_emotions) > 1 else None

    return {
        "primary_emotion": primary_key,
        "emotion_label": emotion_info.get("label", primary_key),
        "emotion_icon": emotion_info.get("icon", "😢"),
        "confidence": round(confidence, 3),
        "emotion_scores": {k: round(v, 3) for k, v in filtered_scores.items()},
        "top_emotions": top_emotions,
        "secondary_emotion": secondary_emotion,
        "age_bracket": age_bracket,
        "hungry_discomfort_overlap": hungry_discomfort_overlap,
        "what_hearing": emotion_info.get("what_hearing", "Cry sounds detected"),
        "what_means": emotion_info.get("what_means", "Your baby is expressing a need"),
        "what_try": emotion_info.get("what_try", ["Observe and respond to your baby's cues"]),
        "dunstan_sound": dunstan_info.get("sound") if age_bracket == CANONICAL_AGE_BRACKET else None,
        "dunstan_ambiguous": bool(dunstan_info.get("ambiguous", False)),
        "dunstan_candidates": dunstan_info.get("candidates", []),
        "decision_close_call": is_close_call,
        "age_cry_match": age_cry_match,
        "debug_trace": debug_trace,
    }


def _check_cry_age_match(
    f0_actual: float,
    age_bracket: str,
    age_days: Optional[int],
) -> Dict[str, Any]:
    """Check if the cry frequency matches the registered age."""
    if f0_actual <= 0:
        return {"matches": True, "reason": "insufficient_data"}

    expected = CRY_FREQUENCY_BY_AGE.get(age_bracket, CRY_FREQUENCY_BY_AGE[CANONICAL_AGE_BRACKET])
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
        # "0_6m": "0-6 months",
        CANONICAL_AGE_BRACKET: "0-3 months",
        LEGACY_AGE_BRACKET: "0-3 months",
        # "6_12m": "6-12 months",
        # "12_18m": "12-18 months",
        # "18_24m": "18-24 months",
    }

    return {
        "matches": matches,
        "expected_f0_range": [f0_min, f0_max],
        "actual_f0": round(f0_actual, 1),
        "registered_age_bracket": bracket_labels.get(age_bracket, age_bracket),
        "probable_age_bracket": bracket_labels.get(probable_bracket, probable_bracket),
        "mismatch": not matches,
    }
