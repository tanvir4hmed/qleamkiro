"""
Qleam — Audio Utilities
Audio loading, preprocessing, and feature extraction
"""
import io
import logging
import os
import tempfile
from typing import Dict, List, Optional, Tuple

import boto3
import numpy as np

logger = logging.getLogger(__name__)

# Lazy imports for Lambda layer (librosa is large)
_librosa = None
_scipy = None


def _get_librosa():
    global _librosa
    if _librosa is None:
        import librosa
        _librosa = librosa
    return _librosa


def _get_scipy():
    global _scipy
    if _scipy is None:
        import scipy
        _scipy = scipy
    return _scipy


def download_audio_from_s3(bucket: str, key: str) -> bytes:
    """
    Download audio file from S3.
    
    Args:
        bucket: S3 bucket name
        key: S3 object key
    
    Returns:
        Audio file bytes
    """
    s3 = boto3.client("s3")
    logger.info(f"Downloading audio from s3://{bucket}/{key}")
    
    response = s3.get_object(Bucket=bucket, Key=key)
    audio_bytes = response["Body"].read()
    logger.info(f"Downloaded {len(audio_bytes)} bytes")
    return audio_bytes


def load_audio_from_bytes(audio_bytes: bytes, target_sr: int = 22050) -> Tuple[np.ndarray, int]:
    """
    Load audio from bytes, convert to mono, resample.
    
    Always uses ffmpeg for maximum compatibility with all audio formats
    (WebM, WAV, MP3, MP4, OGG, etc.) including corrupted or variant files.
    
    Args:
        audio_bytes: Raw audio bytes
        target_sr: Target sample rate
    
    Returns:
        Tuple of (audio_array, sample_rate)
    """
    import soundfile as sf
    import subprocess
    
    # Log file info for debugging
    file_size = len(audio_bytes)
    header = audio_bytes[:16] if len(audio_bytes) >= 16 else audio_bytes
    logger.info(f"Loading audio: {file_size} bytes, header: {header.hex()}")
    
    if file_size < 100:
        raise ValueError(f"Audio file too small: {file_size} bytes")
    
    # Always use ffmpeg - handles all formats reliably
    # Write input to temp file (ffmpeg auto-detects format)
    with tempfile.NamedTemporaryFile(delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in_path = tmp_in.name
    
    # Output WAV file
    tmp_out_path = tempfile.mktemp(suffix='.wav')
    
    try:
        # Use ffmpeg to convert to WAV (mono, target sample rate)
        # -y: overwrite output
        # -i: input file (auto-detect format)
        # -ac 1: mono
        # -ar: target sample rate
        # -resampler soxr: use libsoxr for high-quality resampling
        # -precision 28: maximum precision for soxr (28-bit)
        # -f wav: output format
        # -acodec pcm_f32le: 32-bit float PCM for soundfile compatibility
        cmd = [
            'ffmpeg', '-y', '-i', tmp_in_path,
            '-ac', '1',
            '-ar', str(target_sr),
            '-resampler', 'soxr',
            '-precision', '28',
            '-f', 'wav',
            '-acodec', 'pcm_f32le',
            tmp_out_path
        ]
        
        logger.info(f"Running ffmpeg: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            logger.error(f"ffmpeg stderr: {result.stderr}")
            raise RuntimeError(f"ffmpeg failed to process audio: {result.stderr[:500]}")
        
        # Read the converted WAV file
        y, sr = sf.read(tmp_out_path, dtype='float32')
        
        logger.info(f"Loaded audio: {len(y)} samples at {sr}Hz ({len(y)/sr:.2f}s)")
        return y, sr
        
    except subprocess.TimeoutExpired:
        raise RuntimeError("ffmpeg conversion timed out (60s limit)")
    except Exception as e:
        logger.error(f"Audio loading failed: {e}")
        raise
    finally:
        # Clean up temp files
        if os.path.exists(tmp_in_path):
            os.unlink(tmp_in_path)
        if os.path.exists(tmp_out_path):
            os.unlink(tmp_out_path)


def voice_activity_detection(y: np.ndarray, sr: int, top_db: float = 20.0) -> np.ndarray:
    """
    Simple Voice Activity Detection — trim silence.
    
    Args:
        y: Audio array
        sr: Sample rate
        top_db: Threshold in dB below reference
    
    Returns:
        Trimmed audio array
    """
    librosa = _get_librosa()
    y_trimmed, _ = librosa.effects.trim(y, top_db=top_db)
    logger.debug(f"VAD: {len(y)} -> {len(y_trimmed)} samples")
    return y_trimmed


def extract_mfcc(y: np.ndarray, sr: int, n_mfcc: int = 13) -> np.ndarray:
    """
    Extract MFCC features.
    
    Returns:
        MFCC matrix (n_mfcc x time_frames)
    """
    librosa = _get_librosa()
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
    return mfcc


def extract_rhythm_score(y: np.ndarray, sr: int) -> float:
    """
    Compute rhythm score from energy peaks.
    
    Method:
        - Compute RMS energy envelope
        - Count energy peaks per second
        - Compute variance of inter-peak intervals
        - Normalize to [0, 1]
    
    Higher score = more rhythmic/regular pattern
    """
    librosa = _get_librosa()
    
    # RMS energy
    rms = librosa.feature.rms(y=y)[0]
    
    if len(rms) == 0 or np.max(rms) == 0:
        return 0.0
    
    # Normalize RMS
    rms_norm = rms / np.max(rms)
    
    # Find peaks above threshold
    threshold = 0.3
    peaks = np.where(rms_norm > threshold)[0]
    
    if len(peaks) < 2:
        return 0.1  # Very low rhythm
    
    # Inter-peak intervals
    intervals = np.diff(peaks)
    
    # Regularity = inverse of coefficient of variation
    mean_interval = np.mean(intervals)
    std_interval = np.std(intervals)
    
    if mean_interval == 0:
        return 0.0
    
    cv = std_interval / mean_interval  # Coefficient of variation
    
    # Low CV = regular rhythm = high score
    rhythm_score = 1.0 / (1.0 + cv)
    return float(np.clip(rhythm_score, 0.0, 1.0))


def extract_repetition_score(y: np.ndarray, sr: int, n_mfcc: int = 13) -> float:
    """
    Compute repetition score using MFCC self-similarity.
    
    Method:
        - Extract MFCC
        - Compute self-similarity matrix
        - Score = mean of off-diagonal similarity (repetition indicator)
    
    Higher score = more repetitive sound patterns
    """
    librosa = _get_librosa()
    
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
    
    if mfcc.shape[1] < 4:
        return 0.0
    
    # Normalize MFCC frames
    mfcc_norm = mfcc / (np.linalg.norm(mfcc, axis=0, keepdims=True) + 1e-8)
    
    # Self-similarity matrix
    sim_matrix = np.dot(mfcc_norm.T, mfcc_norm)
    
    # Off-diagonal mean (exclude main diagonal)
    n = sim_matrix.shape[0]
    mask = ~np.eye(n, dtype=bool)
    off_diag_mean = np.mean(sim_matrix[mask])
    
    # Normalize to [0, 1]
    repetition_score = float(np.clip((off_diag_mean + 1.0) / 2.0, 0.0, 1.0))
    return repetition_score


def extract_emotional_intensity(y: np.ndarray, sr: int) -> float:
    """
    Compute emotional intensity from pitch variance and energy amplitude.
    
    Method:
        - F0 (fundamental frequency) variance
        - RMS energy amplitude variance
        - Combined score
    
    Higher score = higher emotional intensity
    """
    librosa = _get_librosa()
    
    # Pitch (F0) using yin (pure numpy/scipy, no numba required)
    try:
        f0 = librosa.yin(
            y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7')
        )
        # Filter out NaN values (unvoiced frames)
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        
        if len(f0_voiced) > 1:
            f0_variance = float(np.std(f0_voiced) / (np.mean(f0_voiced) + 1e-8))
            f0_score = float(np.clip(f0_variance / 2.0, 0.0, 1.0))
        else:
            f0_score = 0.3  # Default moderate
    except Exception:
        f0_score = 0.3
    
    # RMS energy variance
    rms = librosa.feature.rms(y=y)[0]
    if len(rms) > 1 and np.mean(rms) > 0:
        energy_variance = float(np.std(rms) / (np.mean(rms) + 1e-8))
        energy_score = float(np.clip(energy_variance, 0.0, 1.0))
    else:
        energy_score = 0.0
    
    # Combined score (weighted)
    intensity = 0.6 * f0_score + 0.4 * energy_score
    return float(np.clip(intensity, 0.0, 1.0))


def extract_expressive_flow(y: np.ndarray, sr: int) -> float:
    """
    Compute expressive flow from pause ratio and continuity.
    
    Method:
        - Compute silence ratio (pause ratio)
        - Compute continuity duration (longest voiced segment)
        - Flow = inverse of pause ratio weighted by continuity
    
    Higher score = more continuous, flowing vocalization
    """
    librosa = _get_librosa()
    
    # RMS energy
    rms = librosa.feature.rms(y=y)[0]
    
    if len(rms) == 0:
        return 0.0
    
    # Silence threshold
    silence_threshold = 0.05 * np.max(rms) if np.max(rms) > 0 else 0.0
    
    # Pause ratio
    silent_frames = np.sum(rms < silence_threshold)
    pause_ratio = float(silent_frames / len(rms))
    
    # Continuity: longest voiced segment
    voiced = rms >= silence_threshold
    max_continuity = 0
    current_run = 0
    for v in voiced:
        if v:
            current_run += 1
            max_continuity = max(max_continuity, current_run)
        else:
            current_run = 0
    
    continuity_ratio = float(max_continuity / len(rms)) if len(rms) > 0 else 0.0
    
    # Flow = low pause + high continuity
    flow_score = (1.0 - pause_ratio) * 0.5 + continuity_ratio * 0.5
    return float(np.clip(flow_score, 0.0, 1.0))


def extract_embedding_vector(y: np.ndarray, sr: int, n_mfcc: int = 13) -> List[float]:
    """
    Extract a compact embedding vector for cluster comparison.
    
    Uses mean + std of MFCC coefficients = 2 * n_mfcc dimensional vector.
    
    Returns:
        List of floats (embedding vector)
    """
    librosa = _get_librosa()
    
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=n_mfcc)
    
    # Mean and std of each MFCC coefficient
    mfcc_mean = np.mean(mfcc, axis=1)
    mfcc_std = np.std(mfcc, axis=1)
    
    # Concatenate to form embedding
    embedding = np.concatenate([mfcc_mean, mfcc_std])
    
    # L2 normalize
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    
    return embedding.tolist()


# =============================================================================
# Phase 1 — Layer 0: Audio Quality Gate
# =============================================================================

def _compute_snr(rms: np.ndarray) -> float:
    """Estimate SNR from RMS energy frames (signal top 20% vs noise bottom 20%)."""
    if len(rms) < 4:
        return 0.0
    rms_sorted = np.sort(rms)
    n = len(rms_sorted)
    noise_mean = float(np.mean(rms_sorted[: max(1, n // 5)])) + 1e-10
    signal_mean = float(np.mean(rms_sorted[n - max(1, n // 5) :])) + 1e-10
    snr_db = 10.0 * np.log10(signal_mean / noise_mean)
    return float(np.clip(snr_db, -20.0, 80.0))


def _compute_clipping_ratio(y: np.ndarray, threshold: float = 0.99) -> float:
    """Fraction of samples at or near the clipping boundary."""
    if len(y) == 0:
        return 0.0
    return float(np.sum(np.abs(y) >= threshold) / len(y))


def _compute_noise_floor_db(rms: np.ndarray) -> float:
    """Estimate background noise floor in dBFS from the quietest 10% of frames."""
    if len(rms) == 0:
        return -60.0
    n = max(1, len(rms) // 10)
    noise_rms = float(np.mean(np.sort(rms)[:n])) + 1e-10
    return float(10.0 * np.log10(noise_rms ** 2 + 1e-10))


def audio_quality_gate(
    y: np.ndarray,
    sr: int,
    duration_seconds: float,
    min_duration: float = 3.0,
    max_duration: float = 60.0,
    min_snr_db: float = 10.0,
    max_silence_ratio: float = 0.80,
    max_clipping_ratio: float = 0.005,
    lombard_floor_db: float = -30.0,
) -> Dict:
    """
    Layer 0: Audio quality gate — run before any feature extraction.

    Thresholds per TECHNICAL_PIPELINE.md Layer 0:
        min_duration=3.0s, min_snr=10dB, silence<0.80, clipping<0.005 (0.5%)

    Checks duration, SNR, silence ratio, clipping, and Lombard noise flag.
    Lombard flag is a warning only and does not fail the gate.

    Returns:
        {
            "passed": bool,
            "issues": List[str],
            "snr_db": float,
            "silence_ratio": float,
            "duration_seconds": float,
            "clipping_ratio": float,
            "lombard_flag": bool,
            "noise_floor_db": float,
        }
    """
    librosa = _get_librosa()
    issues = []

    # --- Duration ---
    if duration_seconds < min_duration:
        issues.append(f"too_short:{duration_seconds:.1f}s")
    if duration_seconds > max_duration:
        issues.append(f"too_long:{duration_seconds:.1f}s")

    # --- RMS energy ---
    rms = librosa.feature.rms(y=y)[0]
    max_rms = float(np.max(rms)) if len(rms) > 0 else 0.0

    # --- SNR ---
    snr_db = _compute_snr(rms)
    if snr_db < min_snr_db:
        issues.append(f"low_snr:{snr_db:.1f}dB")

    # --- Silence ratio ---
    if max_rms > 0:
        silence_threshold = 0.05 * max_rms
        silence_ratio = float(np.sum(rms < silence_threshold) / max(len(rms), 1))
    else:
        silence_ratio = 1.0
        issues.append("no_signal")

    if silence_ratio > max_silence_ratio:
        issues.append(f"too_silent:{silence_ratio:.0%}")

    # --- Voiced energy fraction ---
    # Fraction of frames with RMS significantly above the noise floor.
    # Flat ambient noise has few peaks → fraction < 0.08 means no vocal content.
    voiced_energy_fraction = 0.0
    if max_rms > 0 and len(rms) > 0:
        n_noise = max(1, len(rms) // 10)
        noise_floor_rms = float(np.mean(np.sort(rms)[:n_noise])) + 1e-10
        voiced_frames = int(np.sum(rms > 3.0 * noise_floor_rms))
        voiced_energy_fraction = float(voiced_frames / max(len(rms), 1))
        if voiced_energy_fraction < 0.08:
            issues.append("no_vocal_activity_detected")

    # --- Clipping ---
    clipping_ratio = _compute_clipping_ratio(y)
    if clipping_ratio > max_clipping_ratio:
        issues.append(f"clipping:{clipping_ratio:.1%}")

    # --- Lombard flag (warning only — does not fail gate) ---
    noise_floor_db = _compute_noise_floor_db(rms)
    lombard_flag = noise_floor_db > lombard_floor_db

    passed = len(issues) == 0

    return {
        "passed": passed,
        "issues": issues,
        "snr_db": round(snr_db, 2),
        "silence_ratio": round(silence_ratio, 4),
        "duration_seconds": round(duration_seconds, 2),
        "clipping_ratio": round(clipping_ratio, 6),
        "lombard_flag": lombard_flag,
        "noise_floor_db": round(noise_floor_db, 2),
        "voiced_energy_fraction": round(voiced_energy_fraction, 4),
    }


# =============================================================================
# Phase 1 — Layer 1: Biological Validation (Formants, VTL, Infant Classifier)
# =============================================================================

def extract_formants_lpc(y: np.ndarray, sr: int) -> Dict[str, float]:
    """
    Extract F1–F4 formant frequencies via LPC analysis.

    Uses librosa.lpc (librosa >= 0.8) on a 25ms windowed frame
    from the middle of the audio. Falls back to zeros on failure.

    F4 is required for the spec-correct VTL formula
    (SCIENTIFIC_MATHEMATICS.md Eq 1.5: mean of F2-F1, F3-F2, F4-F3).

    Returns:
        {"F1": Hz, "F2": Hz, "F3": Hz, "F4": Hz}
    """
    librosa = _get_librosa()

    try:
        frame_len = int(0.025 * sr)
        mid = len(y) // 2
        frame = y[max(0, mid - frame_len // 2): mid + frame_len // 2]

        if len(frame) < 64:
            return {"F1": 0.0, "F2": 0.0, "F3": 0.0, "F4": 0.0}

        # Hamming window + pre-emphasis
        frame = frame * np.hamming(len(frame))
        frame = np.append(frame[0], frame[1:] - 0.97 * frame[:-1])

        # LPC order (rule of thumb: 2 + sr/1000)
        order = min(2 + sr // 1000, len(frame) - 2)

        # LPC coefficients
        A = librosa.lpc(frame, order=order)

        # Roots of LPC polynomial
        roots = np.roots(A)

        # Keep roots with positive imaginary part (inside unit circle)
        roots = roots[(np.imag(roots) >= 0.01) & (np.abs(roots) < 1.0)]

        # Convert angular frequency to Hz
        freqs = np.angle(roots) * sr / (2.0 * np.pi)
        freqs = np.sort(freqs[(freqs > 90) & (freqs < sr / 2.0 - 100)])

        return {
            "F1": round(float(freqs[0]), 1) if len(freqs) > 0 else 0.0,
            "F2": round(float(freqs[1]), 1) if len(freqs) > 1 else 0.0,
            "F3": round(float(freqs[2]), 1) if len(freqs) > 2 else 0.0,
            "F4": round(float(freqs[3]), 1) if len(freqs) > 3 else 0.0,
        }

    except Exception as e:
        logger.warning(f"Formant extraction failed: {e}")
        return {"F1": 0.0, "F2": 0.0, "F3": 0.0, "F4": 0.0}


def estimate_vtl_from_formants(
    formants: Dict[str, float],
    ambient_temp_c: float = 20.0,
) -> float:
    """
    Estimate Vocal Tract Length (VTL) in cm from mean inter-formant spacing.

    Spec (SCIENTIFIC_MATHEMATICS.md Eq 1.5):
        VTL = c(T) / (2 × ΔF̄)   [cm]
        ΔF̄ = mean(F2−F1, F3−F2, F4−F3)   [Hz]

    Temperature correction (Eq 1.6):
        c(T) = 331.3 + 0.606 × T   [m/s]   (T in Celsius)

    Falls back to single-resonance estimate if fewer than 2 valid spacings.

    Reference ranges at 20°C:
        Infant 0-6m:   ~6-8 cm   (ΔF̄ ≈ 2145-1608 Hz)
        Infant 6-18m:  ~8-11 cm  (ΔF̄ ≈ 1608-1169 Hz)
        Infant 18-24m: ~10-12 cm (ΔF̄ ≈ 1169-975 Hz)
        Adult female:  ~14-17 cm (ΔF̄ ≈ 699-577 Hz)
        Adult male:    ~16-18 cm (ΔF̄ ≈ 611-543 Hz)
    """
    # Temperature-corrected speed of sound: m/s → cm/s
    c_cms = (331.3 + 0.606 * ambient_temp_c) * 100.0

    f1 = formants.get("F1", 0.0)
    f2 = formants.get("F2", 0.0)
    f3 = formants.get("F3", 0.0)
    f4 = formants.get("F4", 0.0)

    spacings = []
    if f2 > 0 and f1 > 0 and f2 > f1:
        spacings.append(f2 - f1)
    if f3 > 0 and f2 > 0 and f3 > f2:
        spacings.append(f3 - f2)
    if f4 > 0 and f3 > 0 and f4 > f3:
        spacings.append(f4 - f3)

    if len(spacings) >= 2:
        mean_spacing = sum(spacings) / len(spacings)
        if mean_spacing > 0:
            return round(c_cms / (2.0 * mean_spacing), 2)

    # Fallback: single-resonance estimate using highest available formant
    if f3 > 500:
        return round(5.0 * c_cms / (4.0 * f3), 2)
    if f2 > 500:
        return round(3.0 * c_cms / (4.0 * f2), 2)
    return 0.0


def biological_validation(
    y: np.ndarray,
    sr: int,
    vtl_infant_max_cm: float = 13.0,
    vtl_uncertain_min_cm: float = 12.5,
    infant_f0_min_hz: float = 200.0,
    strong_infant_f0_hz: float = 300.0,
    ambient_temp_c: float = 20.0,
) -> Dict:
    """
    Layer 1: Biological validation — classify infant vs adult speaker.

    Evidence sources:
      1. F0 (fundamental frequency) via YIN estimator
      2. Formants (F1–F4) via LPC analysis
      3. VTL estimate from mean inter-formant spacing (Eq 1.5)

    VTL scoring (TECHNICAL_PIPELINE.md Layer 1 / Theorem 3.1):
      VTL < 12.5 cm   → +2 (strong infant)
      VTL 12.5–13.0 cm → 0  (UNCERTAIN — no score change)
      VTL > 13.0 cm   → -2 (adult — REJECT signal)

    F0 scoring:
      +2: F0 > 300 Hz   (strong infant signal)
      +1: F0 200–300 Hz (moderate infant signal)
      -2: F0 < 180 Hz   (adult range)

    is_infant:         score >= 1
    mimicry_suspected: score <= -2 (strong adult signal in a baby session)

    Returns:
        {
            "vtl_cm": float,
            "f0_hz": float,
            "formants": {"F1": Hz, "F2": Hz, "F3": Hz, "F4": Hz},
            "is_infant": bool,
            "mimicry_suspected": bool,
            "vtl_zone": str,         # "infant" | "uncertain" | "adult"
            "bio_confidence": float, # 0-1
            "evidence": List[str],
        }
    """
    librosa = _get_librosa()
    evidence = []
    infant_score = 0

    # --- F0 estimation ---
    try:
        f0 = librosa.yin(y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7"))
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])
        f0_hz = float(np.median(f0_voiced)) if len(f0_voiced) > 0 else 0.0
    except Exception:
        f0_hz = 0.0

    if f0_hz > strong_infant_f0_hz:
        infant_score += 2
        evidence.append(f"f0_strong_infant:{f0_hz:.0f}Hz")
    elif f0_hz > infant_f0_min_hz:
        infant_score += 1
        evidence.append(f"f0_infant:{f0_hz:.0f}Hz")
    elif 0 < f0_hz < 180:
        infant_score -= 2
        evidence.append(f"f0_adult:{f0_hz:.0f}Hz")

    # --- Formants (F1–F4) + VTL via mean formant spacing ---
    formants = extract_formants_lpc(y, sr)
    vtl_cm = estimate_vtl_from_formants(formants, ambient_temp_c)

    vtl_zone = "unknown"
    if vtl_cm > 0:
        if vtl_cm < vtl_uncertain_min_cm:
            infant_score += 2
            vtl_zone = "infant"
            evidence.append(f"vtl_infant:{vtl_cm:.1f}cm")
        elif vtl_cm <= vtl_infant_max_cm:
            vtl_zone = "uncertain"
            evidence.append(f"vtl_uncertain:{vtl_cm:.1f}cm")  # no score change
        else:
            infant_score -= 2
            vtl_zone = "adult"
            evidence.append(f"vtl_adult:{vtl_cm:.1f}cm")

    is_infant = infant_score >= 1
    mimicry_suspected = infant_score <= -2
    bio_confidence = round(min(abs(infant_score) / 4.0, 1.0), 3)

    return {
        "vtl_cm": vtl_cm,
        "f0_hz": round(f0_hz, 1),
        "formants": formants,
        "is_infant": is_infant,
        "mimicry_suspected": mimicry_suspected,
        "vtl_zone": vtl_zone,
        "bio_confidence": bio_confidence,
        "evidence": evidence,
    }


def extract_all_features(audio_bytes: bytes, sr: int = 22050) -> Dict:
    """
    Full feature extraction pipeline.
    
    Args:
        audio_bytes: Raw audio bytes
        sr: Target sample rate
    
    Returns:
        {
            "feature_scores": {rhythm, repetition, emotional_intensity, expressive_flow},
            "embedding_vector": List[float],
            "duration_seconds": float,
            "sample_rate": int
        }
    """
    logger.info("Starting full feature extraction")
    
    # Load audio
    y, sr = load_audio_from_bytes(audio_bytes, target_sr=sr)
    duration = len(y) / sr
    
    # VAD — trim silence
    y_trimmed = voice_activity_detection(y, sr)
    
    if len(y_trimmed) < sr * 0.5:  # Less than 0.5 seconds of voiced audio
        logger.warning("Very short voiced audio detected")
        y_trimmed = y  # Fall back to original
    
    # Extract features
    rhythm = extract_rhythm_score(y_trimmed, sr)
    repetition = extract_repetition_score(y_trimmed, sr)
    emotional_intensity = extract_emotional_intensity(y_trimmed, sr)
    expressive_flow = extract_expressive_flow(y_trimmed, sr)
    embedding = extract_embedding_vector(y_trimmed, sr)
    
    feature_scores = {
        "rhythm": round(rhythm, 4),
        "repetition": round(repetition, 4),
        "emotional_intensity": round(emotional_intensity, 4),
        "expressive_flow": round(expressive_flow, 4),
    }
    
    logger.info(f"Feature scores: {feature_scores}")
    
    return {
        "feature_scores": feature_scores,
        "embedding_vector": embedding,
        "duration_seconds": round(duration, 2),
        "sample_rate": sr,
        # Trimmed audio array for Phase 1 quality gate + bio validation.
        # Stays in Lambda memory only — not serialised or persisted.
        "audio_array": y_trimmed,
    }
