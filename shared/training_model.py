"""
Qleam - Online supervised acoustic model utilities (Phase 3).

This module trains and serves a lightweight stage-specific prototype classifier
from accepted TrainingCandidate samples (no raw audio required).
"""
import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from intent_taxonomy import canonical_intent_key, normalize_intent_distribution

logger = logging.getLogger(__name__)

# Stable feature schema for model training/inference.
_MODEL_FEATURE_KEYS: Tuple[str, ...] = (
    "emotional_intensity",
    "rhythm",
    "repetition",
    "expressive_flow",
    "cry_fraction",
    "babble_fraction",
    "pause_ratio",
    "syllable_rate",
    "hnr_db",
    "jitter_percent",
    "shimmer_db",
    "f0_mean",
    "f0_std",
    "spectral_centroid",
    "spectral_entropy",
    "cbr_estimate",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _softmax(logits: Dict[str, float]) -> Dict[str, float]:
    if not logits:
        return {}
    m = max(logits.values())
    exps = {k: math.exp(v - m) for k, v in logits.items()}
    z = sum(exps.values()) or 1.0
    return {k: exps[k] / z for k in exps}


def _to_feature_map(feature_scores: Dict[str, Any], rich_features: Dict[str, Any]) -> Dict[str, float]:
    merged: Dict[str, float] = {}
    for k, v in (feature_scores or {}).items():
        merged[str(k)] = _safe_float(v)
    for k, v in (rich_features or {}).items():
        merged[str(k)] = _safe_float(v)
    return merged


def build_training_vector(
    feature_scores: Optional[Dict[str, Any]],
    rich_features: Optional[Dict[str, Any]],
    feature_keys: Optional[List[str]] = None,
) -> Dict[str, float]:
    """
    Build a stable numeric feature vector for training/inference.
    """
    keys = tuple(feature_keys) if feature_keys else _MODEL_FEATURE_KEYS
    merged = _to_feature_map(feature_scores or {}, rich_features or {})
    return {k: _safe_float(merged.get(k, 0.0)) for k in keys}


def _vector_list(vector: Dict[str, float], feature_keys: Tuple[str, ...]) -> List[float]:
    return [_safe_float(vector.get(k, 0.0)) for k in feature_keys]


def _zscore(x: List[float], mean: List[float], std: List[float]) -> List[float]:
    z: List[float] = []
    for i in range(len(x)):
        denom = std[i] if i < len(std) and std[i] > 1e-6 else 1.0
        mu = mean[i] if i < len(mean) else 0.0
        z.append((x[i] - mu) / denom)
    return z


def _predict_from_z(
    z: List[float],
    centroids: Dict[str, List[float]],
    temperature: float = 1.0,
) -> Dict[str, float]:
    if not centroids:
        return {}
    t = max(0.5, float(temperature))
    dim = max(1, len(z))
    logits: Dict[str, float] = {}
    for label, c in centroids.items():
        if not isinstance(c, list) or not c:
            continue
        m = min(len(z), len(c))
        if m <= 0:
            continue
        dist = 0.0
        for i in range(m):
            d = z[i] - _safe_float(c[i])
            dist += d * d
        dist /= max(1, m)
        logits[label] = -dist / t
    probs = _softmax(logits)
    return normalize_intent_distribution(probs, include_technical=False, fill_missing=True)


def predict_intent_distribution(
    model: Dict[str, Any],
    feature_scores: Optional[Dict[str, Any]],
    rich_features: Optional[Dict[str, Any]],
) -> Dict[str, float]:
    """
    Predict intent probabilities from a trained prototype model artifact.
    """
    if not isinstance(model, dict):
        return {}

    keys_raw = model.get("feature_keys") or list(_MODEL_FEATURE_KEYS)
    feature_keys = tuple(str(k) for k in keys_raw)

    vector = build_training_vector(feature_scores or {}, rich_features or {}, list(feature_keys))
    x = _vector_list(vector, feature_keys)

    mean = [_safe_float(v) for v in (model.get("global_mean") or [0.0] * len(feature_keys))]
    std = [_safe_float(v, 1.0) for v in (model.get("global_std") or [1.0] * len(feature_keys))]
    z = _zscore(x, mean, std)

    centroids_raw = model.get("centroids") or {}
    centroids = {
        str(k): [_safe_float(v) for v in vals]
        for k, vals in centroids_raw.items()
        if isinstance(vals, list) and vals
    }
    return _predict_from_z(z, centroids, temperature=_safe_float(model.get("temperature"), 1.0))


def _accuracy(rows: List[Tuple[str, List[float]]], centroids: Dict[str, List[float]]) -> Tuple[float, int]:
    if not rows:
        return 0.0, 0
    correct = 0
    for label, z in rows:
        pred = _predict_from_z(z, centroids)
        if not pred:
            continue
        top = max(pred, key=pred.get)
        if top == label:
            correct += 1
    n = len(rows)
    return (float(correct) / max(1, n), n)


def train_prototype_model(
    candidates: List[Dict[str, Any]],
    min_train_samples: int = 120,
    min_val_samples: int = 24,
    min_label_support: int = 8,
    min_accuracy: float = 0.55,
) -> Dict[str, Any]:
    """
    Train a stage-level prototype classifier from accepted candidates.

    Returns:
      {
        "ok": bool,
        "reason": str,
        "model": {...},          # when ok
        "is_reliable": bool,     # when ok
      }
    """
    rows: List[Tuple[str, str, List[float]]] = []
    for item in candidates or []:
        label = canonical_intent_key(item.get("accepted_label"), allow_technical=False)
        if not label:
            continue
        split = str(item.get("dataset_split") or "train").strip().lower()
        if split not in {"train", "val", "test"}:
            split = "train"
        vector = build_training_vector(
            item.get("feature_scores") or {},
            item.get("rich_features") or {},
        )
        rows.append((split, label, _vector_list(vector, _MODEL_FEATURE_KEYS)))

    if not rows:
        return {"ok": False, "reason": "no_training_rows"}

    train_rows = [r for r in rows if r[0] == "train"]
    if not train_rows:
        train_rows = list(rows)

    train_label_counts: Dict[str, int] = {}
    for _, label, _ in train_rows:
        train_label_counts[label] = train_label_counts.get(label, 0) + 1

    eligible_labels = {k for k, n in train_label_counts.items() if n >= max(1, min_label_support)}
    if len(eligible_labels) < 3:
        return {"ok": False, "reason": "insufficient_label_diversity"}

    train_rows = [r for r in train_rows if r[1] in eligible_labels]
    val_rows = [r for r in rows if r[0] == "val" and r[1] in eligible_labels]
    test_rows = [r for r in rows if r[0] == "test" and r[1] in eligible_labels]
    filtered_label_counts: Dict[str, int] = {}
    for _, label, _ in train_rows:
        filtered_label_counts[label] = filtered_label_counts.get(label, 0) + 1
    if len(train_rows) < max(1, min_train_samples):
        return {"ok": False, "reason": "insufficient_train_samples"}

    dim = len(_MODEL_FEATURE_KEYS)
    mean = [0.0] * dim
    for _, _, x in train_rows:
        for i in range(dim):
            mean[i] += _safe_float(x[i])
    n_train = len(train_rows)
    mean = [v / max(1, n_train) for v in mean]

    var = [0.0] * dim
    for _, _, x in train_rows:
        for i in range(dim):
            d = _safe_float(x[i]) - mean[i]
            var[i] += d * d
    std = [max(1e-6, math.sqrt(v / max(1, n_train))) for v in var]

    z_train: List[Tuple[str, List[float]]] = []
    for _, label, x in train_rows:
        z_train.append((label, _zscore(x, mean, std)))

    z_val: List[Tuple[str, List[float]]] = []
    for _, label, x in val_rows:
        z_val.append((label, _zscore(x, mean, std)))

    z_test: List[Tuple[str, List[float]]] = []
    for _, label, x in test_rows:
        z_test.append((label, _zscore(x, mean, std)))

    centroid_sum: Dict[str, List[float]] = {}
    centroid_count: Dict[str, int] = {}
    for label, z in z_train:
        if label not in centroid_sum:
            centroid_sum[label] = [0.0] * dim
            centroid_count[label] = 0
        centroid_count[label] += 1
        for i in range(dim):
            centroid_sum[label][i] += z[i]

    centroids: Dict[str, List[float]] = {}
    for label, sums in centroid_sum.items():
        cnt = max(1, centroid_count.get(label, 1))
        centroids[label] = [round(v / cnt, 6) for v in sums]

    if len(centroids) < 3:
        return {"ok": False, "reason": "insufficient_centroids"}

    val_acc, val_n = _accuracy(z_val, centroids)
    test_acc, test_n = _accuracy(z_test, centroids)
    chance = 1.0 / max(1, len(centroids))

    eval_acc = 0.0
    if val_n >= min_val_samples:
        eval_acc = val_acc
    elif test_n >= min_val_samples:
        eval_acc = test_acc

    saturation = max(min_train_samples + 1, min_train_samples * 8)
    data_factor = min(1.0, math.log1p(n_train) / math.log1p(float(saturation)))
    rel_raw = 0.0
    if chance < 0.999:
        rel_raw = (eval_acc - chance) / max(1e-6, (1.0 - chance))
    reliability = round(_clamp(rel_raw * data_factor, 0.0, 1.0), 4)

    is_reliable = bool(
        n_train >= min_train_samples
        and (
            (val_n >= min_val_samples and val_acc >= min_accuracy)
            or (test_n >= min_val_samples and test_acc >= min_accuracy)
        )
    )

    model = {
        "model_type": "prototype_v1",
        "feature_keys": list(_MODEL_FEATURE_KEYS),
        "global_mean": [round(v, 6) for v in mean],
        "global_std": [round(v, 6) for v in std],
        "centroids": centroids,
        "label_counts": {k: int(v) for k, v in filtered_label_counts.items()},
        "temperature": 1.0,
        "training_samples": int(n_train),
        "validation_samples": int(val_n),
        "test_samples": int(test_n),
        "metrics": {
            "val_accuracy": round(val_acc, 4),
            "test_accuracy": round(test_acc, 4),
            "chance_accuracy": round(chance, 4),
        },
        "reliability": reliability,
    }

    logger.info(
        "Prototype model trained: n_train=%s val_acc=%.4f test_acc=%.4f reliability=%.4f reliable=%s",
        n_train,
        val_acc,
        test_acc,
        reliability,
        is_reliable,
    )
    return {"ok": True, "reason": "", "model": model, "is_reliable": is_reliable}
