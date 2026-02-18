"""
Unit tests for normalization utilities
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../shared"))

from normalization import (
    clamp,
    compute_deviation_level,
    compute_readiness_score,
    normalize_probability_distribution,
    normalize_score,
    update_ema_baseline,
    update_feature_baselines,
)


class TestNormalizeScore:
    def test_within_range(self):
        assert normalize_score(0.5, 0.0, 1.0) == 0.5

    def test_clamps_above_max(self):
        assert normalize_score(1.5, 0.0, 1.0) == 1.0

    def test_clamps_below_min(self):
        assert normalize_score(-0.5, 0.0, 1.0) == 0.0

    def test_equal_min_max(self):
        assert normalize_score(0.5, 0.5, 0.5) == 0.0


class TestUpdateEmaBaseline:
    def test_basic_ema(self):
        result = update_ema_baseline(0.5, 0.8, alpha=0.3)
        expected = 0.3 * 0.8 + 0.7 * 0.5
        assert abs(result - expected) < 1e-6

    def test_alpha_zero_raises(self):
        with pytest.raises(ValueError):
            update_ema_baseline(0.5, 0.8, alpha=0.0)

    def test_alpha_one_raises(self):
        with pytest.raises(ValueError):
            update_ema_baseline(0.5, 0.8, alpha=1.0)

    def test_first_session_same_value(self):
        result = update_ema_baseline(0.7, 0.7, alpha=0.3)
        assert abs(result - 0.7) < 1e-6


class TestUpdateFeatureBaselines:
    def test_updates_all_features(self):
        previous = {"rhythm": 0.5, "repetition": 0.6}
        current = {"rhythm": 0.8, "repetition": 0.4}
        result = update_feature_baselines(previous, current, alpha=0.3)
        assert "rhythm" in result
        assert "repetition" in result
        assert abs(result["rhythm"] - (0.3 * 0.8 + 0.7 * 0.5)) < 1e-5

    def test_new_feature_uses_current(self):
        previous = {}
        current = {"rhythm": 0.7}
        result = update_feature_baselines(previous, current, alpha=0.3)
        assert abs(result["rhythm"] - 0.7) < 1e-5


class TestComputeDeviationLevel:
    def test_below_min_sessions(self):
        result = compute_deviation_level({"rhythm": 0.8}, {"rhythm": 0.5}, session_count=2, min_sessions=3)
        assert result["deviation_level"] == "none"
        assert result["deviation_flag"] is False

    def test_no_deviation(self):
        scores = {"rhythm": 0.5, "repetition": 0.5}
        baseline = {"rhythm": 0.5, "repetition": 0.5}
        result = compute_deviation_level(scores, baseline, session_count=5)
        assert result["deviation_level"] == "none"
        assert result["deviation_flag"] is False

    def test_high_deviation(self):
        scores = {"rhythm": 0.9, "repetition": 0.9}
        baseline = {"rhythm": 0.1, "repetition": 0.1}
        result = compute_deviation_level(scores, baseline, session_count=5)
        assert result["deviation_level"] in ("moderate", "high")
        assert result["deviation_flag"] is True


class TestComputeReadinessScore:
    def test_all_features_present(self):
        scores = {
            "rhythm": 0.8,
            "repetition": 0.6,
            "emotional_intensity": 0.7,
            "expressive_flow": 0.5,
        }
        result = compute_readiness_score(scores)
        expected = 0.8 * 0.25 + 0.6 * 0.25 + 0.7 * 0.30 + 0.5 * 0.20
        assert abs(result - expected) < 1e-4

    def test_empty_scores_returns_default(self):
        result = compute_readiness_score({})
        assert result == 0.5


class TestNormalizeProbabilityDistribution:
    def test_sums_to_one(self):
        dist = {"a": 0.3, "b": 0.5, "c": 0.2}
        result = normalize_probability_distribution(dist)
        assert abs(sum(result.values()) - 1.0) < 1e-6

    def test_zero_sum_returns_uniform(self):
        dist = {"a": 0.0, "b": 0.0}
        result = normalize_probability_distribution(dist)
        assert abs(result["a"] - 0.5) < 1e-6


class TestClamp:
    def test_within_range(self):
        assert clamp(0.5) == 0.5

    def test_above_max(self):
        assert clamp(1.5) == 1.0

    def test_below_min(self):
        assert clamp(-0.5) == 0.0
