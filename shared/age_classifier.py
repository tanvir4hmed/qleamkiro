"""
Qleam — Probabilistic Speaker / Age Classifier (Phase 4)

Replaces hard F0 thresholds with a multi-layer architecture:

  Layer 1 — Voice Type Detection
      Classifies audio as: cry_like | structured_speech | sustained_tone | noise
      Age classification only proceeds for cry_like / structured_speech.
      sustained_tone (humming, falsetto) is routed to UNKNOWN in ambiguous zones.

  Layer 2 — Diagonal Gaussian Scoring
      Computes weighted log-likelihood of each class against literature-derived
      prior distributions for 7 key acoustic features.  Returns full probability
      distribution (softmax over log-likelihoods).

  Layer 3 — Conservative Adult Gate
      ADULT label requires ALL conditions to hold simultaneously:
        • f0_mean < 180 Hz
        • vtl_cm > 13 cm  (if VTL is available)
        • hnr_db  > 14 dB
        • jitter_percent < 2.5 %
        • cry_fraction < 0.02
        • voice_type ∈ {structured_speech, sustained_tone}
      If gate fails → adult probability redistributed to child/toddler.

  Layer 4 — UNKNOWN class
      Returned when: voice_type=noise, max_probability < 0.35,
      or sustained_tone with adult-range F0 and insufficient evidence.

No model training required.  Uses features already produced by
  • rich_features.extract_rich_features()   (~65 features)
  • audio_utils.biological_validation()     (provides vtl_cm)

Privacy-first: no external API calls, runs entirely in Lambda.
"""
import logging
import math
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Class definitions
# ---------------------------------------------------------------------------

ALL_CLASSES = ["newborn", "infant", "toddler", "child", "adult_female", "adult_male"]
NON_ADULT_CLASSES = ["newborn", "infant", "toddler", "child"]
ADULT_CLASSES = ["adult_female", "adult_male"]

# ---------------------------------------------------------------------------
# Layer 2 — Literature-based Gaussian priors
#
# Each entry is (mean, std) for a feature within a speaker class.
#
# Sources: aggregated acoustic phonetics / speech science literature on
#   vocal tract development, infant cry acoustics, and adult voice quality.
#   Key references include Peterson & Barney (1952), Fitch & Giedd (1999),
#   Robb & Saxman (1985), Titze (1994), and infant-cry corpus studies.
# ---------------------------------------------------------------------------

_PRIORS: Dict[str, Dict[str, Tuple[float, float]]] = {
    "newborn": {
        # F0 during newborn cry: 300–600+ Hz, median ~450 Hz
        "f0_mean":           (450.0,  90.0),
        # Very high jitter — F0 instability in cry
        "jitter_percent":    (15.0,   6.0),
        # High shimmer — amplitude perturbation
        "shimmer_db":        (5.5,    2.0),
        # Low HNR — lots of turbulent airflow in cry
        "hnr_db":            (5.0,    3.5),
        # Bright spectrum due to high harmonics in cry
        "spectral_centroid": (2800.0, 700.0),
        # Most voiced frames are cry
        "cry_fraction":      (0.65,   0.22),
        # Newborns produce sustained cries, not syllables → low rate
        "syllable_rate":     (1.5,    1.0),
        # VTL: smallest human vocal tract
        "vtl_cm":            (7.5,    0.7),
    },
    "infant": {
        # Infant babbling / cooing / low cry: 280–450 Hz
        "f0_mean":           (375.0,  65.0),
        "jitter_percent":    (10.0,   5.0),
        "shimmer_db":        (4.0,    1.5),
        "hnr_db":            (8.0,    4.0),
        "spectral_centroid": (2400.0, 550.0),
        "cry_fraction":      (0.25,   0.18),
        "syllable_rate":     (2.5,    1.2),
        "vtl_cm":            (9.0,    0.8),
    },
    "toddler": {
        # Toddler speech: ~240–320 Hz
        "f0_mean":           (290.0,  45.0),
        "jitter_percent":    (6.0,    3.0),
        "shimmer_db":        (3.0,    1.2),
        "hnr_db":            (12.0,   4.0),
        "spectral_centroid": (2100.0, 450.0),
        "cry_fraction":      (0.08,   0.08),
        "syllable_rate":     (3.5,    1.2),
        "vtl_cm":            (10.5,   0.8),
    },
    "child": {
        # Child 2–5 yrs: ~200–280 Hz
        "f0_mean":           (240.0,  35.0),
        "jitter_percent":    (3.5,    1.8),
        "shimmer_db":        (2.0,    1.0),
        "hnr_db":            (16.0,   4.5),
        "spectral_centroid": (1900.0, 400.0),
        "cry_fraction":      (0.02,   0.04),
        "syllable_rate":     (4.5,    1.3),
        "vtl_cm":            (12.0,   1.0),
    },
    "adult_female": {
        # Adult female: ~165–255 Hz
        "f0_mean":           (195.0,  35.0),
        "jitter_percent":    (1.0,    0.6),
        "shimmer_db":        (0.8,    0.5),
        "hnr_db":            (22.0,   5.0),
        "spectral_centroid": (1500.0, 350.0),
        "cry_fraction":      (0.005,  0.02),
        "syllable_rate":     (5.5,    1.5),
        "vtl_cm":            (15.5,   1.5),
    },
    "adult_male": {
        # Adult male: ~85–180 Hz
        "f0_mean":           (120.0,  28.0),
        "jitter_percent":    (0.8,    0.4),
        "shimmer_db":        (0.6,    0.4),
        "hnr_db":            (25.0,   5.0),
        "spectral_centroid": (1200.0, 300.0),
        "cry_fraction":      (0.002,  0.01),
        "syllable_rate":     (5.0,    1.5),
        "vtl_cm":            (17.0,   1.2),
    },
}

# Feature weights for weighted log-likelihood sum.
# Higher weight → feature has more influence on classification.
_FEATURE_WEIGHTS: Dict[str, float] = {
    "f0_mean":           3.5,   # Strongest single discriminator
    "vtl_cm":            3.0,   # Physical vocal-tract constraint — highly reliable
    "cry_fraction":      2.0,   # Strong evidence for newborn / infant
    "jitter_percent":    2.0,   # Voice stability — very different across ages
    "hnr_db":            2.0,   # Harmonic clarity — matures with age
    "spectral_centroid": 1.5,   # Spectral brightness — age-correlated
    "shimmer_db":        1.5,   # Amplitude perturbation
    "syllable_rate":     1.0,   # Speech rate proxy (less reliable alone)
}


# ---------------------------------------------------------------------------
# Layer 1 — Voice Type Detection
# ---------------------------------------------------------------------------

def detect_voice_type(rich_features: Dict[str, float]) -> Dict:
    """
    Classify audio content type before running the age classifier.

    This prevents adult humming / falsetto from being misclassified as baby
    by flagging voice segments that are sustained tones (low F0 variance,
    very regular energy, low syllable rate).

    Returns:
        {
            "voice_type":  "cry_like" | "structured_speech" | "sustained_tone" | "noise",
            "confidence":  float,
        }
    """
    f0_mean              = rich_features.get("f0_mean",           0.0)
    f0_std               = rich_features.get("f0_std",            0.0)
    jitter_percent       = rich_features.get("jitter_percent",    0.0)
    cry_fraction         = rich_features.get("cry_fraction",      0.0)
    rms_mean             = rich_features.get("rms_mean",          0.0)
    rms_std              = rich_features.get("rms_std",           0.0)
    hnr_db               = rich_features.get("hnr_db",            0.0)
    f0_voiced_fraction   = rich_features.get("f0_voiced_fraction", 0.0)
    syllable_rate        = rich_features.get("syllable_rate",     0.0)

    # --- Noise: very few voiced frames, very low energy, or no F0 ---
    energy_ratio = rms_std / (rms_mean + 1e-8)
    if (
        f0_voiced_fraction < 0.15
        or hnr_db < 2.0
        or (rms_mean < 0.001 and f0_mean == 0.0)
    ):
        return {"voice_type": "noise", "confidence": 0.90}

    # --- Cry-like: high F0 + high instability, or high cry fraction ---
    cry_evidence = 0
    if cry_fraction > 0.25:
        cry_evidence += 3
    elif cry_fraction > 0.12:
        cry_evidence += 1
    if f0_mean > 300 and f0_std > 55:
        cry_evidence += 2
    if jitter_percent > 8.0:
        cry_evidence += 2
    if f0_mean > 350 and jitter_percent > 5.0:
        cry_evidence += 1
    if energy_ratio > 0.5 and f0_mean > 280:
        cry_evidence += 1

    if cry_evidence >= 3:
        conf = min(0.96, 0.50 + cry_evidence * 0.08)
        return {"voice_type": "cry_like", "confidence": round(conf, 3)}

    # --- Sustained tone: stable F0, very regular energy, low syllable rate ---
    # Captures adult humming, singing, held vowels.
    # Criterion: pitch must be very steady AND output non-syllabic.
    is_sustained = (
        f0_std < 18.0           # Stable pitch
        and jitter_percent < 1.5   # Very low cycle-to-cycle perturbation
        and syllable_rate < 1.5    # Not producing syllabic speech
        and cry_fraction < 0.08    # Not crying
        and f0_voiced_fraction > 0.40  # Mostly voiced (not silence)
    )
    if is_sustained:
        return {"voice_type": "sustained_tone", "confidence": 0.80}

    # --- Default: structured speech ---
    return {"voice_type": "structured_speech", "confidence": 0.75}


# ---------------------------------------------------------------------------
# Layer 2 — Gaussian Scoring
# ---------------------------------------------------------------------------

def _gaussian_log_prob(x: float, mu: float, sigma: float) -> float:
    """Unnormalized Gaussian log-probability at x given (mu, sigma)."""
    if sigma <= 0:
        return -1e6
    return -0.5 * ((x - mu) / sigma) ** 2


def compute_class_log_likelihoods(
    rich_features: Dict[str, float],
    vtl_cm: float = 0.0,
) -> Dict[str, float]:
    """
    Compute weighted diagonal Gaussian log-likelihoods for every class.

    Only features with a non-zero observed value contribute (avoids punishing
    missing/failed extractions).  VTL is treated as an extra feature when
    it is available (vtl_cm > 0).

    Returns:
        {class_name: weighted_log_likelihood_score}  — higher is more probable.
    """
    fmap: Dict[str, float] = {
        "f0_mean":           rich_features.get("f0_mean",           0.0),
        "jitter_percent":    rich_features.get("jitter_percent",    0.0),
        "shimmer_db":        rich_features.get("shimmer_db",        0.0),
        "hnr_db":            rich_features.get("hnr_db",            0.0),
        "spectral_centroid": rich_features.get("spectral_centroid", 0.0),
        "cry_fraction":      rich_features.get("cry_fraction",      0.0),
        "syllable_rate":     rich_features.get("syllable_rate",     0.0),
    }
    if vtl_cm > 0.0:
        fmap["vtl_cm"] = vtl_cm

    # Features that may legitimately be exactly zero
    _ALLOW_ZERO = {"cry_fraction", "shimmer_db"}

    log_likes: Dict[str, float] = {}
    for cls in ALL_CLASSES:
        priors = _PRIORS[cls]
        score = 0.0
        weight_sum = 0.0

        for feat, val in fmap.items():
            if val == 0.0 and feat not in _ALLOW_ZERO:
                continue  # Skip — missing / failed extraction
            if feat not in priors:
                continue

            mu, sigma = priors[feat]
            w = _FEATURE_WEIGHTS.get(feat, 1.0)
            score += w * _gaussian_log_prob(val, mu, sigma)
            weight_sum += w

        log_likes[cls] = score / max(weight_sum, 1.0)

    return log_likes


def _softmax(log_scores: Dict[str, float]) -> Dict[str, float]:
    """Normalize log-likelihood scores to a probability distribution."""
    vals = np.array(list(log_scores.values()), dtype=float)
    vals -= np.max(vals)          # Numeric stability shift
    exp_vals = np.exp(vals)
    total = float(np.sum(exp_vals))

    if total <= 0:
        n = len(log_scores)
        return {k: round(1.0 / n, 4) for k in log_scores}

    return {k: round(float(ev / total), 4) for k, ev in zip(log_scores, exp_vals)}


# ---------------------------------------------------------------------------
# Layer 3 — Conservative Adult Gate
# ---------------------------------------------------------------------------

def apply_conservative_adult_gate(
    probs: Dict[str, float],
    rich_features: Dict[str, float],
    vtl_cm: float,
    voice_type: str,
) -> Dict[str, float]:
    """
    Only confirm ADULT classification if ALL gate conditions hold.

    If the gate fails but Gaussian scored adult highest → redistribute adult
    probability into child (70 %) and toddler (30 %) — conservative fallback.

    Gate conditions (ALL required):
      1. f0_mean       < 180 Hz  OR  (overlap-zone adult cues)
      2. vtl_cm        > 13.0 cm      — adult vocal tract (when VTL available)
      3. hnr_db        > 14 dB        — clear harmonic structure
      4. jitter_percent < 2.5 %       — stable pitch
      5. cry_fraction  < 0.02         — not crying
      6. voice_type ∈ {structured_speech, sustained_tone}
      Overlap-zone adult cues (180–260 Hz):
        vtl_cm > 14.5 cm, hnr_db > 18 dB, jitter_percent < 1.8, shimmer_db < 1.6
    """
    adult_prob = probs.get("adult_female", 0.0) + probs.get("adult_male", 0.0)
    if adult_prob < 0.25:
        return probs  # Not a close call — gate not needed

    f0_mean       = rich_features.get("f0_mean",        0.0)
    jitter        = rich_features.get("jitter_percent", 0.0)
    shimmer_db    = rich_features.get("shimmer_db",     0.0)
    hnr           = rich_features.get("hnr_db",         0.0)
    cry           = rich_features.get("cry_fraction",   0.0)

    overlap_adult = False
    if 180.0 <= f0_mean <= 260.0:
        overlap_adult = (
            (vtl_cm > 14.5) if vtl_cm > 0.0 else False
        ) and (hnr > 18.0) and (jitter < 1.8) and (shimmer_db < 1.6)

    gate: list = [
        (f0_mean < 180.0) or overlap_adult,
        (vtl_cm > 13.0) if vtl_cm > 0.0 else True,   # Pass when VTL unavailable
        hnr > 14.0,
        jitter < 2.5,
        cry < 0.02,
        voice_type in ("structured_speech", "sustained_tone"),
    ]

    if all(gate):
        return probs  # Adult confirmed

    # Gate failed → redistribute adult probability
    adjusted = dict(probs)
    adult_total = adjusted.get("adult_female", 0.0) + adjusted.get("adult_male", 0.0)
    adjusted["adult_female"] = 0.0
    adjusted["adult_male"]   = 0.0
    adjusted["child"]   = adjusted.get("child",   0.0) + adult_total * 0.70
    adjusted["toddler"] = adjusted.get("toddler", 0.0) + adult_total * 0.30

    total = sum(adjusted.values())
    if total > 0:
        adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}

    logger.debug(
        f"Adult gate failed: f0={f0_mean:.0f}Hz vtl={vtl_cm:.1f}cm "
        f"hnr={hnr:.1f}dB jitter={jitter:.1f}% cry={cry:.3f} "
        f"vtype={voice_type} → redistributed to child/toddler"
    )
    return adjusted


# ---------------------------------------------------------------------------
# Layer 4 — Final class determination + UNKNOWN
# ---------------------------------------------------------------------------

def _determine_final_class(
    probs: Dict[str, float],
    voice_type: str,
    rich_features: Dict[str, float],
    vtl_cm: float,
) -> Tuple[str, float, bool]:
    """
    Pick the final class from probability distribution.

    Returns:
        (final_class, confidence, is_unknown)
    """
    # Noise → always unknown
    if voice_type == "noise":
        return "unknown", 0.0, True

    # Sustained tone in adult-overlap F0 range → uncertain unless strong adult cues
    f0_mean = rich_features.get("f0_mean", 0.0)
    if voice_type == "sustained_tone" and f0_mean < 220.0:
        jitter = rich_features.get("jitter_percent", 0.0)
        shimmer_db = rich_features.get("shimmer_db", 0.0)
        hnr = rich_features.get("hnr_db", 0.0)
        strong_adult = (
            (vtl_cm > 14.5) if vtl_cm > 0.0 else False
        ) and (hnr > 18.0) and (jitter < 1.8) and (shimmer_db < 1.6)

        if not strong_adult:
            adult_prob = probs.get("adult_female", 0.0) + probs.get("adult_male", 0.0)
            non_adult  = 1.0 - adult_prob
            if adult_prob > 0.30 and non_adult < 0.60:
                return "unknown", max(adult_prob, non_adult), True

    # Low-confidence or nearly-tied distributions → unknown
    sorted_probs = sorted(probs.values(), reverse=True)
    max_prob   = sorted_probs[0] if sorted_probs else 0.0
    second_prob = sorted_probs[1] if len(sorted_probs) > 1 else 0.0
    margin = max_prob - second_prob
    max_class = max(probs, key=probs.get)

    if max_prob < 0.35 or margin < 0.08:
        return "unknown", max_prob, True

    return max_class, max_prob, False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_probabilistic(
    rich_features: Dict[str, float],
    bio_result: Optional[Dict] = None,
) -> Dict:
    """
    Full probabilistic speaker / age classification.

    Uses the ~65 rich acoustic features (from extract_rich_features) and the
    VTL estimate (from biological_validation) to produce a stable,
    probability-aware classification without hard F0 thresholds.

    Pipeline:
      1. Detect voice type (cry_like | structured_speech | sustained_tone | noise)
      2. Gaussian log-likelihoods from literature priors  →  probability distribution
      3. Conservative adult gate  →  adjusted probabilities
      4. Final class with UNKNOWN fallback

    Args:
        rich_features:  Output of extract_rich_features()  (~65 keys)
        bio_result:     Output of biological_validation()  — used for vtl_cm

    Returns:
        {
            "final_class":              str,    # newborn | infant | toddler | child |
                                                #   adult_female | adult_male | unknown
            "confidence":               float,  # probability of top class [0–1]
            "is_baby":                  bool,   # newborn / infant / toddler
            "is_child":                 bool,   # child (2–5 yr)
            "is_adult":                 bool,   # adult_female / adult_male
            "is_unknown":               bool,
            "voice_type":               str,    # content type label
            "voice_type_confidence":    float,
            "probability_distribution": dict,   # full {class: prob} map
            "vtl_cm_used":              float,
        }
    """
    # Graceful degradation when rich features are unavailable
    if not rich_features or not any(rich_features.values()):
        logger.warning("age_classifier: rich_features empty — returning unknown")
        return _unknown_result(vtl_cm=0.0, voice_type="noise", voice_type_conf=0.0)

    vtl_cm = float((bio_result or {}).get("vtl_cm", 0.0))

    # Step 1 — Voice type
    vtype_result     = detect_voice_type(rich_features)
    voice_type       = vtype_result["voice_type"]
    voice_type_conf  = vtype_result["confidence"]

    # Step 2 — Gaussian scoring
    log_likes = compute_class_log_likelihoods(rich_features, vtl_cm)

    # Step 3 — Softmax
    probs = _softmax(log_likes)

    # Step 4 — Conservative adult gate
    probs = apply_conservative_adult_gate(probs, rich_features, vtl_cm, voice_type)

    # Step 5 — Final class
    final_class, confidence, is_unknown = _determine_final_class(
        probs, voice_type, rich_features, vtl_cm
    )

    is_baby  = final_class in ("newborn", "infant", "toddler")
    is_child = final_class == "child"
    is_adult = final_class in ("adult_female", "adult_male")

    logger.info(
        f"age_classifier: voice_type={voice_type} final={final_class} "
        f"conf={confidence:.3f} probs={probs} vtl={vtl_cm:.1f}cm"
    )

    return {
        "final_class":              final_class,
        "confidence":               round(confidence, 4),
        "is_baby":                  is_baby,
        "is_child":                 is_child,
        "is_adult":                 is_adult,
        "is_unknown":               is_unknown,
        "voice_type":               voice_type,
        "voice_type_confidence":    round(voice_type_conf, 4),
        "probability_distribution": probs,
        "vtl_cm_used":              round(vtl_cm, 2),
    }


def age_class_to_stage_hint(
    age_class_result: Dict,
    age_days: Optional[int] = None,
) -> Dict:
    """
    Convert probabilistic classifier output to a developmental stage hint.

    Used in feature_extraction to provide a richer audio-derived stage estimate
    that complements (and can override) the VTL/F0-only hint from
    audio_stage_hint_from_bio().

    When age_days is provided, it disambiguates within broad acoustic classes:
      - "infant" (3-12m acoustically) → EARLY_VOCAL or CANONICAL_BABBLE
      - "child"  (2-5yr acoustically) → FIRST_WORDS, WORD_COMBINATIONS, or EARLY_SENTENCES

    Returns:
        {"stage": str | None, "mode": str | None, "confidence": float}
    """
    cls  = age_class_result.get("final_class", "unknown")
    conf = float(age_class_result.get("confidence", 0.0))

    # For adult/unknown classes, no stage hint
    if cls in ("adult_female", "adult_male", "unknown"):
        return {"stage": None, "mode": None, "confidence": 0.0}

    # Use age_days to pick the most accurate stage within the acoustic class
    if age_days is not None and age_days >= 0:
        stage, mode, base_conf = _stage_from_class_and_age(cls, age_days)
    else:
        # Fallback: pure acoustic class mapping (no age info)
        _MAP = {
            "newborn":  ("NEWBORN",      "PRE_LINGUISTIC",  0.70),
            "infant":   ("EARLY_VOCAL",  "PRE_LINGUISTIC",  0.63),
            "toddler":  ("PROTO_WORDS",  "TRANSITION",      0.60),
            "child":    ("FIRST_WORDS",  "LINGUISTIC",      0.55),
        }
        stage, mode, base_conf = _MAP.get(cls, (None, None, 0.0))

    if stage is None:
        return {"stage": None, "mode": None, "confidence": 0.0}

    # Scale base confidence by the classifier's own confidence
    final_conf = round(base_conf * conf, 3)
    return {"stage": stage, "mode": mode, "confidence": final_conf}


def _stage_from_class_and_age(
    cls: str, age_days: int
) -> Tuple[str, str, float]:
    """
    Pick developmental stage using both acoustic class and registered age.

    The acoustic classifier gives broad buckets (newborn/infant/toddler/child).
    age_days from the child profile gives the fine-grained stage within each
    bucket, aligning with the 7-stage DEVELOPMENTAL_STAGE_MAP from constants.

    Returns (stage, mode, base_confidence).
    """
    if cls == "newborn":
        return ("NEWBORN", "PRE_LINGUISTIC", 0.70)

    if cls == "infant":
        # infant acoustics span 3-12 months
        # EARLY_VOCAL: 91-180 days, CANONICAL_BABBLE: 181-270 days
        if age_days <= 180:
            return ("EARLY_VOCAL", "PRE_LINGUISTIC", 0.65)
        else:
            return ("CANONICAL_BABBLE", "PRE_LINGUISTIC", 0.63)

    if cls == "toddler":
        # toddler acoustics span ~9-24 months
        # PROTO_WORDS: 271-365 days
        return ("PROTO_WORDS", "TRANSITION", 0.60)

    if cls == "child":
        # child acoustics span 2-5 years
        # FIRST_WORDS: 366-548 days, WORD_COMBINATIONS: 549-730 days,
        # EARLY_SENTENCES: 731+ days
        if age_days <= 548:
            return ("FIRST_WORDS", "LINGUISTIC", 0.58)
        elif age_days <= 730:
            return ("WORD_COMBINATIONS", "LINGUISTIC", 0.55)
        else:
            return ("EARLY_SENTENCES", "LINGUISTIC", 0.52)

    return (None, None, 0.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _unknown_result(vtl_cm: float, voice_type: str, voice_type_conf: float) -> Dict:
    """Build a fully-populated UNKNOWN result."""
    zero_probs = {cls: round(1.0 / len(ALL_CLASSES), 4) for cls in ALL_CLASSES}
    return {
        "final_class":              "unknown",
        "confidence":               0.0,
        "is_baby":                  False,
        "is_child":                 False,
        "is_adult":                 False,
        "is_unknown":               True,
        "voice_type":               voice_type,
        "voice_type_confidence":    round(voice_type_conf, 4),
        "probability_distribution": zero_probs,
        "vtl_cm_used":              round(vtl_cm, 2),
    }
