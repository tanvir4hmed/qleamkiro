"""
Qleam — Emotion Classifier (BRAIN)
Lightweight classifier that takes HuBERT embeddings and predicts cry emotions.

Phase 2: Pre-trained on public datasets (Dunstan + DonateACry + Baby Chillanto).
Phase 3: Fine-tuned with parent-confirmed data.
Phase 4: age_days added as continuous input with sin encoding.

Model format: TFLite (~2MB), loaded from S3 or bundled as Lambda layer.
"""
import logging
import os
from typing import Any, Dict, List, Optional

import numpy as np

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


def load_model(model_path: Optional[str] = None) -> bool:
    """
    Load TFLite emotion classifier model.

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


def predict_emotion(
    embeddings: np.ndarray,
    age_days: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Predict cry emotion from HuBERT embeddings.

    Args:
        embeddings: 768-dim HuBERT embeddings (mean-pooled)
        age_days: Child age in days (used in Phase 4, ignored in Phase 2)

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
    if not _model_loaded or _interpreter is None:
        return _fallback_prediction(embeddings)

    try:
        input_details = _interpreter.get_input_details()
        output_details = _interpreter.get_output_details()

        # Prepare input — reshape to (1, 768)
        input_data = embeddings.astype(np.float32).reshape(1, -1)

        # Phase 4 will add age encoding here
        # if age_days is not None:
        #     age_features = _encode_age(age_days)
        #     input_data = np.concatenate([input_data, age_features], axis=1)

        _interpreter.set_tensor(input_details[0]["index"], input_data)
        _interpreter.invoke()
        output = _interpreter.get_tensor(output_details[0]["index"])[0]

        # Softmax probabilities
        probs = _softmax(output)
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
            "model_version": "phase2-pretrained",
            "using_model": True,
        }

    except Exception as e:
        logger.warning(f"Emotion classifier inference failed: {e}")
        return _fallback_prediction(embeddings)


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / (e.sum() + 1e-9)


def _fallback_prediction(embeddings: np.ndarray) -> Dict[str, Any]:
    """
    Fallback when model is not available.
    Returns uniform distribution — lets cry_analyzer rule-based scoring handle it.
    """
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
