"""
Unit tests for similarity utilities
"""
import math
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../shared"))

from similarity import (
    cosine_similarity,
    euclidean_distance,
    find_best_cluster,
    l2_normalize,
    update_centroid,
)


class TestCosineSimilarity:
    def test_identical_vectors(self):
        v = [1.0, 2.0, 3.0]
        assert abs(cosine_similarity(v, v) - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_opposite_vectors(self):
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        assert abs(cosine_similarity(a, b) - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = [0.0, 0.0]
        b = [1.0, 2.0]
        assert cosine_similarity(a, b) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


class TestFindBestCluster:
    def test_empty_clusters(self):
        cluster_id, sim = find_best_cluster([1.0, 0.0], [], threshold=0.85)
        assert cluster_id is None
        assert sim == 0.0

    def test_finds_matching_cluster(self):
        clusters = [
            {"cluster_id": "c1", "embedding_vector": [1.0, 0.0]},
            {"cluster_id": "c2", "embedding_vector": [0.0, 1.0]},
        ]
        cluster_id, sim = find_best_cluster([1.0, 0.0], clusters, threshold=0.85)
        assert cluster_id == "c1"
        assert abs(sim - 1.0) < 1e-6

    def test_no_cluster_above_threshold(self):
        clusters = [
            {"cluster_id": "c1", "embedding_vector": [0.0, 1.0]},
        ]
        cluster_id, sim = find_best_cluster([1.0, 0.0], clusters, threshold=0.85)
        assert cluster_id is None


class TestUpdateCentroid:
    def test_first_session(self):
        result = update_centroid([0.5, 0.5], [1.0, 0.0], frequency_count=1)
        assert result == [1.0, 0.0]

    def test_incremental_mean(self):
        old = [0.0, 0.0]
        new = [1.0, 1.0]
        result = update_centroid(old, new, frequency_count=2)
        assert abs(result[0] - 0.5) < 1e-6
        assert abs(result[1] - 0.5) < 1e-6


class TestL2Normalize:
    def test_unit_vector(self):
        v = [3.0, 4.0]
        result = l2_normalize(v)
        norm = math.sqrt(sum(x * x for x in result))
        assert abs(norm - 1.0) < 1e-6

    def test_zero_vector_unchanged(self):
        v = [0.0, 0.0]
        result = l2_normalize(v)
        assert result == [0.0, 0.0]
