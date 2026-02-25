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
    Classify a single voiced segment using F0 and basic acoustic features.

    IMPORTANT: Default to baby classification unless there's STRONG adult evidence.
    Baby sounds (crying, cooing, babbling) are much more common in this app.
    Adult detection should require very low F0 (< 150 Hz) as definitive evidence.

    Classification categories:
        "newborn"       - F0 > 400 Hz (crying baby 0-3 months)
        "infant"        - F0 280-400 Hz (baby 3-12 months) - includes low crying
        "toddler"       - F0 220-280 Hz (child 1-2 years)
        "child"         - F0 180-220 Hz (child 2-5 years)
        "adult_female"  - F0 150-180 Hz (adult female) - STRICT threshold
        "adult_male"    - F0 < 150 Hz (adult male) - STRONG evidence required
        "unknown"       - no reliable F0 detected

    Returns: "newborn" | "infant" | "toddler" | "child" | "adult_female" | "adult_male" | "unknown"
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

        # LENIENT baby-first classification
        # Default to baby unless F0 is very low (strong adult evidence)
        if f0_median > 450:
            return "newborn"       # High-pitch cry - definitely baby
        elif f0_median > 400:
            return "newborn"       # Newborn crying range
        elif f0_median > 280:
            return "infant"        # Infant cooing, babbling, low crying
        elif f0_median > 220:
            return "toddler"       # Toddler range
        elif f0_median > 180:
            return "child"         # Young child
        elif f0_median > 150:
            return "child"         # Still likely child (lenient)
        elif f0_median > 120:
            # Gray zone - could be low child or high adult female
            # Default to child (more likely in baby monitoring app)
            return "child"
        elif f0_median > 85:
            # Very low F0 - strong adult male evidence
            return "adult_male"
        elif f0_median > 0:
            return "adult_male"    # Deep adult male
        return "unknown"

    except Exception as e:
        logger.warning(f"Segment classification failed: {e}")
        return "unknown"


def classify_segment_detailed(y_segment: np.ndarray, sr: int) -> Dict:
    """
    Detailed segment classification with confidence score.
    
    Returns:
        {
            "label": str,
            "f0_median": float,
            "confidence": float,
        }
    """
    try:
        import librosa

        min_samples = int(sr * 0.15)
        if len(y_segment) < min_samples:
            return {"label": "unknown", "f0_median": 0.0, "confidence": 0.0}

        f0 = librosa.yin(
            y_segment,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])

        if len(f0_voiced) == 0:
            return {"label": "unknown", "f0_median": 0.0, "confidence": 0.0}

        f0_median = float(np.median(f0_voiced))
        f0_std = float(np.std(f0_voiced))
        
        # Lower std = more confident classification
        confidence = 1.0 - min(f0_std / f0_median if f0_median > 0 else 1.0, 1.0)
        
        label = classify_segment(y_segment, sr)
        
        return {
            "label": label,
            "f0_median": round(f0_median, 1),
            "confidence": round(confidence, 3),
        }

    except Exception as e:
        logger.warning(f"Detailed segment classification failed: {e}")
        return {"label": "unknown", "f0_median": 0.0, "confidence": 0.0}


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
                    "label": str
                },
                ...
            ],
            "baby_audio_fraction": float,    # newborn + infant + toddler
            "child_audio_fraction": float,   # child (2-5 years)
            "adult_audio_fraction": float,   # adult_male + adult_female
            "total_segments": int,
            "newborn_segments": int,
            "infant_segments": int,
            "toddler_segments": int,
            "child_segments": int,
            "adult_segments_detected": int,
            "primary_speaker": str,          # most common speaker type
        }
    """
    total_duration = len(y) / max(sr, 1)
    raw_segments = segment_audio_by_energy(y, sr)

    # Limit how many segments we classify (performance cap)
    segments_to_classify = raw_segments[:MAX_SEGMENTS_TO_CLASSIFY]

    labeled_segments = []
    
    # Duration by category
    newborn_duration = 0.0
    infant_duration = 0.0
    toddler_duration = 0.0
    child_duration = 0.0
    adult_male_duration = 0.0
    adult_female_duration = 0.0
    
    # Segment counts by category
    newborn_count = 0
    infant_count = 0
    toddler_count = 0
    child_count = 0
    adult_male_count = 0
    adult_female_count = 0

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

        # Track durations and counts by category
        if label == "newborn":
            newborn_duration += seg_dur
            newborn_count += 1
        elif label == "infant":
            infant_duration += seg_dur
            infant_count += 1
        elif label == "toddler":
            toddler_duration += seg_dur
            toddler_count += 1
        elif label == "child":
            child_duration += seg_dur
            child_count += 1
        elif label == "adult_male":
            adult_male_duration += seg_dur
            adult_male_count += 1
        elif label == "adult_female":
            adult_female_duration += seg_dur
            adult_female_count += 1

    # Calculate fractions
    baby_duration = newborn_duration + infant_duration + toddler_duration
    adult_duration = adult_male_duration + adult_female_duration
    
    baby_fraction = baby_duration / max(total_duration, 0.001)
    child_fraction = child_duration / max(total_duration, 0.001)
    adult_fraction = adult_duration / max(total_duration, 0.001)
    
    # Determine primary speaker
    durations = {
        "newborn": newborn_duration,
        "infant": infant_duration,
        "toddler": toddler_duration,
        "child": child_duration,
        "adult_male": adult_male_duration,
        "adult_female": adult_female_duration,
    }
    primary_speaker = max(durations, key=durations.get) if max(durations.values()) > 0 else "unknown"

    return {
        "segments": labeled_segments,
        "baby_audio_fraction": round(baby_fraction, 4),
        "child_audio_fraction": round(child_fraction, 4),
        "adult_audio_fraction": round(adult_fraction, 4),
        "total_segments": len(labeled_segments),
        "newborn_segments": newborn_count,
        "infant_segments": infant_count,
        "toddler_segments": toddler_count,
        "child_segments": child_count,
        "adult_segments_detected": adult_male_count + adult_female_count,
        "primary_speaker": primary_speaker,
    }


# ---------------------------------------------------------------------------
# Baby audio extraction
# ---------------------------------------------------------------------------

def extract_baby_audio(y: np.ndarray, sr: int, diarization_result: Dict) -> np.ndarray:
    """
    Concatenate all baby-labeled segments (newborn, infant, toddler, child).
    
    Also includes "unknown" segments in case they are baby sounds.

    Falls back to full audio if no baby segments are found — ensures
    feature extraction always has input to work with.

    Returns:
        np.ndarray: concatenated baby audio samples
    """
    baby_labels = ("newborn", "infant", "toddler", "child", "unknown")
    baby_chunks = []

    for seg in diarization_result.get("segments", []):
        if seg["label"] in baby_labels:
            start_sample = int(seg["start_s"] * sr)
            end_sample = int(seg["end_s"] * sr)
            chunk = y[start_sample:end_sample]
            if len(chunk) > 0:
                baby_chunks.append(chunk)

    if baby_chunks:
        return np.concatenate(baby_chunks)

    # No baby segments found → use full audio with a warning
    logger.warning("No baby segments found in diarization — using full audio")
    return y
