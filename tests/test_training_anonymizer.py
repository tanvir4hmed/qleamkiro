"""Tests for shared/training_anonymizer.py"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from training_anonymizer import (
    get_blend_weights,
    apply_quality_gates,
    MIN_SNR_DB,
    MIN_DURATION_S,
    MIN_CONFIDENCE_FOR_CONFIRM,
)


class TestGetBlendWeights:
    def test_zero_samples(self):
        w = get_blend_weights(0)
        assert w["public_weight"] == 1.0
        assert w["our_weight"] == 0.0

    def test_under_30(self):
        w = get_blend_weights(20)
        assert w["public_weight"] == 1.0
        assert w["our_weight"] == 0.0

    def test_30_to_99(self):
        w = get_blend_weights(50)
        assert w["public_weight"] == 0.7
        assert w["our_weight"] == 0.3

    def test_100_to_299(self):
        w = get_blend_weights(200)
        assert w["public_weight"] == 0.4
        assert w["our_weight"] == 0.6

    def test_300_plus(self):
        w = get_blend_weights(500)
        assert w["public_weight"] == 0.15
        assert w["our_weight"] == 0.85

    def test_weights_sum_to_one(self):
        for n in [0, 10, 50, 150, 500, 1000]:
            w = get_blend_weights(n)
            assert abs(w["public_weight"] + w["our_weight"] - 1.0) < 1e-6


class TestApplyQualityGates:
    def _make_session(self, snr=15.0, duration=5.0, sound_type="cry",
                      confidence=0.8, session_id="sess-123"):
        return {
            "session_id": session_id,
            "quality_gate": {"snr_db": snr},
            "duration_seconds": duration,
            "sound_type": sound_type,
            "classifier_result": {"confidence": confidence},
        }

    def _make_table_stub(self, has_record=True, already_confirmed=False):
        """Minimal stub for training_features_table."""
        class FakeTable:
            def scan(self, **kwargs):
                if not has_record:
                    return {"Items": []}
                item = {
                    "feature_id": "feat-001",
                    "session_id": "sess-123",
                }
                if already_confirmed:
                    item["confirmed_emotion"] = "hungry"
                return {"Items": [item]}
        return FakeTable()

    def test_accepted(self):
        session = self._make_session()
        table = self._make_table_stub()
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is True
        assert result["feature_id"] == "feat-001"

    def test_no_embeddings(self):
        session = self._make_session()
        table = self._make_table_stub(has_record=False)
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert result["rejection_reason"] == "no_embeddings"

    def test_skip_label(self):
        session = self._make_session()
        table = self._make_table_stub()
        result = apply_quality_gates(session, "skip", True, table)
        assert result["accepted"] is False
        assert result["rejection_reason"] == "feedback_skip"

    def test_low_snr(self):
        session = self._make_session(snr=5.0)
        table = self._make_table_stub()
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert "low_snr" in result["rejection_reason"]

    def test_short_duration(self):
        session = self._make_session(duration=1.5)
        table = self._make_table_stub()
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert "short_duration" in result["rejection_reason"]

    def test_wrong_sound_type(self):
        session = self._make_session(sound_type="adult")
        table = self._make_table_stub()
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert "wrong_sound_type" in result["rejection_reason"]

    def test_low_confidence_confirm_rejected(self):
        session = self._make_session(confidence=0.2)
        table = self._make_table_stub()
        # was_correct=True + low confidence = reject
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert "low_confidence" in result["rejection_reason"]

    def test_correction_always_accepted(self):
        session = self._make_session(confidence=0.2)
        table = self._make_table_stub()
        # was_correct=False = correction, always accepted regardless of confidence
        result = apply_quality_gates(session, "hungry", False, table)
        assert result["accepted"] is True

    def test_already_confirmed(self):
        session = self._make_session()
        table = self._make_table_stub(already_confirmed=True)
        result = apply_quality_gates(session, "hungry", True, table)
        assert result["accepted"] is False
        assert result["rejection_reason"] == "already_confirmed"
