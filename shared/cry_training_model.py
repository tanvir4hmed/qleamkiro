"""
Qleam — Cry Training Model
Global cry emotion training model that learns from all children's data.
Age-stratified for accurate emotion detection across developmental stages.

This model:
1. Collects parent-confirmed cry emotion labels
2. Builds age-stratified prototype centroids for each emotion
3. Predicts cry emotion from acoustic features using nearest-centroid
4. Improves accuracy with every parent confirmation

Storage: DynamoDB ModelRegistry table (model_type="cry_emotion")
Training data: DynamoDB TrainingCandidate table (candidate_type="cry_emotion")

Key difference from private_language_model:
- This is GLOBAL — all children contribute (anonymized)
- Data is age-stratified — separate models per age bracket
- Uses acoustic features, not embeddings
"""
import logging
import math
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MIN_SAMPLES_PER_EMOTION = 5      # Minimum samples before using trained model
MIN_TOTAL_SAMPLES = 15            # Minimum total samples per age bracket
FEATURE_KEYS = [
    "f0_mean", "f0_std", "f0_instability",
    "rms_mean", "rms_std", "energy_variability",
    "zcr", "spectral_centroid", "spectral_flatness",
    "spectral_rolloff", "syllable_rate", "voiced_fraction",
]
FEATURE_DIM = len(FEATURE_KEYS)

AGE_BRACKETS = ["0_6m", "6_12m", "12_18m", "18_24m", "24_36m"]


def _decimal_to_float(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(i) for i in obj]
    return obj


def _float_to_decimal(obj):
    import math as _math
    if obj is None:
        return None
    if isinstance(obj, Decimal):
        return obj
    if hasattr(obj, 'item'):
        try:
            obj = obj.item()
        except (AttributeError, TypeError):
            pass
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return Decimal("0")
        return Decimal(str(obj))
    if isinstance(obj, int) and not isinstance(obj, bool):
        return Decimal(obj)
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(i) for i in obj]
    return obj


def _features_to_vector(features: Dict) -> List[float]:
    """Convert feature dict to ordered vector."""
    return [float(features.get(k, 0.0)) for k in FEATURE_KEYS]


def _normalize_vector(vec: List[float]) -> List[float]:
    """Normalize feature vector to unit length."""
    arr = np.array(vec, dtype=np.float64)
    norm = float(np.linalg.norm(arr))
    if norm < 1e-9:
        return vec
    return (arr / norm).tolist()


def store_cry_training_sample(
    features: Dict,
    confirmed_emotion: str,
    age_bracket: str,
    child_id: str,
    session_id: str,
    training_candidate_table,
) -> Dict[str, str]:
    """
    Store a parent-confirmed cry emotion sample for model training.

    Args:
        features: Acoustic features from sound classifier
        confirmed_emotion: Parent-confirmed emotion label
        age_bracket: Age bracket of the child
        child_id: Child ID (for deduplication, not stored in model)
        session_id: Session ID
        training_candidate_table: DynamoDB Table resource

    Returns:
        {"status": "stored", "candidate_id": str}
    """
    now = datetime.now(timezone.utc).isoformat()
    candidate_id = f"cry_{uuid.uuid4().hex[:12]}"

    feature_vector = _features_to_vector(features)

    item = {
        "candidate_id": candidate_id,
        "candidate_type": "cry_emotion",
        "age_bracket": age_bracket,
        "emotion_label": confirmed_emotion,
        "feature_vector": feature_vector,
        "session_id": session_id,
        "accepted_at": now,
    }

    try:
        training_candidate_table.put_item(Item=_float_to_decimal(item))
        logger.info(f"Stored cry training sample: emotion={confirmed_emotion} age={age_bracket}")
        return {"status": "stored", "candidate_id": candidate_id}
    except Exception as e:
        logger.error(f"Failed to store cry training sample: {e}")
        return {"status": "error", "error": str(e)}


def train_cry_model(
    age_bracket: str,
    training_candidate_table,
    model_registry_table,
) -> Dict[str, Any]:
    """
    Train or update cry emotion model for a specific age bracket.
    Uses prototype-based learning (nearest centroid classifier).

    This is called periodically or when enough new samples arrive.

    Returns:
        {"status": "trained" | "insufficient_data", "model_id": str, ...}
    """
    try:
        from boto3.dynamodb.conditions import Attr
        # Scan for all cry training samples for this age bracket
        response = training_candidate_table.scan(
            FilterExpression=(
                Attr("candidate_type").eq("cry_emotion") &
                Attr("age_bracket").eq(age_bracket)
            ),
        )
        samples = _decimal_to_float(response.get("Items", []))

        if len(samples) < MIN_TOTAL_SAMPLES:
            return {
                "status": "insufficient_data",
                "sample_count": len(samples),
                "needed": MIN_TOTAL_SAMPLES,
            }

        # Group by emotion
        emotion_groups = {}
        for sample in samples:
            emotion = sample.get("emotion_label", "unknown")
            vec = sample.get("feature_vector", [])
            if not vec or len(vec) != FEATURE_DIM:
                continue
            if emotion not in emotion_groups:
                emotion_groups[emotion] = []
            emotion_groups[emotion].append(vec)

        # Compute centroids for each emotion with enough samples
        centroids = {}
        counts = {}
        for emotion, vectors in emotion_groups.items():
            if len(vectors) < MIN_SAMPLES_PER_EMOTION:
                continue
            arr = np.array(vectors, dtype=np.float64)
            centroid = np.mean(arr, axis=0).tolist()
            std = np.std(arr, axis=0).tolist()
            centroids[emotion] = {
                "centroid": centroid,
                "std": std,
                "count": len(vectors),
            }
            counts[emotion] = len(vectors)

        if len(centroids) < 2:
            return {
                "status": "insufficient_emotions",
                "emotions_found": list(centroids.keys()),
                "needed_emotions": 2,
            }

        # Save model to registry
        model_id = f"cry_{age_bracket}_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()

        model_item = {
            "model_id": model_id,
            "model_type": "cry_emotion",
            "age_bracket": age_bracket,
            "centroids": centroids,
            "total_samples": len(samples),
            "emotion_counts": counts,
            "created_at": now,
            "is_promoted": True,
        }

        model_registry_table.put_item(Item=_float_to_decimal(model_item))
        logger.info(f"Trained cry model: {model_id} with {len(samples)} samples, {len(centroids)} emotions")

        return {
            "status": "trained",
            "model_id": model_id,
            "sample_count": len(samples),
            "emotion_count": len(centroids),
            "emotions": list(centroids.keys()),
        }

    except Exception as e:
        logger.error(f"Failed to train cry model: {e}")
        return {"status": "error", "error": str(e)}


def predict_cry_emotion(
    features: Dict,
    age_bracket: str,
    model_registry_table,
) -> Optional[Dict[str, Any]]:
    """
    Predict cry emotion using the trained model for this age bracket.

    Args:
        features: Acoustic features from sound classifier
        age_bracket: Age bracket to use
        model_registry_table: DynamoDB Table resource

    Returns:
        {
            "emotion_scores": {"hungry": 0.8, "tired": 0.3, ...},
            "primary_emotion": str,
            "confidence": float,
            "model_id": str,
            "total_training_samples": int,
        }
        or None if no trained model exists
    """
    try:
        from boto3.dynamodb.conditions import Attr
        # Find latest promoted cry model for this age bracket
        response = model_registry_table.scan(
            FilterExpression=(
                Attr("model_type").eq("cry_emotion") &
                Attr("age_bracket").eq(age_bracket) &
                Attr("is_promoted").eq(True)
            ),
        )
        models = _decimal_to_float(response.get("Items", []))

        if not models:
            return None

        # Get most recent model
        model = max(models, key=lambda m: m.get("created_at", ""))
        centroids = model.get("centroids", {})

        if not centroids:
            return None

        # Compute feature vector
        feature_vec = np.array(_features_to_vector(features), dtype=np.float64)

        # Compute distance to each emotion centroid
        scores = {}
        for emotion, data in centroids.items():
            centroid = np.array(data.get("centroid", []), dtype=np.float64)
            std = np.array(data.get("std", []), dtype=np.float64)

            if len(centroid) != FEATURE_DIM:
                continue

            # Mahalanobis-like distance (normalized by std)
            std_safe = np.maximum(std, 1e-6)
            diff = (feature_vec - centroid) / std_safe
            distance = float(np.sqrt(np.sum(diff ** 2)))

            # Convert distance to similarity score
            score = math.exp(-distance * 0.5)
            scores[emotion] = score

        if not scores:
            return None

        # Normalize scores
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        primary = ranked[0]

        return {
            "emotion_scores": {k: round(v, 3) for k, v in scores.items()},
            "primary_emotion": primary[0],
            "confidence": round(primary[1], 3),
            "model_id": model.get("model_id", ""),
            "total_training_samples": int(model.get("total_samples", 0)),
        }

    except Exception as e:
        logger.warning(f"Cry model prediction failed: {e}")
        return None
