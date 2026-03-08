"""Tests for lambdas/model_trainer/handler.py — unit tests for helper functions."""
import sys
import os

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "model_trainer"))

# We can test the neural network functions directly without AWS
from handler import (
    _init_params,
    _forward_two_branch,
    _relu,
    _softmax_batch,
    _train_two_branch,
    EMBEDDING_DIM,
)
from age_encoder import AGE_DIM


class TestNeuralNetwork:
    def test_relu(self):
        x = np.array([-2, -1, 0, 1, 2], dtype=np.float32)
        result = _relu(x)
        np.testing.assert_array_equal(result, [0, 0, 0, 1, 2])

    def test_softmax_batch(self):
        x = np.array([[1, 2, 3], [3, 2, 1]], dtype=np.float32)
        result = _softmax_batch(x)
        # Each row should sum to ~1
        np.testing.assert_array_almost_equal(result.sum(axis=1), [1.0, 1.0])
        # Highest logit should have highest probability
        assert np.argmax(result[0]) == 2
        assert np.argmax(result[1]) == 0

    def test_init_params_shapes(self):
        n_classes = 7
        params = _init_params(n_classes)

        assert params["W_emb1"].shape == (EMBEDDING_DIM, 256)
        assert params["b_emb1"].shape == (256,)
        assert params["W_emb2"].shape == (256, 128)
        assert params["b_emb2"].shape == (128,)
        assert params["W_age1"].shape == (AGE_DIM, 16)
        assert params["b_age1"].shape == (16,)
        assert params["W_age2"].shape == (16, 8)
        assert params["b_age2"].shape == (8,)
        assert params["W_fc1"].shape == (136, 64)  # 128 + 8
        assert params["b_fc1"].shape == (64,)
        assert params["W_fc2"].shape == (64, n_classes)
        assert params["b_fc2"].shape == (n_classes,)

    def test_forward_two_branch_output_shape(self):
        n_classes = 7
        batch_size = 4
        params = _init_params(n_classes)

        X_emb = np.random.randn(batch_size, EMBEDDING_DIM).astype(np.float32)
        X_age = np.random.randn(batch_size, AGE_DIM).astype(np.float32)

        logits = _forward_two_branch(params, X_emb, X_age)
        assert logits.shape == (batch_size, n_classes)

    def test_train_two_branch_reduces_loss(self):
        """Training should reduce loss over epochs."""
        np.random.seed(42)
        n_samples = 50
        n_classes = 3

        X_emb = np.random.randn(n_samples, EMBEDDING_DIM).astype(np.float32)
        X_age = np.random.randn(n_samples, AGE_DIM).astype(np.float32)
        y = np.random.randint(0, n_classes, n_samples)

        params, losses = _train_two_branch(
            X_emb, X_age, y, n_classes,
            epochs=10, lr=0.001, reg=1e-4, batch_size=16,
        )

        # Loss should decrease
        assert losses[-1] < losses[0], f"Loss didn't decrease: {losses[0]:.4f} -> {losses[-1]:.4f}"

    def test_train_produces_valid_params(self):
        np.random.seed(42)
        n_samples = 30
        n_classes = 7

        X_emb = np.random.randn(n_samples, EMBEDDING_DIM).astype(np.float32)
        X_age = np.random.randn(n_samples, AGE_DIM).astype(np.float32)
        y = np.random.randint(0, n_classes, n_samples)

        params, _ = _train_two_branch(
            X_emb, X_age, y, n_classes, epochs=5, lr=0.001,
        )

        # All params should be finite
        for key, val in params.items():
            assert np.all(np.isfinite(val)), f"{key} contains NaN/Inf"
