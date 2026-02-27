"""
Qleam — Baby Admission Gate

Dedicated pre-processing filter for baby-vocalization sessions.
Only BABY_PASS sessions should flow into core clustering/learning pipelines.
"""
from typing import Any, Dict, List

from constants import (
    ADMISSION_ADULT_AGE_CONFIDENCE_MIN,
    ADMISSION_ADULT_BIO_CONFIDENCE_MIN,
    ADMISSION_ADULT_FRACTION_HARD_MIN,
    ADMISSION_ADULT_SEGMENTS_HARD_MIN,
    ADMISSION_NOISE_BABY_FRACTION_MAX,
    ADMISSION_NOISE_CRY_FRACTION_MAX,
    ADMISSION_NOISE_VOICE_CONF_MIN,
    ADMISSION_NO_SIGNAL_SILENCE_MIN,
    ADMISSION_NO_SIGNAL_VOICED_MAX,
    ADMISSION_PASS_CONFIDENCE_MIN,
    ADMISSION_STATUS_BABY_PASS,
    ADMISSION_STATUS_PASS_UNCERTAIN,
    ADMISSION_STATUS_REJECT_ADULT,
    ADMISSION_STATUS_REJECT_NON_BABY,
    ADMISSION_STATUS_REJECT_NO_SOUND,
    ADMISSION_UNCERTAIN_CONFIDENCE_MIN,
)

_NO_SOUND_PREFIXES = ("no_signal", "too_short:")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _critical_no_sound(quality_gate: Dict[str, Any]) -> bool:
    if not isinstance(quality_gate, dict):
        return False
    issues = quality_gate.get("issues", []) or []
    if any(str(issue).startswith(prefix) for issue in issues for prefix in _NO_SOUND_PREFIXES):
        return True
    if "no_vocal_activity_detected" in issues:
        voiced = _f(quality_gate.get("voiced_energy_fraction"), 0.0)
        silence = _f(quality_gate.get("silence_ratio"), 1.0)
        if voiced <= ADMISSION_NO_SIGNAL_VOICED_MAX and silence >= ADMISSION_NO_SIGNAL_SILENCE_MIN:
            return True
    return False


def evaluate_baby_admission(
    quality_gate: Dict[str, Any],
    diarization: Dict[str, Any],
    biological: Dict[str, Any],
    age_classification: Dict[str, Any],
    rich_features: Dict[str, Any],
    routing: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    Evaluate whether a session should enter the core baby insight pipeline.

    Returns:
        {
          "status": str,
          "baby_confidence": float,
          "reason": str,
          "message": str,
          "reasons": List[str],
          "signals": {...}
        }
    """
    quality_gate = quality_gate or {}
    diarization = diarization or {}
    biological = biological or {}
    age_classification = age_classification or {}
    rich_features = rich_features or {}
    routing = routing or {}

    reasons: List[str] = []

    # --- Hard no-sound reject ---
    if _critical_no_sound(quality_gate):
        issues = quality_gate.get("issues", []) or []
        return {
            "status": ADMISSION_STATUS_REJECT_NO_SOUND,
            "baby_confidence": 0.0,
            "reason": "no_sound",
            "message": "No reliable vocal signal detected.",
            "reasons": [str(i) for i in issues] if issues else ["critical_no_sound"],
            "signals": {},
        }

    speaker_type = str(biological.get("speaker_type", "") or "").strip().lower()
    speaker_category = str(biological.get("speaker_category", "") or "").strip().lower()
    mimicry_suspected = bool(biological.get("mimicry_suspected", False))
    bio_confidence = _f(biological.get("bio_confidence"), 0.0)
    spoof_likelihood = _f(biological.get("spoof_likelihood"), 0.0)

    age_class = str(age_classification.get("final_class", "") or "").strip().lower()
    age_conf = _f(age_classification.get("confidence"), 0.0)
    age_baby_conf = _f(age_classification.get("baby_confidence"), -1.0)
    age_is_adult = bool(age_classification.get("is_adult", False))
    voice_type = str(age_classification.get("voice_type", "") or "").strip().lower()
    voice_type_conf = _f(age_classification.get("voice_type_confidence"), 0.0)

    adult_fraction = _f(diarization.get("adult_audio_fraction"), 0.0)
    baby_fraction = _f(diarization.get("baby_audio_fraction"), 0.0)
    adult_segments = int(_f(diarization.get("adult_segments_detected"), 0))

    cry_fraction = _f(rich_features.get("cry_fraction"), 0.0)
    voiced_fraction = _f(rich_features.get("f0_voiced_fraction"), 0.0)

    # --- Hard adult reject ---
    adult_by_bio = (
        mimicry_suspected
        or speaker_type == "adult"
        or speaker_category in ("adult_female", "adult_male")
    ) and max(bio_confidence, spoof_likelihood) >= ADMISSION_ADULT_BIO_CONFIDENCE_MIN
    adult_by_age = age_is_adult and age_conf >= ADMISSION_ADULT_AGE_CONFIDENCE_MIN
    adult_by_diar = (
        adult_segments >= ADMISSION_ADULT_SEGMENTS_HARD_MIN
        and adult_fraction >= ADMISSION_ADULT_FRACTION_HARD_MIN
    )
    adult_by_routing = str(routing.get("analysis_type", "")).lower().strip() == "adult_mimicry_flagged"

    if adult_by_bio or adult_by_age or adult_by_diar or adult_by_routing:
        if adult_by_bio:
            reasons.append("adult_by_bio")
        if adult_by_age:
            reasons.append("adult_by_age")
        if adult_by_diar:
            reasons.append("adult_by_diar")
        if adult_by_routing:
            reasons.append("adult_by_routing")
        return {
            "status": ADMISSION_STATUS_REJECT_ADULT,
            "baby_confidence": 0.0,
            "reason": "adult",
            "message": "Adult voice evidence is strong.",
            "reasons": reasons,
            "speaker_type": speaker_type or "adult",
            "speaker_category": speaker_category or "adult",
            "signals": {
                "bio_confidence": round(bio_confidence, 3),
                "spoof_likelihood": round(spoof_likelihood, 3),
                "adult_fraction": round(adult_fraction, 3),
                "baby_fraction": round(baby_fraction, 3),
                "adult_segments": adult_segments,
                "age_class": age_class,
                "age_confidence": round(age_conf, 3),
            },
        }

    # --- Hard non-baby reject (noise / environmental clip) ---
    noise_like = (
        voice_type == "noise"
        and voice_type_conf >= ADMISSION_NOISE_VOICE_CONF_MIN
        and baby_fraction <= ADMISSION_NOISE_BABY_FRACTION_MAX
        and cry_fraction <= ADMISSION_NOISE_CRY_FRACTION_MAX
    )
    if noise_like:
        return {
            "status": ADMISSION_STATUS_REJECT_NON_BABY,
            "baby_confidence": 0.0,
            "reason": "non_baby_noise",
            "message": "Non-baby acoustic pattern detected.",
            "reasons": ["noise_voice_type_hard"],
            "signals": {
                "voice_type": voice_type,
                "voice_type_confidence": round(voice_type_conf, 3),
                "adult_fraction": round(adult_fraction, 3),
                "baby_fraction": round(baby_fraction, 3),
                "cry_fraction": round(cry_fraction, 3),
            },
        }

    # --- Baby confidence synthesis ---
    # Age-class contribution
    age_score = 0.0
    if age_class in ("newborn", "infant", "toddler"):
        age_score = age_conf
    elif age_class == "child":
        age_score = min(0.5, age_conf * 0.5)
    if age_baby_conf >= 0.0:
        age_score = max(age_score, _clamp01(age_baby_conf))

    # Bio contribution
    bio_score = 0.0
    if bool(biological.get("is_infant", False)) and not mimicry_suspected:
        bio_score = max(0.5, bio_confidence)
    elif speaker_type in ("infant", "toddler"):
        bio_score = bio_confidence * 0.8

    # Diarization contribution
    diar_score = _clamp01(baby_fraction - (adult_fraction * 0.7))

    # Rich feature contribution
    cry_score = _clamp01((cry_fraction - 0.02) / 0.20)
    voice_score = _clamp01((voiced_fraction - 0.05) / 0.35)
    rich_score = max(cry_score, voice_score)
    if voice_type == "noise" and voice_type_conf >= 0.70:
        rich_score *= 0.3

    baby_confidence = round(
        _clamp01(0.35 * age_score + 0.35 * bio_score + 0.20 * diar_score + 0.10 * rich_score),
        3,
    )

    status = ADMISSION_STATUS_PASS_UNCERTAIN
    reason = "uncertain"
    message = "Baby signal is present but below the confident pass threshold."

    if baby_confidence >= ADMISSION_PASS_CONFIDENCE_MIN:
        status = ADMISSION_STATUS_BABY_PASS
        reason = "baby_confident"
        message = "Baby vocalization confidence passed."
    elif baby_confidence < ADMISSION_UNCERTAIN_CONFIDENCE_MIN:
        status = ADMISSION_STATUS_REJECT_NON_BABY
        reason = "low_baby_confidence"
        message = "Baby confidence is too low for core processing."

    return {
        "status": status,
        "baby_confidence": baby_confidence,
        "reason": reason,
        "message": message,
        "reasons": reasons,
        "speaker_type": speaker_type or "unknown",
        "speaker_category": speaker_category or "unknown",
        "signals": {
            "age_class": age_class,
            "age_confidence": round(age_conf, 3),
            "bio_confidence": round(bio_confidence, 3),
            "spoof_likelihood": round(spoof_likelihood, 3),
            "adult_fraction": round(adult_fraction, 3),
            "baby_fraction": round(baby_fraction, 3),
            "adult_segments": adult_segments,
            "voice_type": voice_type,
            "voice_type_confidence": round(voice_type_conf, 3),
            "cry_fraction": round(cry_fraction, 3),
            "voiced_fraction": round(voiced_fraction, 3),
        },
    }
