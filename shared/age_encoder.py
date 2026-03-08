"""
Qleam — Age Encoder (Phase 4)
Encodes baby age_days into a 4-dimensional feature vector for the
age-conditioned emotion classifier.

Encoding:
  [0] age_days / 730.0              — normalized 0-1 for 0-24 months
  [1] sin(age_days * pi / 90)       — captures ~3-month developmental cycles
  [2] sin(age_days * pi / 180)      — captures ~6-month developmental cycles
  [3] 1.0 if age_days < 90 else 0.0 — newborn hint (Dunstan reflex period)
"""
import math
from typing import List

import numpy as np

AGE_DIM = 4
MAX_AGE_DAYS = 730  # 24 months


def encode_age(age_days: int) -> np.ndarray:
    """
    Encode age_days into a 4-dimensional feature vector.

    Args:
        age_days: Child age in days (0-730). Clamped to [0, 730].

    Returns:
        np.ndarray of shape (4,), dtype float32
    """
    age = max(0, min(age_days, MAX_AGE_DAYS))
    return np.array([
        age / MAX_AGE_DAYS,
        math.sin(age * math.pi / 90),
        math.sin(age * math.pi / 180),
        1.0 if age < 90 else 0.0,
    ], dtype=np.float32)


def encode_age_batch(age_days_list: List[int]) -> np.ndarray:
    """
    Encode a batch of age_days values.

    Returns:
        np.ndarray of shape (N, 4), dtype float32
    """
    return np.array([encode_age(a) for a in age_days_list], dtype=np.float32)
