"""
Rule-based cry emotion scoring for Basic mode / model fallback.

This mirrors the older handmade approach: score acoustic features against
emotion profiles, then normalize to a probability-like distribution.

Phase 2: Age-adjusted thresholds for all ages 0-730 days.
"""
from typing import Any, Dict, List, Optional, Tuple


# =============================================================================
# Phase 2: Age Anchor Points for Developmental Acoustic Curves
# Derived from acoustic development literature (same sources as original thresholds)
# =============================================================================

AGE_ANCHOR_POINTS = {
    # Hungry emotion - F0 thresholds
    "f0_hungry_min": {0: 300.0, 90: 280.0, 180: 250.0, 365: 220.0, 730: 200.0},
    "f0_hungry_max": {0: 560.0, 90: 520.0, 180: 480.0, 365: 420.0, 730: 380.0},
    
    # Tired emotion - F0 thresholds
    "f0_tired_min": {0: 210.0, 90: 200.0, 180: 180.0, 365: 160.0, 730: 150.0},
    "f0_tired_max": {0: 430.0, 90: 400.0, 180: 370.0, 365: 340.0, 730: 320.0},
    
    # Pain emotion - F0 thresholds
    "f0_pain_min": {0: 560.0, 90: 520.0, 180: 480.0, 365: 440.0, 730: 400.0},
    "f0_pain_max": {0: 1100.0, 90: 1000.0, 180: 900.0, 365: 800.0, 730: 700.0},
    
    # Gas emotion - F0 thresholds
    "f0_gas_min": {0: 400.0, 90: 380.0, 180: 350.0, 365: 320.0, 730: 300.0},
    "f0_gas_max": {0: 660.0, 90: 620.0, 180: 580.0, 365: 540.0, 730: 500.0},
    
    # Burp emotion - F0 thresholds
    "f0_burp_min": {0: 280.0, 90: 270.0, 180: 250.0, 365: 230.0, 730: 220.0},
    "f0_burp_max": {0: 520.0, 90: 500.0, 180: 470.0, 365: 440.0, 730: 420.0},
    
    # Content emotion - F0 thresholds
    "f0_content_min": {0: 120.0, 90: 130.0, 180: 140.0, 365: 150.0, 730: 160.0},
    "f0_content_max": {0: 420.0, 90: 400.0, 180: 380.0, 365: 360.0, 730: 350.0},
    
    # RMS (energy) thresholds
    "rms_hungry_min": {0: 0.055, 90: 0.060, 180: 0.065, 365: 0.070, 730: 0.075},
    "rms_hungry_max": {0: 0.16, 90: 0.17, 180: 0.18, 365: 0.19, 730: 0.20},
    "rms_tired_min": {0: 0.010, 90: 0.012, 180: 0.015, 365: 0.018, 730: 0.020},
    "rms_tired_max": {0: 0.075, 90: 0.080, 180: 0.085, 365: 0.090, 730: 0.095},
    "rms_pain_min": {0: 0.13, 90: 0.14, 180: 0.15, 365: 0.16, 730: 0.17},
    "rms_pain_max": {0: 0.45, 90: 0.42, 180: 0.40, 365: 0.38, 730: 0.36},
    "rms_discomfort_min": {0: 0.03, 90: 0.035, 180: 0.04, 365: 0.045, 730: 0.05},
    "rms_discomfort_max": {0: 0.11, 90: 0.12, 180: 0.13, 365: 0.14, 730: 0.15},
    "rms_gas_min": {0: 0.085, 90: 0.090, 180: 0.095, 365: 0.100, 730: 0.105},
    "rms_gas_max": {0: 0.18, 90: 0.19, 180: 0.20, 365: 0.21, 730: 0.22},
    "rms_burp_min": {0: 0.03, 90: 0.035, 180: 0.04, 365: 0.045, 730: 0.05},
    "rms_burp_max": {0: 0.10, 90: 0.105, 180: 0.11, 365: 0.115, 730: 0.12},
    "rms_content_min": {0: 0.0, 90: 0.0, 180: 0.0, 365: 0.0, 730: 0.0},
    "rms_content_max": {0: 0.055, 90: 0.060, 180: 0.065, 365: 0.070, 730: 0.075},
    
    # Spectral centroid thresholds
    "spectral_hungry_min": {0: 800.0, 90: 850.0, 180: 900.0, 365: 950.0, 730: 1000.0},
    "spectral_hungry_max": {0: 2500.0, 90: 2400.0, 180: 2300.0, 365: 2200.0, 730: 2100.0},
    "spectral_pain_min": {0: 2400.0, 90: 2300.0, 180: 2200.0, 365: 2100.0, 730: 2000.0},
    "spectral_pain_max": {0: 5200.0, 90: 5000.0, 180: 4800.0, 365: 4600.0, 730: 4400.0},
    "spectral_gas_min": {0: 2200.0, 90: 2150.0, 180: 2100.0, 365: 2050.0, 730: 2000.0},
    "spectral_gas_max": {0: 4200.0, 90: 4100.0, 180: 4000.0, 365: 3900.0, 730: 3800.0},
    "spectral_discomfort_min": {0: 1200.0, 90: 1250.0, 180: 1300.0, 365: 1350.0, 730: 1400.0},
    "spectral_discomfort_max": {0: 2800.0, 90: 2750.0, 180: 2700.0, 365: 2650.0, 730: 2600.0},
}


def interpolate_threshold(feature_key: str, age_days: int) -> float:
    """
    Linear interpolation between anchor points for given age.
    
    For 0-90 days: returns exact anchor value (preserves current behavior).
    For 91+ days: interpolates between nearest anchors.
    
    Args:
        feature_key: Key in AGE_ANCHOR_POINTS (e.g., "f0_hungry_min")
        age_days: Baby's age in days
    
    Returns:
        Interpolated threshold value
    """
    anchors = AGE_ANCHOR_POINTS.get(feature_key, {})
    if not anchors:
        return 0.0
    
    # Get sorted anchor ages
    ages = sorted(anchors.keys())
    
    # For 0-90 days: return exact value (preserve current behavior)
    if age_days <= 90:
        # Find closest anchor <= age_days
        for age in reversed(ages):
            if age <= age_days:
                return anchors[age]
        return anchors[ages[0]]
    
    # Find surrounding anchors for interpolation
    lower_age = None
    upper_age = None
    
    for age in ages:
        if age <= age_days:
            lower_age = age
        if age >= age_days and upper_age is None:
            upper_age = age
    
    # Edge cases
    if lower_age is None:
        return anchors[ages[0]]
    if upper_age is None:
        return anchors[ages[-1]]
    if lower_age == upper_age:
        return anchors[lower_age]
    
    # Linear interpolation
    lower_val = anchors[lower_age]
    upper_val = anchors[upper_age]
    ratio = (age_days - lower_age) / (upper_age - lower_age)
    return lower_val + ratio * (upper_val - lower_val)


def get_age_adjusted_profiles(age_days: int) -> Dict:
    """
    Returns emotion profiles with age-adjusted thresholds.
    
    For 0-90 days: returns EMOTION_PROFILES_0_3M exactly (no change).
    For 91+ days: returns interpolated profiles based on developmental curves.
    
    Args:
        age_days: Baby's age in days
    
    Returns:
        Dict of emotion profiles with age-appropriate thresholds
    """
    # For 0-90 days: preserve current behavior exactly
    if age_days <= 90:
        return EMOTION_PROFILES_0_3M
    
    # Build age-adjusted profiles for older babies
    adjusted = {}
    
    for emotion, config in EMOTION_PROFILES_0_3M.items():
        adjusted[emotion] = {
            "prior": config["prior"],
            "rules": []
        }
        
        for rule in config["rules"]:
            feature = rule["feature"]
            
            # Map feature name to anchor point keys
            if feature == "f0":
                min_key = f"f0_{emotion}_min"
                max_key = f"f0_{emotion}_max"
            elif feature == "rms_mean":
                min_key = f"rms_{emotion}_min"
                max_key = f"rms_{emotion}_max"
            elif feature == "spectral_centroid":
                min_key = f"spectral_{emotion}_min"
                max_key = f"spectral_{emotion}_max"
            else:
                # Features without age curves keep original thresholds
                adjusted[emotion]["rules"].append(rule)
                continue
            
            # Interpolate min/max for this age
            adjusted_min = interpolate_threshold(min_key, age_days)
            adjusted_max = interpolate_threshold(max_key, age_days)
            
            # If no anchor points found, use original
            if adjusted_min == 0.0 and adjusted_max == 0.0:
                adjusted[emotion]["rules"].append(rule)
            else:
                adjusted_rule = {
                    "feature": feature,
                    "min": adjusted_min if adjusted_min > 0 else rule.get("min"),
                    "max": adjusted_max if adjusted_max > 0 else rule.get("max"),
                    "weight": rule["weight"],
                }
                adjusted[emotion]["rules"].append(adjusted_rule)
    
    return adjusted


EMOTION_PROFILES_0_3M = {
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
    },
    "tired": {
        "prior": 0.06,
        "rules": [
            {"feature": "f0", "min": 210.0, "max": 430.0, "weight": 0.22},
            {"feature": "f0_instability", "min": 0.0, "max": 0.10, "weight": 0.20},
            {"feature": "rms_mean", "min": 0.010, "max": 0.075, "weight": 0.25},
            {"feature": "zcr", "min": 0.0, "max": 0.030, "weight": 0.16},
            {"feature": "duration_s", "min": 2.4, "max": 8.0, "weight": 0.10},
            {"feature": "voiced_fraction", "min": 0.10, "max": 0.65, "weight": 0.10},
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
            {"feature": "f0", "min": 560.0, "max": 1100.0, "weight": 0.22},
            {"feature": "rms_mean", "min": 0.13, "max": 0.45, "weight": 0.26},
            {"feature": "voiced_fraction", "min": 0.60, "max": 1.00, "weight": 0.14},
            {"feature": "spectral_centroid", "min": 2400.0, "max": 5200.0, "weight": 0.12},
            {"feature": "f0_instability", "min": 0.22, "max": 0.55, "weight": 0.10},
            {"feature": "duration_s", "min": 1.5, "max": 8.0, "weight": 0.08},
            {"feature": "energy_var", "min": 0.0, "max": 0.18, "weight": 0.08},
        ],
    },
    # Maps old "closeness" pattern to current "content" taxonomy.
    "content": {
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


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _extract_scoring_features(features: Dict[str, Any]) -> Dict[str, float]:
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


def _soft_range_match(
    value: float,
    min_v: Optional[float],
    max_v: Optional[float],
    tol_ratio: float = 0.20,
) -> float:
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
    return _soft_range_match(
        value=values[feature],
        min_v=cond.get("min"),
        max_v=cond.get("max"),
        tol_ratio=_to_float(cond.get("tol_ratio", 0.20), 0.20),
    )


def _score_profiles(
    values: Dict[str, float],
    profiles: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, float], Dict[str, List[Dict[str, Any]]]]:
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
                feat = str(rule.get("feature", "unknown"))
                triggers.append(
                    {
                        "rule": f"{feat}:{rule.get('min', '-inf')}..{rule.get('max', '+inf')}",
                        "gain": round(gain, 3),
                        "value": round(values.get(feat, 0.0), 4),
                    }
                )

        scores[emotion] = max(0.0, score)
        triggers.sort(key=lambda x: x.get("gain", 0.0), reverse=True)
        trigger_map[emotion] = triggers[:3]

    return scores, trigger_map


def analyze_cry_rules(features: Dict[str, Any], age_days: int = 45) -> Dict[str, Any]:
    """
    Return a rule-based cry result with normalized emotion scores.
    
    Args:
        features: Acoustic features dict
        age_days: Baby's age in days (default 45 for backward compatibility)
    
    Returns:
        Dict with emotion scores and debug info
    """
    values = _extract_scoring_features(features or {})
    profiles = get_age_adjusted_profiles(age_days)
    raw_scores, triggers = _score_profiles(values, profiles)

    total = sum(max(v, 0.0) for v in raw_scores.values())
    if total <= 1e-9:
        # No useful signal: weakly prefer discomfort instead of hard lock.
        probs = {k: (0.1 / 6.0) for k in raw_scores.keys()}
        probs["discomfort"] = 0.9
    else:
        probs = {k: max(v, 0.0) / total for k, v in raw_scores.items()}

    ranked = sorted(probs.items(), key=lambda x: x[1], reverse=True)
    primary_key, primary_score = ranked[0]

    top_emotions = [
        {"key": k, "score": round(float(v), 3)}
        for k, v in ranked[:3]
        if v > 0.01
    ]

    return {
        "primary_emotion": primary_key,
        "confidence": round(float(primary_score), 3),
        "emotion_probabilities": {k: round(float(v), 3) for k, v in probs.items()},
        "top_emotions": top_emotions,
        "model_version": "rule_based_basic",
        "using_model": True,  # Treat as a valid model output for downstream display.
        "debug_trace": {
            "feature_snapshot": {
                "f0": round(values["f0"], 2),
                "rms_mean": round(values["rms_mean"], 5),
                "energy_var": round(values["energy_var"], 3),
                "zcr": round(values["zcr"], 4),
                "duration_s": round(values["duration_s"], 2),
            },
            "top_feature_triggers": {
                emo: triggers.get(emo, []) for emo, _ in ranked[:3]
            },
        },
    }
