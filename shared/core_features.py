"""
Qleam — Core Feature Extraction (Phase 1)
Single computation point for F0, RMS, ZCR, and spectral features.
All downstream consumers receive pre-computed features instead of
recomputing from raw audio independently.
"""
import logging
from typing import Any, Dict, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_librosa = None


def _get_librosa():
    global _librosa
    if _librosa is None:
        import librosa
        _librosa = librosa
    return _librosa


def compute_core_features(y: np.ndarray, sr: int) -> Dict[str, Any]:
    """
    Compute all core acoustic features from audio ONCE.

    Returns a dict with:
        f0_mean, f0_std, voiced_fraction, f0_instability,
        rms (array), rms_mean, rms_std, energy_variability,
        zcr,
        spectral_centroid, spectral_flatness, spectral_rolloff,
        syllable_rate, energy_burst_ratio,
        duration_s
    """
    if y is None or len(y) == 0:
        return _empty_features()

    duration_s = len(y) / max(sr, 1)

    # --- F0 (pyin — probabilistic YIN) ---
    f0_mean, f0_std, voiced_frac = _compute_f0(y, sr)
    f0_instability = f0_std / (f0_mean + 1e-9) if f0_mean > 0 else 0.0

    # --- RMS energy (frame-level) ---
    rms = _compute_rms(y, sr)
    rms_mean = float(np.mean(rms)) if len(rms) > 0 else 0.0
    rms_std = float(np.std(rms)) if len(rms) > 0 else 0.0
    energy_var = rms_std / (rms_mean + 1e-9)

    # --- Zero-crossing rate ---
    zcr = _compute_zcr(y)

    # --- Spectral features ---
    spectral = _compute_spectral(y, sr)

    # --- Derived features ---
    syllable_rate = _estimate_syllable_rate(rms, y, sr)
    energy_bursts = _detect_energy_bursts(rms)

    return {
        "f0_mean": round(f0_mean, 2),
        "f0_std": round(f0_std, 2),
        "voiced_fraction": round(voiced_frac, 3),
        "f0_instability": round(f0_instability, 4),
        "rms": rms,  # raw array for downstream use
        "rms_mean": round(rms_mean, 5),
        "rms_std": round(rms_std, 5),
        "energy_variability": round(energy_var, 3),
        "zcr": round(zcr, 4),
        "spectral_centroid": round(spectral["centroid"], 2),
        "spectral_flatness": round(spectral["flatness"], 5),
        "spectral_rolloff": round(spectral["rolloff"], 2),
        "syllable_rate": round(syllable_rate, 2),
        "energy_burst_ratio": round(energy_bursts, 3),
        "duration_s": round(duration_s, 2),
    }


def _compute_f0(y: np.ndarray, sr: int) -> Tuple[float, float, float]:
    """Compute F0 using pyin. Returns (f0_mean, f0_std, voiced_fraction)."""
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


def _compute_rms(y: np.ndarray, sr: int, frame_ms: int = 25) -> np.ndarray:
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


def _compute_zcr(y: np.ndarray) -> float:
    """Zero-crossing rate."""
    if len(y) < 3:
        return 0.0
    signs = np.sign(y)
    return float(np.sum(signs[:-1] != signs[1:])) / max(1, len(y))


def _compute_spectral(y: np.ndarray, sr: int) -> Dict[str, float]:
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


def _estimate_syllable_rate(rms: np.ndarray, y: np.ndarray, sr: int) -> float:
    """Estimate syllable rate from RMS energy peaks."""
    if len(rms) < 5:
        return 0.0

    kernel_size = min(5, len(rms))
    kernel = np.ones(kernel_size) / kernel_size
    smoothed = np.convolve(rms, kernel, mode='same')

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

    above = rms > mean_rms * 1.2
    transitions = int(np.sum(np.diff(above.astype(int)) != 0))
    burst_rate = transitions / max(1, len(rms))
    return min(1.0, burst_rate * 5.0)


def _empty_features() -> Dict[str, Any]:
    return {
        "f0_mean": 0.0, "f0_std": 0.0, "voiced_fraction": 0.0,
        "f0_instability": 0.0,
        "rms": np.zeros(0), "rms_mean": 0.0, "rms_std": 0.0,
        "energy_variability": 0.0,
        "zcr": 0.0,
        "spectral_centroid": 0.0, "spectral_flatness": 0.0, "spectral_rolloff": 0.0,
        "syllable_rate": 0.0, "energy_burst_ratio": 0.0,
        "duration_s": 0.0,
    }
