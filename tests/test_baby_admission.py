"""
Unit tests for baby admission gate.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../shared"))

from baby_admission import evaluate_baby_admission


def test_rejects_critical_no_sound():
    result = evaluate_baby_admission(
        quality_gate={
            "passed": False,
            "issues": ["no_signal", "no_vocal_activity_detected"],
            "voiced_energy_fraction": 0.0,
            "silence_ratio": 1.0,
        },
        diarization={},
        biological={},
        age_classification={},
        rich_features={},
    )
    assert result["status"] == "REJECT_NO_SOUND"
    assert result["baby_confidence"] == 0.0


def test_rejects_hard_adult_signal():
    result = evaluate_baby_admission(
        quality_gate={"passed": True, "issues": []},
        diarization={"adult_audio_fraction": 0.7, "baby_audio_fraction": 0.1, "adult_segments_detected": 3},
        biological={
            "mimicry_suspected": True,
            "speaker_type": "adult",
            "speaker_category": "adult_male",
            "bio_confidence": 0.86,
            "spoof_likelihood": 0.82,
        },
        age_classification={"final_class": "adult_male", "confidence": 0.90, "is_adult": True},
        rich_features={"cry_fraction": 0.0, "f0_voiced_fraction": 0.05},
    )
    assert result["status"] == "REJECT_ADULT"
    assert result["reason"] == "adult"


def test_passes_confident_baby_signal():
    result = evaluate_baby_admission(
        quality_gate={"passed": True, "issues": []},
        diarization={"adult_audio_fraction": 0.05, "baby_audio_fraction": 0.82, "adult_segments_detected": 0},
        biological={
            "mimicry_suspected": False,
            "speaker_type": "infant",
            "speaker_category": "infant",
            "is_infant": True,
            "bio_confidence": 0.81,
            "spoof_likelihood": 0.05,
        },
        age_classification={
            "final_class": "infant",
            "confidence": 0.84,
            "is_adult": False,
            "voice_type": "cry_like",
            "voice_type_confidence": 0.87,
            "baby_confidence": 0.88,
        },
        rich_features={"cry_fraction": 0.23, "f0_voiced_fraction": 0.56},
    )
    assert result["status"] == "BABY_PASS"
    assert result["baby_confidence"] >= 0.62
