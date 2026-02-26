"""
Qleam - Intent Taxonomy (v2)

Central intent key definitions and normalization helpers.
"""
from typing import Dict, Iterable, Optional, Tuple

# Baby intent classes used for inference + parent feedback.
CORE_INTENT_KEYS: Tuple[str, ...] = (
    "hunger",
    "fatigue",
    "pain",
    "discomfort",
    "closeness",
    "frustration",
    "happy",
    "exploration",
    "distress_unknown",
)

# Technical class is not a normal baby intent; used for rejection sessions.
TECHNICAL_INTENT_KEY: str = "non_baby_spoof_noise"

ALL_INTENT_KEYS: Tuple[str, ...] = CORE_INTENT_KEYS + (TECHNICAL_INTENT_KEY,)

# Legacy and synonym mapping (for backward compatibility and flexible feedback input).
_ALIASES: Dict[str, str] = {
    # Legacy keys
    "connection": "closeness",
    "overstimulation": "frustration",
    "unknown": "distress_unknown",
    # Common parent wording
    "sleep": "fatigue",
    "sleepy": "fatigue",
    "tired": "fatigue",
    "angry": "frustration",
    "frustrated": "frustration",
    "mad": "frustration",
    "need_cuddle": "closeness",
    "cuddle": "closeness",
    "comfort": "closeness",
    "need_comfort": "closeness",
    "happy_content": "happy",
    "content": "happy",
    "neutral": "exploration",
    "coos": "exploration",
    "distress": "distress_unknown",
    "fallback": "distress_unknown",
    # Technical/non-baby class
    "non_baby": TECHNICAL_INTENT_KEY,
    "spoof": TECHNICAL_INTENT_KEY,
    "noise": TECHNICAL_INTENT_KEY,
    "technical": TECHNICAL_INTENT_KEY,
}


def canonical_intent_key(
    key: Optional[str],
    allow_technical: bool = True,
) -> Optional[str]:
    """
    Normalize arbitrary intent text to canonical key.

    Returns None for empty/unknown keys.
    """
    if not key:
        return None
    norm = str(key).strip().lower().replace("-", "_").replace(" ", "_")
    norm = _ALIASES.get(norm, norm)
    if norm in CORE_INTENT_KEYS:
        return norm
    if allow_technical and norm == TECHNICAL_INTENT_KEY:
        return norm
    return None


def canonical_intent_keys(include_technical: bool = False) -> Tuple[str, ...]:
    return ALL_INTENT_KEYS if include_technical else CORE_INTENT_KEYS


def normalize_intent_distribution(
    dist: Optional[Dict[str, float]],
    include_technical: bool = False,
    fill_missing: bool = True,
) -> Dict[str, float]:
    """
    Canonicalize, clamp, and normalize a raw intent distribution.
    """
    keys: Tuple[str, ...] = canonical_intent_keys(include_technical=include_technical)
    out: Dict[str, float] = {k: 0.0 for k in keys}

    if isinstance(dist, dict):
        for raw_k, raw_v in dist.items():
            k = canonical_intent_key(str(raw_k), allow_technical=include_technical)
            if not k:
                continue
            try:
                out[k] += max(0.0, float(raw_v))
            except Exception:
                continue

    total = sum(out.values())
    if total > 0:
        out = {k: (v / total) for k, v in out.items()}
    elif not fill_missing:
        return {}
    else:
        uniform = 1.0 / max(len(keys), 1)
        out = {k: uniform for k in keys}

    if not fill_missing:
        return {k: v for k, v in out.items() if v > 0}
    return out


def map_legacy_intent_keys(keys: Iterable[str]) -> Tuple[str, ...]:
    """
    Convert a list of keys to canonical form (deduplicated, ordered).
    """
    seen = set()
    result = []
    for k in keys:
        c = canonical_intent_key(k, allow_technical=True)
        if c and c not in seen:
            seen.add(c)
            result.append(c)
    return tuple(result)
