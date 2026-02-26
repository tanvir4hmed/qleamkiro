"""
Qleam — Language Analysis Module (Phase 7)

Pure acoustic-proxy functions for LINGUISTIC-mode sessions.
All inputs are existing rich_features fields — no new audio processing required.
"""
from typing import Dict


def estimate_mlu(rich_features: Dict) -> float:
    """
    Estimate Mean Length of Utterance (MLU) from acoustic proxies.

    Uses syllable_rate and pause_ratio to approximate utterance segmentation.
    pause_ratio drives utterance boundaries: higher pause → more utterances → lower MLU.

    Returns float clamped to [1.0, 6.0]. Defaults to 1.5 when data is absent.
    """
    syllable_rate = float(rich_features.get("syllable_rate", 0.0))
    pause_ratio = float(rich_features.get("pause_ratio", 0.5))

    if syllable_rate <= 0.0:
        return 1.5

    # Utterances per second: higher pause → more utterance boundaries
    utterances_per_sec = syllable_rate / (3.0 + pause_ratio * 2.0)
    if utterances_per_sec <= 0.0:
        return 1.5

    mlu = syllable_rate / utterances_per_sec
    return round(min(6.0, max(1.0, mlu)), 3)


def estimate_vocabulary_diversity(rich_features: Dict, known_concepts: int = 0) -> float:
    """
    Estimate vocabulary diversity from spectral entropy and confirmed concept count.

    spectral_entropy (tonal variety proxy) provides acoustic base signal.
    known_concepts from the concept graph boosts the estimate with confirmed data.

    Returns float [0, 1].
    """
    spectral_entropy = float(rich_features.get("spectral_entropy", 0.0))
    base = min(1.0, spectral_entropy / 10.0)
    boost = min(0.3, known_concepts * 0.015)
    return round(min(1.0, base + boost), 4)


def classify_pragmatic_type(rich_features: Dict) -> str:
    """
    Classify the pragmatic intent of a LINGUISTIC utterance from pitch contour.

    Rules (in priority order):
        question     — terminal rise: f0_max > f0_mean * 1.4
        exclamation  — wide range + fast: f0_range > 200 and syllable_rate > 5.0
        request      — moderate range + slower: f0_range > 80 and syllable_rate <= 5.0
        declaration  — fallback

    Returns one of: "declaration" | "request" | "question" | "exclamation"
    """
    f0_mean = float(rich_features.get("f0_mean", 0.0))
    f0_max = float(rich_features.get("f0_max", 0.0))
    f0_range = float(rich_features.get("f0_range", 0.0))
    syllable_rate = float(rich_features.get("syllable_rate", 0.0))

    if f0_mean > 0 and f0_max > f0_mean * 1.4:
        return "question"
    if f0_range > 200 and syllable_rate > 5.0:
        return "exclamation"
    if f0_range > 80 and syllable_rate <= 5.0:
        return "request"
    return "declaration"


def score_fluency(rich_features: Dict) -> float:
    """
    Score speech fluency from pause ratio and HNR (harmonics-to-noise ratio).

    Formula: (1 - pause_ratio) * (0.6 + 0.4 * voice_clarity)
    voice_clarity = clamp((hnr_db - 3) / 15, 0, 1)

    Returns float [0, 1].
    """
    pause_ratio = float(rich_features.get("pause_ratio", 0.5))
    hnr_db = float(rich_features.get("hnr_db", 0.0))

    voice_clarity = max(0.0, min(1.0, (hnr_db - 3.0) / 15.0))
    fluency = (1.0 - pause_ratio) * (0.6 + 0.4 * voice_clarity)
    return round(max(0.0, min(1.0, fluency)), 4)
