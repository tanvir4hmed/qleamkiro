"""
Qleam — Rich Acoustic Feature Extraction (Phase 3)

Extracts ~65 acoustic features organized into 7 groups.

Feature groups:
  Group 1 ( 7): Prosodic       — F0 mean/std/min/max/range, voiced fraction, jitter
  Group 2 ( 2): Voice quality  — shimmer (dB), HNR (dB)
  Group 3 (39): MFCC           — coefficients 1-13 + delta + delta-delta (means)
  Group 4 ( 7): Spectral       — centroid, rolloff, bandwidth, flatness, contrast, ZCR, entropy
  Group 5 ( 5): Temporal       — RMS mean/std, energy entropy, pause ratio, syllable rate
  Group 6 ( 3): Formants       — F1, F2, F3 (reuses pre-computed from bio validation)
  Group 7 ( 2): Cry/Babble     — cry fraction, babble fraction
  Total: ~65 features

Design principles:
  - All functions are pure: (y, sr) → Dict[str, float]
  - Every value is a Python float — safe for DynamoDB Decimal conversion
  - Graceful degradation: individual group failures return 0.0 defaults
  - Formants are accepted as an optional pre-computed dict to avoid double LPC
"""
import logging
from typing import Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

_librosa = None


def _get_librosa():
    global _librosa
    if _librosa is None:
        import librosa
        _librosa = librosa
    return _librosa


# ---------------------------------------------------------------------------
# Group 1: Prosodic Features (F0-based)
# ---------------------------------------------------------------------------

def extract_prosodic_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Extract F0 statistics and jitter (cycle-to-cycle F0 perturbation).

    F0 estimated via YIN algorithm.
    Jitter (%) = mean absolute F0 difference / mean F0 × 100.

    Returns:
        f0_mean, f0_std, f0_min, f0_max, f0_range,
        f0_voiced_fraction, jitter_percent
    """
    librosa = _get_librosa()
    result = {
        "f0_mean": 0.0,
        "f0_std": 0.0,
        "f0_min": 0.0,
        "f0_max": 0.0,
        "f0_range": 0.0,
        "f0_voiced_fraction": 0.0,
        "jitter_percent": 0.0,
    }

    try:
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"))
        f0_all = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        f0_voiced = f0_all[f0_all > 0]

        if len(f0_voiced) == 0:
            return result

        result["f0_mean"] = round(float(np.mean(f0_voiced)), 2)
        result["f0_std"] = round(float(np.std(f0_voiced)), 2)
        result["f0_min"] = round(float(np.min(f0_voiced)), 2)
        result["f0_max"] = round(float(np.max(f0_voiced)), 2)
        result["f0_range"] = round(float(np.max(f0_voiced) - np.min(f0_voiced)), 2)
        result["f0_voiced_fraction"] = round(float(len(f0_voiced) / max(len(f0), 1)), 4)

        # Jitter: mean absolute cycle-to-cycle F0 perturbation
        if len(f0_voiced) > 1:
            diffs = np.abs(np.diff(f0_voiced))
            jitter = float(np.mean(diffs) / (np.mean(f0_voiced) + 1e-8)) * 100.0
            result["jitter_percent"] = round(min(jitter, 100.0), 4)

    except Exception as e:
        logger.warning(f"Prosodic feature extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Group 2: Voice Quality — Shimmer + HNR
# ---------------------------------------------------------------------------

def extract_voice_quality_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Extract shimmer (amplitude perturbation) and HNR (Harmonics-to-Noise Ratio).

    Shimmer (dB):
        Frame-level RMS amplitude perturbation on voiced frames.
        shimmer_linear = mean |A_i+1 - A_i| / mean(A)
        shimmer_dB = -20 * log10(1 - shimmer_linear)

    HNR (dB):
        Estimated from autocorrelation peak on a 40ms center frame.
        HNR = 10 * log10(r / (1 - r))   where r = normalized autocorrelation peak.

    Returns:
        shimmer_db, hnr_db
    """
    librosa = _get_librosa()
    result = {"shimmer_db": 0.0, "hnr_db": 0.0}

    try:
        # --- Shimmer ---
        rms = librosa.feature.rms(y=y, hop_length=256)[0]
        voiced_mask = rms > (np.mean(rms) * 0.1)
        rms_voiced = rms[voiced_mask]

        if len(rms_voiced) > 1:
            rms_mean = float(np.mean(rms_voiced)) + 1e-10
            amp_diffs = np.abs(np.diff(rms_voiced))
            shimmer_linear = float(np.mean(amp_diffs)) / rms_mean
            shimmer_db = -20.0 * np.log10(max(1.0 - shimmer_linear, 1e-5))
            result["shimmer_db"] = round(float(np.clip(shimmer_db, 0.0, 30.0)), 4)

        # --- HNR via autocorrelation on a 40ms center frame ---
        frame_len = int(0.04 * sr)
        mid = len(y) // 2
        frame = y[max(0, mid - frame_len): mid + frame_len]

        if len(frame) > 32:
            corr = np.correlate(frame, frame, mode="full")
            corr = corr[len(corr) // 2:]  # positive lags only

            if corr[0] > 0:
                corr_norm = corr / corr[0]

                # Search for peak in F0 range 50–500 Hz
                min_lag = max(1, int(sr / 500))
                max_lag = min(len(corr_norm) - 1, int(sr / 50))

                if max_lag > min_lag:
                    peak_idx = np.argmax(corr_norm[min_lag:max_lag]) + min_lag
                    r = float(np.clip(corr_norm[peak_idx], 0.0, 0.9999))
                    hnr = 10.0 * np.log10(r / max(1.0 - r, 1e-10))
                    result["hnr_db"] = round(float(np.clip(hnr, -20.0, 40.0)), 4)

    except Exception as e:
        logger.warning(f"Voice quality feature extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Group 3: MFCC Features (mean of each coefficient + delta + delta-delta)
# ---------------------------------------------------------------------------

def extract_mfcc_features(y: np.ndarray, sr: int, n_mfcc: int = 13) -> Dict[str, float]:
    """
    Extract per-coefficient means for MFCC, delta, and delta-delta.

    Returns 39 features:
        mfcc_1 … mfcc_13            — static MFCC coefficients
        mfcc_delta_1 … mfcc_delta_13  — first-order delta (velocity)
        mfcc_delta2_1 … mfcc_delta2_13 — second-order delta (acceleration)
    """
    librosa = _get_librosa()
    result = {}

    for i in range(1, n_mfcc + 1):
        result[f"mfcc_{i}"] = 0.0
        result[f"mfcc_delta_{i}"] = 0.0
        result[f"mfcc_delta2_{i}"] = 0.0

    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
        delta = librosa.feature.delta(mfcc)
        delta2 = librosa.feature.delta(mfcc, order=2)

        for i in range(n_mfcc):
            result[f"mfcc_{i + 1}"] = round(float(np.mean(mfcc[i])), 4)
            result[f"mfcc_delta_{i + 1}"] = round(float(np.mean(delta[i])), 4)
            result[f"mfcc_delta2_{i + 1}"] = round(float(np.mean(delta2[i])), 4)

    except Exception as e:
        logger.warning(f"MFCC feature extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Group 4: Spectral Features
# ---------------------------------------------------------------------------

def extract_spectral_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Extract spectral shape descriptors.

    Returns:
        spectral_centroid      — brightness (Hz), mean across frames
        spectral_rolloff       — frequency containing 85% of energy (Hz)
        spectral_bandwidth     — spread around centroid (Hz)
        spectral_flatness      — tonality: 0=pure tone, 1=white noise
        spectral_contrast_mean — mean spectral contrast (peak vs valley)
        zcr                    — zero crossing rate (mean)
        spectral_entropy       — Shannon entropy of mean power spectrum
    """
    librosa = _get_librosa()
    result = {
        "spectral_centroid": 0.0,
        "spectral_rolloff": 0.0,
        "spectral_bandwidth": 0.0,
        "spectral_flatness": 0.0,
        "spectral_contrast_mean": 0.0,
        "zcr": 0.0,
        "spectral_entropy": 0.0,
    }

    try:
        result["spectral_centroid"] = round(
            float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))), 2
        )
        result["spectral_rolloff"] = round(
            float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85))), 2
        )
        result["spectral_bandwidth"] = round(
            float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))), 2
        )
        result["spectral_flatness"] = round(
            float(np.mean(librosa.feature.spectral_flatness(y=y))), 6
        )
        result["spectral_contrast_mean"] = round(
            float(np.mean(librosa.feature.spectral_contrast(y=y, sr=sr))), 4
        )
        result["zcr"] = round(
            float(np.mean(librosa.feature.zero_crossing_rate(y=y))), 6
        )

        # Spectral entropy: Shannon entropy of mean power spectrum
        stft_power = np.abs(librosa.stft(y)) ** 2
        mean_power = np.mean(stft_power, axis=1)
        total = float(np.sum(mean_power)) + 1e-10
        prob = mean_power / total
        entropy = float(-np.sum(prob * np.log2(prob + 1e-10)))
        result["spectral_entropy"] = round(entropy, 4)

    except Exception as e:
        logger.warning(f"Spectral feature extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Group 5: Temporal / Energy Features
# ---------------------------------------------------------------------------

def extract_temporal_features(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Extract energy envelope and temporal structure features.

    Returns:
        rms_mean       — mean RMS energy
        rms_std        — RMS energy standard deviation
        energy_entropy — Shannon entropy of RMS energy distribution
        pause_ratio    — fraction of frames below 5% of peak RMS
        syllable_rate  — onset detections per second (proxy for syllable rate)
    """
    librosa = _get_librosa()
    result = {
        "rms_mean": 0.0,
        "rms_std": 0.0,
        "energy_entropy": 0.0,
        "pause_ratio": 0.0,
        "syllable_rate": 0.0,
    }

    try:
        rms = librosa.feature.rms(y=y)[0]

        if len(rms) == 0:
            return result

        result["rms_mean"] = round(float(np.mean(rms)), 6)
        result["rms_std"] = round(float(np.std(rms)), 6)

        # Energy entropy
        rms_sum = float(np.sum(rms)) + 1e-10
        rms_prob = rms / rms_sum
        energy_entropy = float(-np.sum(rms_prob * np.log2(rms_prob + 1e-10)))
        result["energy_entropy"] = round(energy_entropy, 4)

        # Pause ratio
        peak = float(np.max(rms)) if float(np.max(rms)) > 0 else 1e-10
        silent_frames = float(np.sum(rms < 0.05 * peak))
        result["pause_ratio"] = round(silent_frames / max(len(rms), 1), 4)

        # Syllable rate via onset detection
        duration_s = len(y) / max(sr, 1)
        if duration_s > 0:
            onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
            result["syllable_rate"] = round(len(onset_frames) / duration_s, 4)

    except Exception as e:
        logger.warning(f"Temporal feature extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Group 6: Formant Features
# ---------------------------------------------------------------------------

def extract_formant_features(formants: Dict[str, float]) -> Dict[str, float]:
    """
    Repackage pre-computed LPC formants as flat feature keys.

    Args:
        formants: {"F1": Hz, "F2": Hz, "F3": Hz} — from extract_formants_lpc()

    Returns:
        {"formant_f1": Hz, "formant_f2": Hz, "formant_f3": Hz}
    """
    return {
        "formant_f1": round(float(formants.get("F1", 0.0)), 1),
        "formant_f2": round(float(formants.get("F2", 0.0)), 1),
        "formant_f3": round(float(formants.get("F3", 0.0)), 1),
    }


# ---------------------------------------------------------------------------
# Group 7: Cry-to-Babble Ratio
# ---------------------------------------------------------------------------

def extract_cry_babble_ratio(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Classify voiced frames as cry vs babble based on F0 range.

    Cry:    F0 > 350 Hz (infant cry: 300–600 Hz)
    Babble: F0 200–350 Hz (infant canonical babble)

    Returns:
        cry_fraction    — fraction of voiced frames classified as cry
        babble_fraction — fraction of voiced frames classified as babble
    """
    librosa = _get_librosa()
    result = {"cry_fraction": 0.0, "babble_fraction": 0.0}

    try:
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"))
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        f0_voiced = f0_voiced[f0_voiced > 0]

        if len(f0_voiced) == 0:
            return result

        total = float(len(f0_voiced))
        result["cry_fraction"] = round(float(np.sum(f0_voiced > 350)) / total, 4)
        result["babble_fraction"] = round(
            float(np.sum((f0_voiced >= 200) & (f0_voiced <= 350))) / total, 4
        )

    except Exception as e:
        logger.warning(f"Cry-babble ratio extraction failed: {e}")

    return result


# ---------------------------------------------------------------------------
# Full Rich Feature Pipeline
# ---------------------------------------------------------------------------

def extract_rich_features(
    y: np.ndarray,
    sr: int,
    formants: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Extract all rich acoustic features (~65 features).

    Args:
        y:        Audio array (trimmed, mono, float32)
        sr:       Sample rate
        formants: Pre-computed {"F1": Hz, "F2": Hz, "F3": Hz} from biological_validation.
                  If None, formants are extracted internally via LPC.

    Returns:
        Flat dict of feature_name -> float.
        All values are Python floats — safe for DynamoDB Decimal conversion.
        Missing/failed features default to 0.0.

    Feature count: ~65
        Group 1 ( 7): f0_mean, f0_std, f0_min, f0_max, f0_range,
                       f0_voiced_fraction, jitter_percent
        Group 2 ( 2): shimmer_db, hnr_db
        Group 3 (39): mfcc_{1-13}, mfcc_delta_{1-13}, mfcc_delta2_{1-13}
        Group 4 ( 7): spectral_centroid, spectral_rolloff, spectral_bandwidth,
                       spectral_flatness, spectral_contrast_mean, zcr, spectral_entropy
        Group 5 ( 5): rms_mean, rms_std, energy_entropy, pause_ratio, syllable_rate
        Group 6 ( 3): formant_f1, formant_f2, formant_f3
        Group 7 ( 2): cry_fraction, babble_fraction
    """
    features: Dict[str, float] = {}

    features.update(extract_prosodic_features(y, sr))
    features.update(extract_voice_quality_features(y, sr))
    features.update(extract_mfcc_features(y, sr))
    features.update(extract_spectral_features(y, sr))
    features.update(extract_temporal_features(y, sr))

    # Formants — reuse pre-computed from bio validation to avoid double LPC
    if formants is None:
        try:
            from audio_utils import extract_formants_lpc
            formants = extract_formants_lpc(y, sr)
        except Exception as e:
            logger.warning(f"Fallback formant extraction failed: {e}")
            formants = {"F1": 0.0, "F2": 0.0, "F3": 0.0}

    features.update(extract_formant_features(formants))
    features.update(extract_cry_babble_ratio(y, sr))

    # Group 8 (1): CBR estimate — approximated from session-level aggregates
    features["cbr_estimate"] = _compute_cbr_estimate(
        babble_fraction=features.get("babble_fraction", 0.0),
        hnr_db=features.get("hnr_db", 0.0),
        f1=features.get("formant_f1", 0.0),
        f2=features.get("formant_f2", 0.0),
    )

    logger.info(f"Rich feature extraction complete: {len(features)} features")
    return features


def _compute_cbr_estimate(babble_fraction: float, hnr_db: float, f1: float, f2: float) -> float:
    """
    Approximate Canonical Babbling Ratio from session-level aggregates.
    True CBR requires syllable segmentation; this estimates from existing features.

    voice_quality: 0 at HNR≤3dB (noisy), 1 at HNR≥13dB (clear voiced)
    formant_factor: full weight if F1>300Hz and F2>700Hz (canonical vowel space)
    """
    voice_quality = max(0.0, min(1.0, (hnr_db - 3.0) / 10.0))
    if f1 > 300 and f2 > 700:
        formant_factor = 1.0
    elif f1 > 200:
        formant_factor = 0.6
    else:
        formant_factor = 0.3
    return round(min(1.0, max(0.0, babble_fraction * voice_quality * formant_factor)), 4)
