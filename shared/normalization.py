"""
Qleam — Normalization Utilities
Score normalization and EMA baseline aggregation
"""
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def normalize_score(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """
    Clamp a value to [0, 1] range.
    """
    if max_val == min_val:
        return 0.0
    normalized = (value - min_val) / (max_val - min_val)
    return max(0.0, min(1.0, normalized))


def normalize_to_range(value: float, observed_min: float, observed_max: float) -> float:
    """
    Normalize value from observed range to [0, 1].
    """
    if observed_max <= observed_min:
        return 0.5
    return normalize_score(value, observed_min, observed_max)


def update_ema_baseline(
    previous_baseline: float,
    current_value: float,
    alpha: float = 0.3
) -> float:
    """
    Exponential Moving Average baseline update.
    
    Formula: new = alpha * current + (1 - alpha) * previous
    
    Args:
        previous_baseline: Previous EMA value
        current_value: Current observed value
        alpha: Smoothing factor (0.3 per spec)
    
    Returns:
        Updated baseline value
    """
    if not (0.0 < alpha < 1.0):
        raise ValueError(f"Alpha must be between 0 and 1, got {alpha}")
    
    new_baseline = alpha * current_value + (1 - alpha) * previous_baseline
    return round(new_baseline, 6)


def update_feature_baselines(
    previous_baselines: Dict[str, float],
    current_scores: Dict[str, float],
    alpha: float = 0.3
) -> Dict[str, float]:
    """
    Update all feature baselines using EMA.
    
    Args:
        previous_baselines: Dict of feature_name -> baseline_value
        current_scores: Dict of feature_name -> current_score
        alpha: EMA smoothing factor
    
    Returns:
        Updated baselines dict
    """
    updated = {}
    for feature, current in current_scores.items():
        previous = previous_baselines.get(feature, current)  # First session: baseline = current
        updated[feature] = update_ema_baseline(previous, current, alpha)
    return updated


def compute_deviation_level(
    current_scores: Dict[str, float],
    baseline: Dict[str, float],
    session_count: int,
    min_sessions: int = 3
) -> Dict:
    """
    Compute deviation from baseline.
    Only meaningful after min_sessions sessions.
    
    Returns:
        {
            "deviation_score": float,
            "deviation_level": "none" | "low" | "moderate" | "high",
            "deviation_flag": bool,
            "features_deviated": list
        }
    """
    if session_count < min_sessions:
        return {
            "deviation_score": 0.0,
            "deviation_level": "none",
            "deviation_flag": False,
            "features_deviated": [],
            "note": f"Baseline still forming ({session_count}/{min_sessions} sessions)"
        }
    
    deviations = {}
    for feature, current in current_scores.items():
        base = baseline.get(feature, current)
        if base > 0:
            deviations[feature] = abs(current - base) / max(base, 0.01)
        else:
            deviations[feature] = abs(current - base)
    
    avg_deviation = sum(deviations.values()) / len(deviations) if deviations else 0.0
    features_deviated = [f for f, d in deviations.items() if d > 0.2]
    
    if avg_deviation < 0.15:
        level = "none"
        flag = False
    elif avg_deviation < 0.30:
        level = "low"
        flag = False
    elif avg_deviation < 0.60:
        level = "moderate"
        flag = True
    else:
        level = "high"
        flag = True
    
    return {
        "deviation_score": round(avg_deviation, 4),
        "deviation_level": level,
        "deviation_flag": flag,
        "features_deviated": features_deviated,
        "feature_deviations": {k: round(v, 4) for k, v in deviations.items()}
    }


def normalize_probability_distribution(distribution: Dict[str, float]) -> Dict[str, float]:
    """
    Normalize a probability distribution so values sum to 1.0.
    Handles zero-sum edge case.
    """
    total = sum(distribution.values())
    if total <= 0:
        # Uniform distribution
        n = len(distribution)
        return {k: round(1.0 / n, 6) for k in distribution} if n > 0 else {}
    return {k: round(v / total, 6) for k, v in distribution.items()}


def compute_readiness_score(feature_scores: Dict[str, float]) -> float:
    """
    Compute a composite readiness score from feature scores.
    Weighted composite per design spec.
    
    Weights:
        rhythm: 0.25
        repetition: 0.25
        emotional_intensity: 0.30
        expressive_flow: 0.20
    """
    weights = {
        "rhythm": 0.25,
        "repetition": 0.25,
        "emotional_intensity": 0.30,
        "expressive_flow": 0.20,
    }
    
    score = 0.0
    total_weight = 0.0
    
    for feature, weight in weights.items():
        if feature in feature_scores:
            score += feature_scores[feature] * weight
            total_weight += weight
    
    if total_weight == 0:
        return 0.5
    
    return round(score / total_weight, 4)


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Clamp value to [min_val, max_val]."""
    return max(min_val, min(max_val, value))


def developmental_stage_from_age(age_days) -> Dict:
    """
    Map age in days to developmental stage name and mode.

    Args:
        age_days: int or None

    Returns:
        {"stage": str, "mode": str}
        mode is one of: PRE_LINGUISTIC | TRANSITION | LINGUISTIC
    """
    # Inline stage map to avoid circular imports
    _STAGE_MAP = [
        (0,    90,   "NEWBORN",           "PRE_LINGUISTIC"),
        (91,   180,  "EARLY_VOCAL",       "PRE_LINGUISTIC"),
        (181,  270,  "CANONICAL_BABBLE",  "TRANSITION"),
        (271,  365,  "PROTO_WORDS",       "TRANSITION"),
        (366,  548,  "FIRST_WORDS",       "LINGUISTIC"),
        (549,  730,  "WORD_COMBINATIONS", "LINGUISTIC"),
        (731,  99999, "EARLY_SENTENCES",  "LINGUISTIC"),
    ]

    if age_days is None or not isinstance(age_days, (int, float)) or age_days < 0:
        return {"stage": "UNKNOWN", "mode": "PRE_LINGUISTIC"}

    for min_d, max_d, stage, mode in _STAGE_MAP:
        if min_d <= int(age_days) <= max_d:
            return {"stage": stage, "mode": mode}

    return {"stage": "EARLY_SENTENCES", "mode": "LINGUISTIC"}


def audio_stage_hint_from_bio(bio_result: Optional[Dict]) -> Dict:
    """
    Derive a developmental stage hint from biological validation signals
    (VTL and F0), instead of relying solely on birth_date.

    Uses vocal tract length (VTL cm) and fundamental frequency (F0 Hz):
      VTL < 9.0cm  + F0 > 380Hz  → NEWBORN        PRE_LINGUISTIC
      VTL < 9.0cm  + F0 ≤ 380Hz  → EARLY_VOCAL    PRE_LINGUISTIC
      VTL 9–10.5cm + F0 > 300Hz  → CANONICAL_BABBLE TRANSITION
      VTL 9–10.5cm + F0 ≤ 300Hz  → PROTO_WORDS    TRANSITION
      VTL 10.5–12cm + F0 > 240Hz → FIRST_WORDS    LINGUISTIC
      VTL 10.5–12cm + F0 ≤ 240Hz → WORD_COMBINATIONS LINGUISTIC
      VTL ≥ 12cm                 → EARLY_SENTENCES LINGUISTIC

    Returns:
        {"stage": str|None, "mode": str|None, "confidence": float}
        stage=None when signals are absent, unreliable, or mimicry suspected.
    """
    _NO_HINT = {"stage": None, "mode": None, "confidence": 0.0}

    if not bio_result:
        return _NO_HINT
    # Adult mimicry suspected or bio validation skipped
    if bio_result.get("mimicry_suspected") or not bio_result.get("is_infant", False):
        return _NO_HINT

    vtl_cm = bio_result.get("vtl_cm") or 0.0
    f0_hz  = bio_result.get("f0_hz")  or 0.0

    # Need at least one reliable signal
    if vtl_cm <= 0:
        return _NO_HINT

    if vtl_cm < 9.0:
        stage = "NEWBORN" if f0_hz > 380 else "EARLY_VOCAL"
        mode  = "PRE_LINGUISTIC"
        conf  = 0.70
    elif vtl_cm < 10.5:
        stage = "CANONICAL_BABBLE" if f0_hz > 300 else "PROTO_WORDS"
        mode  = "TRANSITION"
        conf  = 0.65
    elif vtl_cm < 12.0:
        stage = "FIRST_WORDS" if f0_hz > 240 else "WORD_COMBINATIONS"
        mode  = "LINGUISTIC"
        conf  = 0.60
    else:
        stage = "EARLY_SENTENCES"
        mode  = "LINGUISTIC"
        conf  = 0.55

    return {"stage": stage, "mode": mode, "confidence": round(conf, 2)}
