"""
Qleam — HuBERT Feature Extraction Client
Calls SageMaker Serverless endpoint to get 768-dim embeddings from audio.
"""
import json
import logging
import time
from typing import Dict, Optional, Tuple

import boto3
import numpy as np

logger = logging.getLogger(__name__)

_sagemaker_client = None


def _get_client():
    global _sagemaker_client
    if _sagemaker_client is None:
        _sagemaker_client = boto3.client("sagemaker-runtime")
    return _sagemaker_client


def extract_hubert_embeddings(
    audio: np.ndarray,
    sr: int,
    endpoint_name: str,
    retry_on_cold_start: bool = True,
) -> Dict:
    """
    Extract HuBERT embeddings from audio via SageMaker endpoint.

    Args:
        audio: Audio waveform (mono, float32)
        sr: Sample rate (will resample to 16kHz if needed)
        endpoint_name: SageMaker endpoint name
        retry_on_cold_start: Retry once on ModelNotReadyException (cold start)

    Returns:
        {
            "embeddings": np.ndarray (768,),  # mean-pooled
            "raw_embeddings": np.ndarray (T, 768),  # per-frame (if available)
            "latency_ms": float,
            "cold_start": bool,
        }
    """
    if not endpoint_name:
        logger.warning("No HuBERT endpoint configured, returning empty embeddings")
        return _empty_result()

    # Resample to 16kHz if needed (HuBERT expects 16kHz)
    if sr != 16000:
        audio = _resample(audio, sr, 16000)

    # Prepare payload — send as raw float32 bytes for efficiency
    payload = {
        "inputs": audio.tolist(),
    }
    payload_bytes = json.dumps(payload).encode("utf-8")

    client = _get_client()
    cold_start = False
    start = time.time()

    try:
        response = client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=payload_bytes,
        )
    except client.exceptions.ModelNotReadyException:
        if not retry_on_cold_start:
            logger.warning("HuBERT endpoint cold start, no retry")
            return _empty_result()
        cold_start = True
        logger.info("HuBERT endpoint cold start, retrying in 3s...")
        time.sleep(3)
        start = time.time()
        response = client.invoke_endpoint(
            EndpointName=endpoint_name,
            ContentType="application/json",
            Body=payload_bytes,
        )

    latency_ms = (time.time() - start) * 1000
    body = json.loads(response["Body"].read().decode("utf-8"))

    # HuggingFace feature-extraction returns nested list: [[frames x 768]]
    raw = np.array(body, dtype=np.float32)
    if raw.ndim == 3:
        raw = raw[0]  # Remove batch dimension -> (T, 768)
    elif raw.ndim == 1:
        raw = raw.reshape(1, -1)

    # Mean-pool across time frames
    embeddings = np.mean(raw, axis=0)

    logger.info(
        f"HuBERT embeddings: shape={embeddings.shape} latency={latency_ms:.0f}ms "
        f"cold_start={cold_start}"
    )

    return {
        "embeddings": embeddings,
        "raw_embeddings": raw,
        "latency_ms": round(latency_ms, 1),
        "cold_start": cold_start,
    }


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resample (avoids librosa dependency)."""
    if orig_sr == target_sr:
        return audio
    ratio = target_sr / orig_sr
    n_samples = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, n_samples)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _empty_result() -> Dict:
    return {
        "embeddings": np.zeros(768, dtype=np.float32),
        "raw_embeddings": np.zeros((1, 768), dtype=np.float32),
        "latency_ms": 0.0,
        "cold_start": False,
    }
