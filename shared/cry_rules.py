"""
Rule-based cry emotion scoring for Basic mode / model fallback.

This mirrors the older handmade approach: score acoustic features against
emotion profiles, then normalize to a probability-like distribution.
"""
from typing import Any, Dict, List, Optional, Tuple


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


def analyze_cry_rules(features: Dict[str, Any]) -> Dict[str, Any]:
    """Return a rule-based cry result with normalized emotion scores."""
    values = _extract_scoring_features(features or {})
    raw_scores, triggers = _score_profiles(values, EMOTION_PROFILES_0_3M)

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
