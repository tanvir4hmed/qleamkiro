"""
Qleam — Audio Diarization (Phase 2)

Energy-based speaker segmentation and per-segment infant/adult labeling.
No external diarization library required — runs inside Lambda.

Pipeline:
  1. segment_audio_by_energy()  — split voiced regions by silence gaps
  2. classify_segment()          — F0-based infant/adult/child label per segment
  3. diarize()                   — full result with summary stats
  4. extract_baby_audio()        — concatenate all infant-labeled chunks
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
FRAME_DURATION_MS: int = 30       # RMS analysis frame size
SILENCE_THRESHOLD_FACTOR: float = 0.08  # Fraction of peak RMS → silence
MIN_SEGMENT_DURATION_MS: int = 250      # Discard shorter segments
MIN_SILENCE_GAP_MS: int = 150           # Gap required to split segments
MAX_SEGMENTS_TO_CLASSIFY: int = 20      # Cap to keep Lambda latency bounded


# ---------------------------------------------------------------------------
# Energy-based segmentation
# ---------------------------------------------------------------------------

def _frame_rms(y: np.ndarray, frame_len: int, hop_len: int) -> np.ndarray:
    """Compute per-frame RMS energy without librosa dependency."""
    n_frames = max(1, 1 + (len(y) - frame_len) // hop_len)
    rms = np.zeros(n_frames)
    for i in range(n_frames):
        start = i * hop_len
        chunk = y[start: start + frame_len]
        rms[i] = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) > 0 else 0.0
    return rms


def segment_audio_by_energy(
    y: np.ndarray,
    sr: int,
    frame_ms: int = FRAME_DURATION_MS,
    silence_factor: float = SILENCE_THRESHOLD_FACTOR,
    min_segment_ms: int = MIN_SEGMENT_DURATION_MS,
    min_silence_ms: int = MIN_SILENCE_GAP_MS,
) -> List[Tuple[int, int]]:
    """
    Split audio into voiced regions using RMS energy thresholding.

    Returns:
        List of (start_sample, end_sample) for each voiced segment.
    """
    frame_len = int(sr * frame_ms / 1000)
    hop_len = max(1, frame_len // 2)

    if len(y) < frame_len:
        return [(0, len(y))]

    rms = _frame_rms(y, frame_len, hop_len)
    peak_rms = float(np.max(rms))

    if peak_rms == 0:
        return []

    threshold = silence_factor * peak_rms
    voiced = rms > threshold

    # Minimum lengths in frames
    min_seg_frames = max(1, int(min_segment_ms / (frame_ms / 2)))
    min_sil_frames = max(1, int(min_silence_ms / (frame_ms / 2)))

    segments: List[Tuple[int, int]] = []
    in_segment = False
    seg_start_frame = 0
    silence_run = 0

    for i, v in enumerate(voiced):
        if v:
            if not in_segment:
                seg_start_frame = i
                in_segment = True
            silence_run = 0
        else:
            if in_segment:
                silence_run += 1
                if silence_run >= min_sil_frames:
                    seg_end_frame = i - silence_run + 1
                    if seg_end_frame - seg_start_frame >= min_seg_frames:
                        segments.append((
                            int(seg_start_frame * hop_len),
                            min(int(seg_end_frame * hop_len), len(y)),
                        ))
                    in_segment = False
                    silence_run = 0

    # Final segment
    if in_segment:
        seg_end_frame = len(voiced)
        if seg_end_frame - seg_start_frame >= min_seg_frames:
            segments.append((
                int(seg_start_frame * hop_len),
                len(y),
            ))

    return segments


# ---------------------------------------------------------------------------
# Per-segment speaker classification
# ---------------------------------------------------------------------------

def classify_segment(y_segment: np.ndarray, sr: int) -> str:
    """
    Classify a single voiced segment using median F0.

    F0 ranges (approximate):
        infant (0-24m):  F0 > 200 Hz  (crying 300-600 Hz, babble 250-450 Hz)
        child  (2-6y):   F0 150-250 Hz
        adult female:    F0 165-255 Hz
        adult male:      F0  85-180 Hz

    Classification boundaries:
        > 250 Hz  → "infant"
        200-250   → "infant"   (overlaps older infant / young child)
        150-200   → "child"    (ambiguous — toddler or adult female)
        < 150 Hz  → "adult"
        no pitch  → "unknown"

    Returns: "infant" | "child" | "adult" | "unknown"
    """
    try:
        import librosa

        min_samples = int(sr * 0.15)  # Need at least 150ms for reliable F0
        if len(y_segment) < min_samples:
            return "unknown"

        f0 = librosa.yin(
            y_segment,
            fmin=librosa.note_to_hz("C2"),   # ~65 Hz
            fmax=librosa.note_to_hz("C7"),   # ~2093 Hz
        )
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])

        if len(f0_voiced) == 0:
            return "unknown"

        f0_median = float(np.median(f0_voiced))

        if f0_median > 200:
            return "infant"
        elif f0_median > 150:
            return "child"   # toddler / adult female / ambiguous
        elif f0_median > 0:
            return "adult"
        return "unknown"

    except Exception as e:
        logger.warning(f"Segment classification failed: {e}")
        return "unknown"


# ---------------------------------------------------------------------------
# Full diarization pipeline
# ---------------------------------------------------------------------------

def diarize(y: np.ndarray, sr: int) -> Dict:
    """
    Full diarization: segment audio → label each segment → summary.

    Returns:
        {
            "segments": [
                {
                    "start_s": float,
                    "end_s": float,
                    "duration_s": float,
                    "label": "infant" | "child" | "adult" | "unknown"
                },
                ...
            ],
            "baby_audio_fraction": float,   # fraction of total duration that is infant
            "total_segments": int,
            "baby_segments": int,
            "adult_segments_detected": int,
        }
    """
    total_duration = len(y) / max(sr, 1)
    raw_segments = segment_audio_by_energy(y, sr)

    # Limit how many segments we classify (performance cap)
    segments_to_classify = raw_segments[:MAX_SEGMENTS_TO_CLASSIFY]

    labeled_segments = []
    baby_duration = 0.0
    adult_count = 0

    for start_s, end_s in segments_to_classify:
        y_seg = y[start_s:end_s]
        label = classify_segment(y_seg, sr)

        t_start = start_s / sr
        t_end = end_s / sr
        seg_dur = t_end - t_start

        labeled_segments.append({
            "start_s": round(t_start, 3),
            "end_s": round(t_end, 3),
            "duration_s": round(seg_dur, 3),
            "label": label,
        })

        if label == "infant":
            baby_duration += seg_dur
        elif label == "adult":
            adult_count += 1

    baby_fraction = baby_duration / max(total_duration, 0.001)
    baby_seg_count = sum(1 for s in labeled_segments if s["label"] == "infant")

    return {
        "segments": labeled_segments,
        "baby_audio_fraction": round(baby_fraction, 4),
        "total_segments": len(labeled_segments),
        "baby_segments": baby_seg_count,
        "adult_segments_detected": adult_count,
    }


# ---------------------------------------------------------------------------
# Baby audio extraction
# ---------------------------------------------------------------------------

def extract_baby_audio(y: np.ndarray, sr: int, diarization_result: Dict) -> np.ndarray:
    """
    Concatenate all infant-labeled (and unknown) segments.

    Falls back to full audio if no infant segments are found — ensures
    feature extraction always has input to work with.

    Returns:
        np.ndarray: concatenated baby audio samples
    """
    infant_chunks = []

    for seg in diarization_result.get("segments", []):
        if seg["label"] in ("infant", "unknown"):
            start_sample = int(seg["start_s"] * sr)
            end_sample = int(seg["end_s"] * sr)
            chunk = y[start_sample:end_sample]
            if len(chunk) > 0:
                infant_chunks.append(chunk)

    if infant_chunks:
        return np.concatenate(infant_chunks)

    # No infant segments found → use full audio with a warning
    logger.warning("No infant segments found in diarization — using full audio")
    return y
