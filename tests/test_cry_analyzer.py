"""Tests for shared/cry_analyzer.py."""
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from cry_analyzer import analyze_cry


def test_analyze_cry_uses_model_when_available():
    features = {
        "f0_mean": 420.0,
        "f0_instability": 0.08,
        "spectral_centroid": 1700.0,
        "zcr": 0.02,
        "energy_variability": 0.35,
        "rms_mean": 0.09,
        "voiced_fraction": 0.72,
        "duration_s": 4.2,
    }
    classifier_result = {
        "using_model": True,
        "primary_emotion": "gas",
        "confidence": 0.81,
        "emotion_probabilities": {"gas": 0.81, "hungry": 0.10, "discomfort": 0.09},
        "top_emotions": [{"key": "gas", "score": 0.81}, {"key": "hungry", "score": 0.10}],
        "model_version": "phase4-v2",
    }

    result = analyze_cry(features, classifier_result=classifier_result)

    assert result["primary_emotion"] == "gas"
    assert result["confidence"] == 0.81
    assert result["debug_trace"]["model_version"] == "phase4-v2"


def test_analyze_cry_rule_fallback_is_not_constant_discomfort():
    hungry_like = {
        "f0_mean": 420.0,
        "f0_instability": 0.08,
        "spectral_centroid": 1700.0,
        "zcr": 0.02,
        "energy_variability": 0.35,
        "rms_mean": 0.09,
        "voiced_fraction": 0.72,
        "duration_s": 4.2,
    }
    pain_like = {
        "f0_mean": 780.0,
        "f0_instability": 0.32,
        "spectral_centroid": 3400.0,
        "zcr": 0.045,
        "energy_variability": 0.07,
        "rms_mean": 0.24,
        "voiced_fraction": 0.93,
        "duration_s": 3.2,
    }

    hungry_result = analyze_cry(hungry_like, classifier_result=None)
    pain_result = analyze_cry(pain_like, classifier_result=None)

    assert hungry_result["debug_trace"]["model_version"] == "rule_based_basic"
    assert pain_result["debug_trace"]["model_version"] == "rule_based_basic"
    assert hungry_result["primary_emotion"] != pain_result["primary_emotion"]


def test_analyze_cry_uses_age_specific_variant_and_dunstan_gating():
    classifier_result = {
        "using_model": True,
        "primary_emotion": "hungry",
        "confidence": 0.74,
        "emotion_probabilities": {"hungry": 0.74, "tired": 0.15, "discomfort": 0.11},
        "top_emotions": [{"key": "hungry", "score": 0.74}],
        "model_version": "phase4-v2",
    }

    newborn_result = analyze_cry({}, age_days=45, classifier_result=classifier_result)
    toddler_result = analyze_cry({}, age_days=400, classifier_result=classifier_result)

    assert newborn_result["age_bracket"] == "0_90"
    assert newborn_result["dunstan_sound"] == "neh"
    assert "feeding reflex" in newborn_result["what_means"]

    assert toddler_result["age_bracket"] == "366_730"
    assert toddler_result["dunstan_sound"] is None
    assert "multiple channels" in toddler_result["what_means"]
