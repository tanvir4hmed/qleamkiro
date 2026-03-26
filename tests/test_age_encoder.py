"""Tests for shared/age_encoder.py"""
import sys
import os
import math

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
from age_encoder import encode_age, encode_age_batch, AGE_DIM, MAX_AGE_DAYS


def test_encode_age_shape():
    result = encode_age(100)
    assert result.shape == (AGE_DIM,)
    assert result.dtype == np.float32


def test_encode_age_newborn_hint_is_smooth():
    result_60 = encode_age(60)
    result_90 = encode_age(90)
    result_120 = encode_age(120)

    assert result_60[3] > result_90[3] > result_120[3]
    assert result_60[3] > 0.9
    assert result_90[3] == pytest.approx(0.5, abs=1e-6)
    assert result_120[3] < 0.1


def test_encode_age_normalization():
    # age_days=0 -> normalized = 0
    result = encode_age(0)
    assert result[0] == 0.0

    # age_days=730 -> normalized = 1.0
    result = encode_age(MAX_AGE_DAYS)
    assert result[0] == 1.0


def test_encode_age_clamps():
    # Negative age should clamp to 0
    result = encode_age(-10)
    assert result[0] == 0.0

    # Age > MAX should clamp to MAX
    result = encode_age(1000)
    assert result[0] == 1.0


def test_encode_age_sinusoidal():
    result = encode_age(90)
    # sin(90 * pi / 90) = sin(pi) ≈ 0
    assert abs(result[1]) < 1e-6
    # sin(90 * pi / 180) = sin(pi/2) = 1.0
    assert abs(result[2] - 1.0) < 1e-6


def test_encode_age_batch():
    ages = [0, 30, 90, 180, 365]
    result = encode_age_batch(ages)
    assert result.shape == (5, AGE_DIM)
    assert result.dtype == np.float32

    # Each row should match individual encode
    for i, age in enumerate(ages):
        np.testing.assert_array_almost_equal(result[i], encode_age(age))


def test_encode_age_batch_empty():
    result = encode_age_batch([])
    assert result.shape == (0, AGE_DIM)
