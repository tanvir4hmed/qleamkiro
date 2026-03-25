"""
Qleam — Emotion Classifier (BRAIN)
Lightweight classifier that takes HuBERT embeddings and predicts cry emotions.

Phase 2: Pre-trained on public datasets (Dunstan + DonateACry + Baby Chillanto).
Phase 3: Fine-tuned with parent-confirmed data (numpy softmax on embeddings).
Phase 4: Age-conditioned two-branch network (embeddings + age encoding).

Model formats:
- TFLite (~2MB): Phase 2 public dataset model
- Numpy .npz: Phase 3/4 trained model (loaded from S3 via ModelVersions)
"""
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np
from age_encoder import encode_age

logger = logging.getLogger(__name__)

# 7-class emotion taxonomy (unified across public datasets)
EMOTION_CLASSES = ["hungry", "tired", "discomfort", "gas", "pain", "burp", "content"]

# Mapping from public dataset labels to our taxonomy
LABEL_MAP = {
    # Dunstan
    "hungry": "hungry",
    "neh": "hungry",
    "tired": "tired",
    "owh": "tired",
    "discomfort": "discomfort",
    "heh": "discomfort",
    "stomachache": "gas",
    "eairh": "gas",
    "burping": "burp",
    "eh": "burp",
    "scared": "pain",
    # DonateACry
    "hunger": "hungry",
    "belly_pain": "gas",
    # Baby Chillanto
    "normal": "content",
    "pain": "pain",
}

_interpreter = None
_model_loaded = False
_numpy_model = None  # Phase 3/4: numpy model dict
_numpy_model_loaded = False
_active_model_version = 0


def load_model(model_path: Optional[str] = None) -> bool:
    """
    Load TFLite emotion classifier model (Phase 2).

    Args:
        model_path: Path to .tflite model file. If None, tries S3 or default path.

    Returns:
        True if model loaded successfully.
    """
    global _interpreter, _model_loaded

    if model_path is None:
        model_path = os.environ.get(
            "EMOTION_MODEL_PATH",
            "/var/task/models/emotion_classifier.tflite",
        )

    if not os.path.exists(model_path):
        logger.warning(f"Emotion classifier model not found at {model_path}")
        _model_loaded = False
        return False

    try:
        import tflite_runtime.interpreter as tflite
        _interpreter = tflite.Interpreter(model_path=model_path)
        _interpreter.allocate_tensors()
        _model_loaded = True
        logger.info(f"Emotion classifier loaded from {model_path}")
        return True
    except ImportError:
        try:
            import tensorflow as tf
            _interpreter = tf.lite.Interpreter(model_path=model_path)
            _interpreter.allocate_tensors()
            _model_loaded = True
            logger.info(f"Emotion classifier loaded from {model_path} (tf.lite)")
            return True
        except ImportError:
            logger.warning("Neither tflite_runtime nor tensorflow available")
            _model_loaded = False
            return False
    except Exception as e:
        logger.error(f"Failed to load emotion classifier: {e}")
        _model_loaded = False
        return False


def load_numpy_model(model_path: Optional[str] = None) -> bool:
    """
    Load Phase 3/4 numpy model (.npz file).
    Phase 3: {weights, bias}
    Phase 4: {W_emb1, b_emb1, W_emb2, b_emb2, W_age1, b_age1, W_age2, b_age2, W_fc1, b_fc1, W_fc2, b_fc2}
    """
    global _numpy_model, _numpy_model_loaded, _active_model_version

    if model_path is None:
        model_path = os.environ.get("EMOTION_NUMPY_MODEL_PATH", "")

    if not model_path:
        return _load_active_model_from_s3()

    if not os.path.exists(model_path):
        logger.debug(f"Numpy model not found at {model_path}")
        return False

    try:
        data = np.load(model_path)
        _numpy_model = {k: data[k] for k in data.files}
        _numpy_model_loaded = True
        logger.info(f"Numpy emotion model loaded from {model_path}")
        return True
    except Exception as e:
        logger.warning(f"Failed to load numpy model: {e}")
        return False


def _load_active_model_from_s3() -> bool:
    """Load the active model version from S3 via ModelVersions DynamoDB table."""
    global _numpy_model, _numpy_model_loaded, _active_model_version
    import io

    model_versions_table = os.environ.get("MODEL_VERSIONS_TABLE", "")
    if not model_versions_table:
        return False

    try:
        import boto3
        dynamodb = boto3.resource("dynamodb")
        from boto3.dynamodb.conditions import Attr
        mv_table = dynamodb.Table(model_versions_table)

        response = mv_table.scan(
            FilterExpression=(
                Attr("model_type").eq("emotion_classifier") &
                Attr("active").eq(True)
            ),
            Limit=1,
        )
        items = response.get("Items", [])
        if not items:
            return False

        item = items[0]
        s3_path = item.get("s3_path", "")
        s3_bucket = item.get("s3_bucket", "")
        version = int(item.get("version", 0))

        if not s3_path or not s3_bucket:
            return False

        s3_client = boto3.client("s3")
        obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_path)
        buf = io.BytesIO(obj["Body"].read())
        data = np.load(buf)

        # Load all keys — works for both Phase 3 and Phase 4 model formats
        _numpy_model = {k: data[k] for k in data.files}
        _numpy_model_loaded = True
        _active_model_version = version
        arch = "phase4-two-branch" if "W_emb1" in _numpy_model else "phase3-softmax"
        logger.info(f"Active model v{version} ({arch}) loaded from s3://{s3_bucket}/{s3_path}")
        return True
    except Exception as e:
        logger.debug(f"Could not load active model from S3: {e}")
        return False


def predict_emotion(
    embeddings: np.ndarray,
    age_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Predict cry emotion from HuBERT embeddings.

    Args:
        embeddings: 768-dim HuBERT embeddings (mean-pooled)
        age_days: Child age in days (used by Phase 4 two-branch model)

    Returns:
        {
            "primary_emotion": str,
            "confidence": float,
            "emotion_probabilities": {"hungry": 0.35, ...},
            "top_emotions": [{"key": "hungry", "score": 0.35}, ...],
            "model_version": str,
            "using_model": bool,
        }
    """
    # Try numpy model first (Phase 4 age-conditioned or Phase 3 softmax)
    numpy_probs = None
    if _numpy_model_loaded and _numpy_model is not None:
        try:
            numpy_probs = _predict_numpy(embeddings, age_days=age_days)
        except Exception as e:
            logger.warning(f"Numpy model inference failed: {e}")

    # Try TFLite model (Phase 2 — pre-trained on public datasets)
    tflite_probs = None
    if _model_loaded and _interpreter is not None:
        try:
            input_data = embeddings.astype(np.float32).reshape(1, -1)
            input_details = _interpreter.get_input_details()
            output_details = _interpreter.get_output_details()
            _interpreter.set_tensor(input_details[0]["index"], input_data)
            _interpreter.invoke()
            output = _interpreter.get_tensor(output_details[0]["index"])[0]
            tflite_probs = _softmax(output)
        except Exception as e:
            logger.warning(f"TFLite model inference failed: {e}")

    # No models available
    if numpy_probs is None and tflite_probs is None:
        return _fallback_prediction()

    # Determine final probabilities (blend or single model)
    if numpy_probs is not None and tflite_probs is not None:
        # Blend: our trained model + Phase 2 public model using weight schedule
        from training_anonymizer import get_blend_weights, count_confirmed_samples
        try:
            if os.environ.get("TRAINING_FEATURES_TABLE"):
                import boto3
                _ddb = boto3.resource("dynamodb")
                _tft = _ddb.Table(os.environ["TRAINING_FEATURES_TABLE"])
                n_confirmed = count_confirmed_samples(_tft)
            else:
                n_confirmed = 0
        except Exception:
            n_confirmed = 0

        weights = get_blend_weights(n_confirmed)
        our_w = weights["our_weight"]
        pub_w = weights["public_weight"]
        probs = our_w * numpy_probs + pub_w * tflite_probs
        model_version = f"blended-v{_active_model_version}"
    elif numpy_probs is not None:
        probs = numpy_probs
        model_version = f"phase4-v{_active_model_version}"
    else:
        probs = tflite_probs
        model_version = "phase2-pretrained"

    prob_dict = {EMOTION_CLASSES[i]: float(probs[i]) for i in range(len(EMOTION_CLASSES))}
    ranked = sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)
    primary = ranked[0][0]
    confidence = ranked[0][1]

    top_emotions = [
        {"key": k, "score": round(v, 3)}
        for k, v in ranked[:3]
        if v > 0.05
    ]

    return {
        "primary_emotion": primary,
        "confidence": round(confidence, 3),
        "emotion_probabilities": {k: round(v, 3) for k, v in prob_dict.items()},
        "top_emotions": top_emotions,
        "model_version": model_version,
        "using_model": True,
    }


def _predict_numpy(embeddings: np.ndarray, age_days: Optional[int] = None) -> np.ndarray:
    """Run inference with the Phase 3/4 numpy model.

    Phase 3: single-branch softmax (weights + bias)
    Phase 4: two-branch age-conditioned (W_emb1, W_age1, etc.)
    """
    x_emb = embeddings.astype(np.float32).reshape(1, -1)

    if "W_emb1" in _numpy_model:
        # Phase 4: two-branch age-conditioned network
        age = age_days if isinstance(age_days, int) else 0
        x_age = encode_age(age).reshape(1, -1)

        # Embedding branch: 768 -> 256 -> 128
        h_emb1 = np.maximum(0, x_emb @ _numpy_model["W_emb1"] + _numpy_model["b_emb1"])
        h_emb2 = np.maximum(0, h_emb1 @ _numpy_model["W_emb2"] + _numpy_model["b_emb2"])

        # Age branch: 4 -> 16 -> 8
        h_age1 = np.maximum(0, x_age @ _numpy_model["W_age1"] + _numpy_model["b_age1"])
        h_age2 = np.maximum(0, h_age1 @ _numpy_model["W_age2"] + _numpy_model["b_age2"])

        # Concat -> 136 -> 64 -> 7
        h_concat = np.concatenate([h_emb2, h_age2], axis=1)
        h_fc1 = np.maximum(0, h_concat @ _numpy_model["W_fc1"] + _numpy_model["b_fc1"])
        logits = h_fc1 @ _numpy_model["W_fc2"] + _numpy_model["b_fc2"]
        return _softmax(logits[0])
    else:
        # Phase 3: simple softmax regression
        logits = x_emb @ _numpy_model["weights"] + _numpy_model["bias"]
        return _softmax(logits[0])


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)


def _fallback_prediction() -> Dict[str, Any]:
    """Fallback when no model is available. Returns uniform distribution."""
    n = len(EMOTION_CLASSES)
    uniform = {c: round(1.0 / n, 3) for c in EMOTION_CLASSES}
    return {
        "primary_emotion": "discomfort",
        "confidence": round(1.0 / n, 3),
        "emotion_probabilities": uniform,
        "top_emotions": [{"key": c, "score": round(1.0 / n, 3)} for c in EMOTION_CLASSES[:3]],
        "model_version": "fallback",
        "using_model": False,
    }


def map_label(raw_label: str) -> Optional[str]:
    """Map a raw dataset label to our unified taxonomy. Returns None if unmapped."""
    return LABEL_MAP.get(raw_label.lower().strip())
