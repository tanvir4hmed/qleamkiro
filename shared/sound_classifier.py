"""
Qleam — Sound Classifier
Classifies audio segments into: SPEECH, CRY, LAUGH, SILENCE, NOISE
Uses librosa-based acoustic features for fast, accurate routing.

This is the first gate in the pipeline — determines which analysis
path to follow (word analysis, cry emotion, laugh detection, etc.)
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports
_librosa = None


def _get_librosa():
    global _librosa
    if _librosa is None:
        import librosa
        _librosa = librosa
    return _librosa


# ---------------------------------------------------------------------------
# Sound type constants
# ---------------------------------------------------------------------------
SOUND_SPEECH = "speech"
SOUND_CRY = "cry"
SOUND_LAUGH = "laugh"
SOUND_SILENCE = "silence"
SOUND_NOISE = "noise"
SOUND_MIXED = "mixed"

# ---------------------------------------------------------------------------
# Classification thresholds
# ---------------------------------------------------------------------------
SILENCE_RMS_THRESHOLD = 0.005          # Below this = silence
SILENCE_ENERGY_RATIO = 0.90            # >90% of frames below threshold = silence
MIN_VOICED_FRACTION = 0.05             # Minimum voiced energy for non-silence

# Cry characteristics
CRY_F0_MIN_HZ = 250.0                 # Baby cry F0 typically 300-600Hz
CRY_F0_MAX_HZ = 800.0
CRY_ENERGY_VAR_MIN = 0.25             # Cry has high energy variation
CRY_DURATION_MIN_S = 0.3              # Minimum cry segment duration
CRY_SPECTRAL_CENTROID_MIN = 1000.0    # Cry has high spectral centroid

# Laugh characteristics
LAUGH_ZCR_MIN = 0.03                  # Laugh has high zero-crossing rate
LAUGH_ENERGY_BURST_RATIO = 0.3        # Laugh has rhythmic energy bursts
LAUGH_F0_VAR_MIN = 0.08               # F0 variability in laughter

# Speech characteristics
SPEECH_SYLLABLE_RATE_MIN = 1.5        # Minimum syllable rate for speech
SPEECH_F0_STABILITY_MAX = 0.15        # Speech has more stable F0 than cry
SPEECH_PAUSE_RATIO_RANGE = (0.15, 0.65)  # Speech has natural pauses

# Mixed classification ambiguity threshold.
# Tuned from 0.10 -> 0.08 so "mixed" is assigned slightly less often while
# preserving ambiguity handling.
MIXED_AMBIGUITY_GAP = 0.08


def _compute_rms_profile(y: np.ndarray, sr: int, frame_ms: int = 25) -> np.ndarray:
    """Compute frame-level RMS energy profile."""
    frame_len = max(64, int(sr * frame_ms / 1000))
    hop = frame_len // 2
    n_frames = max(1, (len(y) - frame_len) // hop + 1)
    rms = np.zeros(n_frames)
    for i in range(n_frames):
        chunk = y[i * hop: i * hop + frame_len]
        if len(chunk) > 0:
            rms[i] = float(np.sqrt(np.mean(chunk ** 2)))
    return rms


def _compute_f0_profile(y: np.ndarray, sr: int) -> Tuple[float, float, float]:
    """
    Compute F0 statistics using librosa's pyin.
    Returns: (f0_mean, f0_std, voiced_fraction)
    """
    librosa = _get_librosa()
    try:
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=60, fmax=1000, sr=sr,
            frame_length=2048, hop_length=512
        )
        if f0 is None or len(f0) == 0:
            return 0.0, 0.0, 0.0

        voiced = f0[voiced_flag] if voiced_flag is not None else f0[~np.isnan(f0)]
        if len(voiced) == 0:
            return 0.0, 0.0, 0.0

        voiced_frac = len(voiced) / max(1, len(f0))
        return float(np.nanmean(voiced)), float(np.nanstd(voiced)), voiced_frac
    except Exception as e:
        logger.warning(f"F0 extraction failed: {e}")
        return 0.0, 0.0, 0.0


def _compute_zcr(y: np.ndarray) -> float:
    """Zero-crossing rate."""
    if len(y) < 3:
        return 0.0
    signs = np.sign(y)
    return float(np.sum(signs[:-1] != signs[1:])) / max(1, len(y))


def _compute_spectral_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """Compute spectral centroid, flatness, rolloff."""
    librosa = _get_librosa()
    try:
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)
        flatness = librosa.feature.spectral_flatness(y=y, hop_length=512)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr, hop_length=512)
        return {
            "centroid": float(np.mean(centroid)) if centroid.size > 0 else 0.0,
            "flatness": float(np.mean(flatness)) if flatness.size > 0 else 0.0,
            "rolloff": float(np.mean(rolloff)) if rolloff.size > 0 else 0.0,
        }
    except Exception:
        return {"centroid": 0.0, "flatness": 0.0, "rolloff": 0.0}


def _estimate_syllable_rate(y: np.ndarray, sr: int) -> float:
    """Estimate syllable rate from RMS energy peaks."""
    rms = _compute_rms_profile(y, sr, frame_ms=30)
    if len(rms) < 5:
        return 0.0

    # Smooth RMS
    kernel_size = min(5, len(rms))
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(rms, kernel, mode='same')

    # Find peaks (syllable nuclei)
    threshold = np.mean(smoothed) * 0.6
    peaks = 0
    above = False
    for val in smoothed:
        if val > threshold and not above:
            peaks += 1
            above = True
        elif val <= threshold:
            above = False

    duration_s = len(y) / max(sr, 1)
    if duration_s < 0.1:
        return 0.0
    return peaks / duration_s


def _detect_energy_bursts(rms: np.ndarray) -> float:
    """Detect rhythmic energy bursts (characteristic of laughter)."""
    if len(rms) < 10:
        return 0.0

    mean_rms = float(np.mean(rms))
    if mean_rms < 0.001:
        return 0.0

    # Count transitions above/below mean
    above = rms > mean_rms * 1.2
    transitions = int(np.sum(np.diff(above.astype(int)) != 0))

    # Normalize by duration
    burst_rate = transitions / max(1, len(rms))
    return min(1.0, burst_rate * 5.0)


def classify_sound(
    y: np.ndarray,
    sr: int,
    duration_s: Optional[float] = None,
    core_features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Classify audio into sound type with confidence scores.

    Args:
        y: Audio signal (mono, float32)
        sr: Sample rate
        duration_s: Duration in seconds (computed if not provided)
        core_features: Pre-computed features from core_features.compute_core_features().
                       If provided, avoids recomputing F0/RMS/spectral features.
    """
    if y is None or len(y) == 0:
        return {
            "primary_type": SOUND_SILENCE,
            "confidence": 1.0,
            "scores": {"speech": 0, "cry": 0, "laugh": 0, "silence": 1, "noise": 0},
            "features": {},
        }

    if duration_s is None:
        duration_s = len(y) / max(sr, 1)

    # Use pre-computed features if available, otherwise compute locally
    if core_features:
        rms = core_features["rms"]
        rms_mean = core_features["rms_mean"]
        rms_std = core_features["rms_std"]
        energy_var = core_features["energy_variability"]
        f0_mean = core_features["f0_mean"]
        f0_std = core_features["f0_std"]
        voiced_frac = core_features["voiced_fraction"]
        f0_instability = core_features["f0_instability"]
        zcr = core_features["zcr"]
        spectral = {
            "centroid": core_features["spectral_centroid"],
            "flatness": core_features["spectral_flatness"],
            "rolloff": core_features["spectral_rolloff"],
        }
        syllable_rate = core_features["syllable_rate"]
        energy_bursts = core_features["energy_burst_ratio"]
    else:
        rms = _compute_rms_profile(y, sr)
        rms_mean = float(np.mean(rms)) if len(rms) > 0 else 0.0
        rms_std = float(np.std(rms)) if len(rms) > 0 else 0.0
        energy_var = rms_std / (rms_mean + 1e-9)
        f0_mean, f0_std, voiced_frac = _compute_f0_profile(y, sr)
        f0_instability = f0_std / (f0_mean + 1e-9) if f0_mean > 0 else 0.0
        zcr = _compute_zcr(y)
        spectral = _compute_spectral_features(y, sr)
        syllable_rate = _estimate_syllable_rate(y, sr)
        energy_bursts = _detect_energy_bursts(rms)

    features = {
        "f0_mean": round(f0_mean, 2),
        "f0_std": round(f0_std, 2),
        "f0_instability": round(f0_instability, 4),
        "voiced_fraction": round(voiced_frac, 3),
        "zcr": round(zcr, 4),
        "rms_mean": round(rms_mean, 5),
        "rms_std": round(rms_std, 5),
        "energy_variability": round(energy_var, 3),
        "spectral_centroid": round(spectral["centroid"], 2),
        "spectral_flatness": round(spectral["flatness"], 5),
        "spectral_rolloff": round(spectral["rolloff"], 2),
        "syllable_rate": round(syllable_rate, 2),
        "energy_burst_ratio": round(energy_bursts, 3),
        "duration_s": round(duration_s, 2),
    }

    # --- Scoring ---
    scores = {"speech": 0.0, "cry": 0.0, "laugh": 0.0, "silence": 0.0, "noise": 0.0}

    # SILENCE score
    if rms_mean < SILENCE_RMS_THRESHOLD:
        low_energy_frames = np.sum(rms < SILENCE_RMS_THRESHOLD) / max(1, len(rms))
        scores["silence"] = min(1.0, low_energy_frames * 1.1)
    if voiced_frac < MIN_VOICED_FRACTION and rms_mean < SILENCE_RMS_THRESHOLD * 3:
        scores["silence"] = max(scores["silence"], 0.7)

    # CRY score
    cry_score = 0.0
    if CRY_F0_MIN_HZ <= f0_mean <= CRY_F0_MAX_HZ:
        cry_score += 0.30  # High F0 in cry range
    if f0_instability > 0.10:
        cry_score += 0.25  # F0 instability (wavering pitch)
    if energy_var > CRY_ENERGY_VAR_MIN:
        cry_score += 0.20  # High energy variation
    if spectral["centroid"] > CRY_SPECTRAL_CENTROID_MIN:
        cry_score += 0.15  # High spectral centroid
    if voiced_frac > 0.3:
        cry_score += 0.10  # Sustained voicing
    scores["cry"] = min(1.0, cry_score)

    # LAUGH score
    laugh_score = 0.0
    if zcr > LAUGH_ZCR_MIN:
        laugh_score += 0.25
    if energy_bursts > LAUGH_ENERGY_BURST_RATIO:
        laugh_score += 0.30  # Rhythmic bursts characteristic of laughter
    if f0_instability > LAUGH_F0_VAR_MIN and f0_instability < 0.30:
        laugh_score += 0.20  # Moderate F0 variation (less than cry)
    if f0_mean > 200 and f0_mean < 500:
        laugh_score += 0.15
    if syllable_rate > 3.0:
        laugh_score += 0.10  # Quick bursts
    scores["laugh"] = min(1.0, laugh_score)

    # SPEECH score
    speech_score = 0.0
    if syllable_rate >= SPEECH_SYLLABLE_RATE_MIN:
        speech_score += 0.30
    if f0_instability < SPEECH_F0_STABILITY_MAX:
        speech_score += 0.25  # Stable pitch
    if SPEECH_PAUSE_RATIO_RANGE[0] < (1 - voiced_frac) < SPEECH_PAUSE_RATIO_RANGE[1]:
        speech_score += 0.20  # Natural pauses
    if spectral["flatness"] < 0.1:
        speech_score += 0.15  # Harmonic (not noise-like)
    if voiced_frac > 0.2:
        speech_score += 0.10
    scores["speech"] = min(1.0, speech_score)

    # NOISE score
    noise_score = 0.0
    if spectral["flatness"] > 0.3:
        noise_score += 0.40  # Flat spectrum = noise-like
    if voiced_frac < 0.1 and rms_mean > SILENCE_RMS_THRESHOLD:
        noise_score += 0.30  # Energy but no voicing
    if zcr > 0.1:
        noise_score += 0.20  # Very high ZCR = noise
    if f0_mean < 50 or f0_mean == 0:
        noise_score += 0.10
    scores["noise"] = min(1.0, noise_score)

    # --- Determine primary type ---
    # Sort by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_type, best_score = ranked[0]
    second_type, second_score = ranked[1]

    # Minimum threshold to claim a type
    if best_score < 0.25:
        primary_type = SOUND_NOISE  # Default fallback
        confidence = 0.3
    elif best_score - second_score < MIXED_AMBIGUITY_GAP:
        primary_type = SOUND_MIXED
        confidence = best_score
    else:
        primary_type = best_type
        confidence = min(0.95, best_score)

    return {
        "primary_type": primary_type,
        "confidence": round(confidence, 3),
        "scores": {k: round(v, 3) for k, v in scores.items()},
        "features": features,
    }


def classify_segments(
    y: np.ndarray,
    sr: int,
    segments: List[Dict],
) -> List[Dict]:
    """
    Classify each diarized segment individually.

    Args:
        y: Full audio signal
        sr: Sample rate
        segments: List of {"start_s": float, "end_s": float, "label": str}

    Returns:
        List of segment classifications with sound type added
    """
    results = []
    for seg in segments:
        start_s = float(seg.get("start_s", 0))
        end_s = float(seg.get("end_s", 0))
        if end_s <= start_s:
            continue

        start_i = int(max(0, start_s * sr))
        end_i = int(min(len(y), end_s * sr))
        if end_i <= start_i:
            continue

        y_seg = y[start_i:end_i]
        if len(y_seg) < sr * 0.15:
            continue

        classification = classify_sound(y_seg, sr, duration_s=end_s - start_s)
        results.append({
            "start_s": round(start_s, 3),
            "end_s": round(end_s, 3),
            "duration_s": round(end_s - start_s, 3),
            "speaker_label": seg.get("label", "unknown"),
            "sound_type": classification["primary_type"],
            "sound_confidence": classification["confidence"],
            "sound_scores": classification["scores"],
        })

    return results


def aggregate_sound_types(segment_classifications: List[Dict]) -> Dict[str, Any]:
    """
    Aggregate segment-level classifications into a session-level summary.

    Returns:
        {
            "dominant_type": str,
            "type_durations": {"speech": 2.3, "cry": 5.1, ...},
            "type_ratios": {"speech": 0.3, "cry": 0.5, ...},
            "total_duration": float,
            "segment_count": int,
            "has_speech": bool,
            "has_cry": bool,
            "has_laugh": bool,
        }
    """
    type_durations = {"speech": 0.0, "cry": 0.0, "laugh": 0.0, "silence": 0.0, "noise": 0.0, "mixed": 0.0}
    total = 0.0

    for seg in segment_classifications:
        dur = seg.get("duration_s", 0.0)
        stype = seg.get("sound_type", "noise")
        type_durations[stype] = type_durations.get(stype, 0.0) + dur
        total += dur

    type_ratios = {}
    for k, v in type_durations.items():
        type_ratios[k] = round(v / max(0.001, total), 3)

    # Dominant type (excluding silence and noise for ranking)
    active_types = {k: v for k, v in type_durations.items() if k not in ("silence", "noise", "mixed")}
    if active_types:
        dominant = max(active_types, key=active_types.get)
    elif type_durations.get("silence", 0) > type_durations.get("noise", 0):
        dominant = "silence"
    else:
        dominant = "noise"

    return {
        "dominant_type": dominant,
        "type_durations": {k: round(v, 3) for k, v in type_durations.items()},
        "type_ratios": type_ratios,
        "total_duration": round(total, 3),
        "segment_count": len(segment_classifications),
        "has_speech": type_ratios.get("speech", 0) > 0.05,
        "has_cry": type_ratios.get("cry", 0) > 0.05,
        "has_laugh": type_ratios.get("laugh", 0) > 0.05,
    }
