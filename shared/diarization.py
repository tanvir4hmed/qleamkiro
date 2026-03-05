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

def _segment_aux_features(y_segment: np.ndarray, sr: int):
    """
    Compute lightweight auxiliary features for segment classification.

    Returns:
        (f0_instability, zcr, rms_var_ratio)

    f0_instability — relative F0 standard deviation (std / median).
        High (>0.12) → irregular pitch → baby-like (cry, babble).
        Low  (<0.05) → very stable   → adult speech or sustained tone.

    zcr — zero-crossing rate per sample.
        ~0.018 for pure tone at 200 Hz @ 22 kHz.
        0.02–0.06 for voiced speech.
        High → fricatives / noise.

    rms_var_ratio — RMS energy std / mean across 20 ms frames.
        High (>0.5) → energy bursts → syllabic / cry-like.
        Low  (<0.25)→ steady energy → sustained tone or steady adult speech.
    """
    # F0 already computed by caller, but we only receive the segment here.
    # These are O(n) numpy operations — safe for up to 20 segments.
    try:
        # ZCR: sign changes per sample
        signs = np.sign(y_segment)
        zcr = float(np.sum(signs[:-1] != signs[1:])) / max(len(y_segment), 1)

        # RMS variance ratio across short frames
        frame_len = max(256, int(sr * 0.020))
        hop = max(128, frame_len // 2)
        n_frames = max(1, (len(y_segment) - frame_len) // hop + 1)
        frames_rms = np.array([
            float(np.sqrt(np.mean(y_segment[i * hop: i * hop + frame_len] ** 2)))
            for i in range(n_frames)
        ])
        rms_mean = float(np.mean(frames_rms)) + 1e-10
        rms_var_ratio = float(np.std(frames_rms)) / rms_mean

        return zcr, rms_var_ratio
    except Exception:
        return 0.05, 0.5   # Safe neutral defaults


def _is_sustained_tone(f0_instability: float, zcr: float, rms_var_ratio: float) -> bool:
    """
    Return True if segment looks like a sustained tone (hum / falsetto / held vowel).

    Adults humming or doing falsetto have very stable F0, low ZCR, and steady energy.
    This check flags the overlap zone (160–260 Hz) where adults and toddlers meet.
    """
    return (
        f0_instability < 0.05      # Pitch barely fluctuates
        and zcr < 0.025            # Few zero crossings → periodic signal
        and rms_var_ratio < 0.30   # Steady energy
    )


def classify_segment(y_segment: np.ndarray, sr: int) -> str:
    """
    Classify a single voiced segment using F0 + auxiliary acoustic features.

    Conservative by design: defaults to baby classification unless there is
    strong multi-feature evidence for an adult speaker.

    Improvements over pure F0 threshold approach:
      - Computes F0 instability (std/median): high → baby-like irregularity
      - Computes ZCR: very low → sustained periodic tone (possible adult hum)
      - Computes energy variance ratio: high → cry / babble pattern
      - Sustained-tone detection: ambiguous zones return "unknown" instead of
        misclassifying adult humming as toddler/child
      - Adult classification requires low F0 (<160 Hz) AND feature stability

    Classification categories:
        "newborn"      — F0 > 400 Hz  (newborn cry — almost certain)
        "infant"       — F0 280–400 Hz (infant babble/cry)
        "toddler"      — F0 220–280 Hz (toddler speech; stable tone → unknown)
        "child"        — F0 160–220 Hz (child speech; stable tone → unknown)
        "adult_female" — F0 130–160 Hz + stable features
        "adult_male"   — F0 <  130 Hz
        "unknown"      — no reliable F0, or sustained tone in overlap zone

    Returns: one of the seven labels above.
    """
    try:
        import librosa

        min_samples = int(sr * 0.15)
        if len(y_segment) < min_samples:
            return "unknown"

        # --- F0 estimation via YIN ---
        f0 = librosa.yin(
            y_segment,
            fmin=librosa.note_to_hz("C2"),   # ~65 Hz
            fmax=librosa.note_to_hz("C7"),   # ~2093 Hz
        )
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])

        if len(f0_voiced) == 0:
            return "unknown"

        f0_median = float(np.median(f0_voiced))
        f0_std    = float(np.std(f0_voiced))
        f0_instability = f0_std / (f0_median + 1e-6)

        # Auxiliary features (lightweight O(n) operations)
        zcr, rms_var_ratio = _segment_aux_features(y_segment, sr)

        # ----------------------------------------------------------------
        # Classification — high F0 zones are unambiguously baby
        # ----------------------------------------------------------------

        # Clear newborn cry: very high fundamental
        if f0_median > 400:
            return "newborn"

        # Clear infant range: 280–400 Hz (only extreme adult falsetto reaches here)
        if f0_median > 280:
            return "infant"

        # Toddler range: 220–280 Hz
        if f0_median > 220:
            # Sustained tone in this range could be adult falsetto / hum → unknown
            if _is_sustained_tone(f0_instability, zcr, rms_var_ratio):
                return "unknown"
            return "toddler"

        # Overlap zone: 160–220 Hz (child / adult-female boundary)
        if f0_median > 160:
            # Sustained tone → adult humming most likely → mark ambiguous
            if _is_sustained_tone(f0_instability, zcr, rms_var_ratio):
                return "unknown"
            # Baby-like instability → child/toddler
            if f0_instability > 0.10 or rms_var_ratio > 0.55:
                return "child"
            # Moderate — conservative default
            return "child"

        # Lower overlap: 130–160 Hz (adult_female / low-child boundary)
        if f0_median > 130:
            # Require stable features before calling adult_female
            if f0_instability < 0.08 and zcr > 0.018:
                return "adult_female"
            return "child"   # Conservative

        # Clear adult male: ≤ 130 Hz
        if f0_median > 85:
            return "adult_male"

        if f0_median > 0:
            return "adult_male"

        return "unknown"

    except Exception as e:
        logger.warning(f"Segment classification failed: {e}")
        return "unknown"


def classify_segment_detailed(y_segment: np.ndarray, sr: int) -> Dict:
    """
    Detailed segment classification with confidence score and auxiliary features.

    Returns:
        {
            "label":           str,
            "f0_median":       float,
            "f0_instability":  float,   # std / median — high → irregular (baby-like)
            "confidence":      float,
        }
    """
    try:
        import librosa

        min_samples = int(sr * 0.15)
        if len(y_segment) < min_samples:
            return {"label": "unknown", "f0_median": 0.0, "f0_instability": 0.0, "confidence": 0.0}

        f0 = librosa.yin(
            y_segment,
            fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C7"),
        )
        f0_voiced = f0[~np.isnan(f0)] if f0 is not None else np.array([])

        if len(f0_voiced) == 0:
            return {"label": "unknown", "f0_median": 0.0, "f0_instability": 0.0, "confidence": 0.0}

        f0_median = float(np.median(f0_voiced))
        f0_std    = float(np.std(f0_voiced))
        f0_instability = f0_std / (f0_median + 1e-6)

        # Confidence: higher for more stable F0 AND clearer class boundary
        # (lower instability = more confident in any direction)
        stability_conf = 1.0 - min(f0_instability, 1.0)

        label = classify_segment(y_segment, sr)

        # "unknown" segments have near-zero confidence
        if label == "unknown":
            stability_conf = 0.0

        return {
            "label":          label,
            "f0_median":      round(f0_median, 1),
            "f0_instability": round(f0_instability, 3),
            "confidence":     round(stability_conf, 3),
        }

    except Exception as e:
        logger.warning(f"Detailed segment classification failed: {e}")
        return {"label": "unknown", "f0_median": 0.0, "f0_instability": 0.0, "confidence": 0.0}


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
    Concatenate all baby-labeled segments for the active 0-3 month scope.

    Falls back to full audio if no baby segments are found — ensures
    feature extraction always has input to work with.

    Returns:
        np.ndarray: concatenated baby audio samples
    """
    baby_labels = ("newborn", "infant")
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
