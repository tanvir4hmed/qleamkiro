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
    
    Args:
        audio_bytes: Raw audio bytes
        target_sr: Target sample rate
    
    Returns:
        Tuple of (audio_array, sample_rate)
    """
    import soundfile as sf
    import soxr
    import subprocess
    
    # Try to detect format from magic bytes
    # WAV: RIFF....WAVE
    # WebM: 1A 45 DF A3
    # MP3: ID3 or FF FB
    # M4A: ftyp
    # OGG: 4F 67 67 53
    header = audio_bytes[:12] if len(audio_bytes) >= 12 else audio_bytes
    
    # Detect WebM/MKV format (from browser MediaRecorder)
    is_webm = header[:4] == b'\x1a\x45\xdf\xa3'
    # Detect OGG format
    is_ogg = header[:4] == b'OggS'
    # Detect MP4/M4A format
    is_mp4 = header[4:8] == b'ftyp'
    # Detect MP3 format
    is_mp3 = header[:3] == b'ID3' or (len(header) > 2 and header[0:1] == b'\xff')
    # Detect WAV format
    is_wav = header[:4] == b'RIFF' and header[8:12] == b'WAVE'
    
    logger.info(f"Audio format detection: webm={is_webm}, ogg={is_ogg}, mp4={is_mp4}, mp3={is_mp3}, wav={is_wav}")
    
    # For WebM, OGG, MP4, MP3 - use ffmpeg to convert to WAV first
    if is_webm or is_ogg or is_mp4 or is_mp3:
        logger.info("Using ffmpeg to convert audio to WAV format")
        
        # Write input to temp file
        with tempfile.NamedTemporaryFile(suffix='.webm' if is_webm else '.ogg' if is_ogg else '.m4a' if is_mp4 else '.mp3', delete=False) as tmp_in:
            tmp_in.write(audio_bytes)
            tmp_in_path = tmp_in.name
        
        # Output WAV file
        tmp_out_path = tempfile.mktemp(suffix='.wav')
        
        try:
            # Use ffmpeg to convert to WAV (mono, target sample rate)
            cmd = [
                'ffmpeg', '-y', '-i', tmp_in_path,
                '-ac', '1',  # Mono
                '-ar', str(target_sr),  # Target sample rate
                '-f', 'wav',
                '-acodec', 'pcm_f32le',  # 32-bit float PCM
                tmp_out_path
            ]
            
            logger.info(f"Running ffmpeg: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                logger.error(f"ffmpeg error: {result.stderr}")
                raise RuntimeError(f"ffmpeg failed: {result.stderr}")
            
            # Read the converted WAV file
            y, sr = sf.read(tmp_out_path, dtype='float32')
            
            logger.info(f"Loaded audio via ffmpeg: {len(y)} samples at {sr}Hz ({len(y)/sr:.2f}s)")
            return y, sr
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("ffmpeg conversion timed out")
        finally:
            # Clean up temp files
            if os.path.exists(tmp_in_path):
                os.unlink(tmp_in_path)
            if os.path.exists(tmp_out_path):
                os.unlink(tmp_out_path)
    
    # For WAV files - use soundfile directly
    if is_wav:
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        
        try:
            y, sr = sf.read(tmp_path, dtype='float32')
            
            # Convert to mono if stereo
            if len(y.shape) > 1:
                y = np.mean(y, axis=1)
            
            # Resample if needed using soxr
            if sr != target_sr:
                y = soxr.resample(y, sr, target_sr)
                sr = target_sr
            
            logger.info(f"Loaded audio: {len(y)} samples at {sr}Hz ({len(y)/sr:.2f}s)")
            return y, sr
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    # Fallback: try ffmpeg on unknown format
    logger.warning(f"Unknown audio format, trying ffmpeg. Header: {header.hex()}")
    
    with tempfile.NamedTemporaryFile(delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in_path = tmp_in.name
    
    tmp_out_path = tempfile.mktemp(suffix='.wav')
    
    try:
        cmd = [
            'ffmpeg', '-y', '-i', tmp_in_path,
            '-ac', '1',
            '-ar', str(target_sr),
            '-f', 'wav',
            '-acodec', 'pcm_f32le',
            tmp_out_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode != 0:
            raise ValueError(f"Could not load audio file. ffmpeg error: {result.stderr}. "
                           f"File header: {header.hex()}")
        
        y, sr = sf.read(tmp_out_path, dtype='float32')
        logger.info(f"Loaded audio via ffmpeg fallback: {len(y)} samples at {sr}Hz")
        return y, sr
        
    finally:
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
    }
