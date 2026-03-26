"""
Qleam — Model Trainer Lambda (Phase 4)
Orchestrated by Step Function. Each invocation handles one step:

Steps:
  load     — Query confirmed training data, load embeddings + age from S3
  train    — Train two-branch age-conditioned classifier
  validate — Evaluate on held-out split, compare to current active model
  promote  — Upload new model to S3, update ModelVersions table

Input: { "step": "load|train|validate|promote", ...context from previous step }
Output: Step result merged with context for next step.
"""
import io
import json
import logging
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List

import boto3
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import S3_BUCKET_NAME, TRAINING_FEATURES_TABLE
from emotion_classifier import EMOTION_CLASSES
from age_encoder import encode_age, encode_age_batch, AGE_DIM

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")

MODEL_VERSIONS_TABLE = os.environ.get("MODEL_VERSIONS_TABLE", "")
EMBEDDING_DIM = 768
RANDOM_SEED = 42
MIN_SAMPLES = 30
MIN_SAMPLES_PER_CLASS = 3
VAL_SPLIT = 0.2


def lambda_handler(event, context):
    """Route to the appropriate training step."""
    step = event.get("step", "load")
    logger.info(f"Model trainer step: {step}")

    try:
        if step == "load":
            return _step_load(event)
        elif step == "train":
            return _step_train(event)
        elif step == "validate":
            return _step_validate(event)
        elif step == "promote":
            return _step_promote(event)
        else:
            return {"error": f"Unknown step: {step}"}
    except Exception as e:
        logger.error(f"Model trainer error at step={step}: {e}", exc_info=True)
        return {"error": str(e), "step": step}


def _step_load(event: Dict) -> Dict:
    """
    Load confirmed training data from DynamoDB + S3, including age_days.
    Phase 3: Filter by age bucket (day/week/slot).
    """
    if not TRAINING_FEATURES_TABLE:
        return {"error": "TRAINING_FEATURES_TABLE not configured"}

    table = dynamodb.Table(TRAINING_FEATURES_TABLE)
    bucket = S3_BUCKET_NAME

    # Phase 3: Get bucket parameters
    bucket_type = event.get("bucket_type")  # "day", "week", or "slot"
    bucket_value = event.get("bucket_value")  # e.g., "45", "6", "0_90"
    communication_stage = event.get("communication_stage", "A")

    # Query samples for this specific bucket
    from boto3.dynamodb.conditions import Attr

    if bucket_type and bucket_value:
        # Bucket-specific training
        filter_expr = Attr("is_confirmed").eq(True)
        
        if bucket_type == "day":
            filter_expr = filter_expr & Attr("age_day_bucket").eq(int(bucket_value))
        elif bucket_type == "week":
            filter_expr = filter_expr & Attr("age_week_bucket").eq(int(bucket_value))
        elif bucket_type == "slot":
            filter_expr = filter_expr & Attr("age_slot_bucket").eq(bucket_value)
        
        logger.info(f"Loading samples for {bucket_type}={bucket_value}, stage={communication_stage}")
    else:
        # Global training (backward compatibility)
        filter_expr = Attr("is_confirmed").eq(True)
        logger.info("Loading all confirmed samples (global training)")

    response = table.scan(FilterExpression=filter_expr)
    items = response.get("Items", [])

    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.scan(
            FilterExpression=filter_expr,
            ExclusiveStartKey=response["LastEvaluatedKey"],
        )
        items.extend(response.get("Items", []))

    logger.info(f"Found {len(items)} confirmed training samples for bucket")

    if len(items) < MIN_SAMPLES:
        return {
            "step": "train",
            "skip": True,
            "reason": f"insufficient_samples:{len(items)}<{MIN_SAMPLES}",
            "accuracy_improved": False,
        }

    # Load embeddings and age_days from S3
    embeddings = []
    labels = []
    age_days_list = []
    feature_ids = []
    skipped = 0

    for item in items:
        s3_key = item.get("s3_embeddings_path", "")
        emotion = item.get("confirmed_emotion", "")
        if not s3_key or emotion not in EMOTION_CLASSES:
            skipped += 1
            continue

        try:
            obj = s3_client.get_object(Bucket=bucket, Key=s3_key)
            buf = io.BytesIO(obj["Body"].read())
            emb = np.load(buf)
            if emb.shape[0] == EMBEDDING_DIM:
                embeddings.append(emb)
                labels.append(emotion)
                age_days_list.append(int(item.get("age_days", 0)))
                feature_ids.append(str(item.get("feature_id", "")))
        except Exception as e:
            logger.warning(f"Failed to load embedding {s3_key}: {e}")
            skipped += 1

    logger.info(f"Loaded {len(embeddings)} embeddings, skipped {skipped}")

    if len(embeddings) < MIN_SAMPLES:
        return {
            "step": "train",
            "skip": True,
            "reason": f"insufficient_valid_embeddings:{len(embeddings)}",
            "accuracy_improved": False,
        }

    # Check class balance
    label_counts = {}
    for l in labels:
        label_counts[l] = label_counts.get(l, 0) + 1

    valid_classes = [c for c in EMOTION_CLASSES if label_counts.get(c, 0) >= MIN_SAMPLES_PER_CLASS]
    if len(valid_classes) < 2:
        return {
            "step": "train",
            "skip": True,
            "reason": f"too_few_classes:{len(valid_classes)}",
            "accuracy_improved": False,
        }

    # Save loaded data to S3 temp location for train step
    train_id = f"train-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    temp_prefix = f"training-runs/{train_id}"

    embeddings_array = np.array(embeddings, dtype=np.float32)
    labels_array = np.array(labels)
    age_encodings = encode_age_batch(age_days_list)

    # Upload to S3
    _upload_numpy(bucket, f"{temp_prefix}/embeddings.npy", embeddings_array)
    _upload_numpy(bucket, f"{temp_prefix}/labels.npy", labels_array)
    _upload_numpy(bucket, f"{temp_prefix}/age_encodings.npy", age_encodings)

    feature_ids_bytes = json.dumps(feature_ids).encode("utf-8")
    s3_client.put_object(Bucket=bucket, Key=f"{temp_prefix}/feature_ids.json",
                         Body=feature_ids_bytes)

    return {
        "step": "train",
        "skip": False,
        "train_id": train_id,
        "temp_prefix": temp_prefix,
        "bucket": bucket,
        "bucket_type": bucket_type,
        "bucket_value": bucket_value,
        "communication_stage": communication_stage,
        "n_samples": len(embeddings),
        "n_classes": len(valid_classes),
        "valid_classes": valid_classes,
        "label_counts": label_counts,
        "trigger_reason": event.get("trigger_reason", ""),
    }


def _step_train(event: Dict) -> Dict:
    """Train two-branch age-conditioned classifier."""
    if event.get("skip"):
        return event

    bucket = event["bucket"]
    prefix = event["temp_prefix"]
    train_id = event["train_id"]

    # Load data from S3
    embeddings = _download_numpy(bucket, f"{prefix}/embeddings.npy")
    labels = _download_numpy(bucket, f"{prefix}/labels.npy")
    age_encodings = _download_numpy(bucket, f"{prefix}/age_encodings.npy")

    # Encode labels
    label_to_idx = {c: i for i, c in enumerate(EMOTION_CLASSES)}
    y = np.array([label_to_idx.get(str(l), -1) for l in labels])

    valid_mask = y >= 0
    embeddings = embeddings[valid_mask]
    age_encodings = age_encodings[valid_mask]
    y = y[valid_mask]

    # Train/val split
    np.random.seed(RANDOM_SEED)
    indices = np.arange(len(embeddings))
    np.random.shuffle(indices)
    n_val = max(1, int(len(indices) * VAL_SPLIT))

    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    X_emb_train, X_age_train, y_train = embeddings[train_idx], age_encodings[train_idx], y[train_idx]
    X_emb_val, X_age_val, y_val = embeddings[val_idx], age_encodings[val_idx], y[val_idx]

    logger.info(f"Training: {len(X_emb_train)} samples, Validation: {len(X_emb_val)} samples")

    # Train two-branch network
    n_classes = len(EMOTION_CLASSES)
    params, train_history = _train_two_branch(
        X_emb_train, X_age_train, y_train, n_classes,
        epochs=50, lr=0.001, reg=1e-4, batch_size=32,
    )

    # Evaluate on validation set
    val_logits = _forward_two_branch(params, X_emb_val, X_age_val)
    val_preds = np.argmax(val_logits, axis=1)
    val_accuracy = float(np.mean(val_preds == y_val))

    logger.info(f"Validation accuracy: {val_accuracy:.3f}")
    # Save model weights to S3
    model_key = f"{prefix}/model_weights.npz"
    buf = io.BytesIO()
    np.savez(buf, **params)
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=model_key, Body=buf.read())

    return {
        **event,
        "step": "validate",
        "model_key": model_key,
        "val_accuracy": val_accuracy,
        "train_samples": len(X_emb_train),
        "val_samples": len(X_emb_val),
        "train_loss_final": train_history[-1] if train_history else None,
        "stopped_epoch": len(train_history),
    }


def _step_validate(event: Dict) -> Dict:
    """
    Compare new model accuracy to current active model.
    Bug Fix #9: Minimum promotion threshold 55% (above random for 7-class).
    """
    if event.get("skip"):
        return event

    val_accuracy = event.get("val_accuracy", 0)

    current_accuracy = _get_active_model_accuracy()
    logger.info(
        f"Model comparison: new={val_accuracy:.3f} vs current={current_accuracy:.3f}"
    )

    PROMOTION_MARGIN = 0.02
    MIN_PROMOTION_ACCURACY = 0.55  # Bug Fix #9: Above random (14%) + meaningful margin
    
    accuracy_improved = val_accuracy > (current_accuracy + PROMOTION_MARGIN)

    # If no current model, require minimum 55% accuracy (not 30%)
    if current_accuracy == 0 and val_accuracy >= MIN_PROMOTION_ACCURACY:
        accuracy_improved = True

    return {
        **event,
        "step": "promote",
        "accuracy_improved": accuracy_improved,
        "current_accuracy": current_accuracy,
    }


def _step_promote(event: Dict) -> Dict:
    """
    Promote new model: copy to permanent S3 path, update ModelVersions.
    Phase 3: Store with bucket-specific composite key.
    """
    bucket = event["bucket"]
    model_key = event["model_key"]
    train_id = event["train_id"]
    val_accuracy = event.get("val_accuracy", 0)
    prefix = event["temp_prefix"]
    
    # Phase 3: Bucket parameters
    bucket_type = event.get("bucket_type", "global")
    bucket_value = event.get("bucket_value", "all")
    communication_stage = event.get("communication_stage", "A")

    current_version = _get_active_model_version(bucket_type, bucket_value)
    new_version = current_version + 1

    # Phase 3: S3 path includes bucket hierarchy
    # models/{stage}/{bucket_type}/{bucket_value}/v{N}/model_weights.npz
    permanent_key = f"models/{communication_stage}/{bucket_type}/{bucket_value}/v{new_version}/model_weights.npz"
    s3_client.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": model_key},
        Key=permanent_key,
    )

    if MODEL_VERSIONS_TABLE:
        mv_table = dynamodb.Table(MODEL_VERSIONS_TABLE)
        now = datetime.now(timezone.utc).isoformat()

        if current_version > 0:
            try:
                mv_table.update_item(
                    Key={"model_type": "emotion_classifier",
                         "version": Decimal(str(current_version))},
                    UpdateExpression="SET active = :f",
                    ConditionExpression=(
                        "age_bucket_type = :bt AND age_bucket_value = :bv"
                    ),
                    ExpressionAttributeValues={
                        ":f": False,
                        ":bt": bucket_type,
                        ":bv": bucket_value,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to deactivate v{current_version}: {e}")

        mv_table.put_item(Item={
            "model_type": "emotion_classifier",
            "version": Decimal(str(new_version)),
            "s3_path": permanent_key,
            "s3_bucket": bucket,
            "age_bucket_type": bucket_type,
            "age_bucket_value": bucket_value,
            "communication_stage": communication_stage,
            "accuracy": Decimal(str(round(val_accuracy, 4))),
            "train_samples": Decimal(str(event.get("train_samples", 0))),
            "val_samples": Decimal(str(event.get("val_samples", 0))),
            "active": True,
            "trained_at": now,
            "train_id": train_id,
            "trigger_reason": event.get("trigger_reason", ""),
            "label_counts": json.dumps(event.get("label_counts", {})),
            "model_architecture": "two_branch_age_conditioned",
        })

    _mark_features_as_trained(bucket, prefix, train_id)

    logger.info(
        f"Model promoted: {bucket_type}={bucket_value} v{new_version} "
        f"accuracy={val_accuracy:.3f} s3={permanent_key}"
    )

    return {
        "status": "promoted",
        "version": new_version,
        "bucket_type": bucket_type,
        "bucket_value": bucket_value,
        "communication_stage": communication_stage,
        "accuracy": val_accuracy,
        "s3_path": permanent_key,
        "train_id": train_id,
        "accuracy_improved": True,
    }


# ---------------------------------------------------------------------------
# Two-branch age-conditioned network (numpy-only backprop)
# ---------------------------------------------------------------------------

def _init_params(n_classes):
    """Initialize two-branch network parameters.

    Architecture (from PHASE_4_AGE_CLASSIFIER.md):
      Embedding branch: 768 -> 256 (ReLU) -> 128 (ReLU)
      Age branch:       4 -> 16 (ReLU) -> 8 (ReLU)
      Concat:           136 -> 64 (ReLU) -> n_classes (softmax)
    """
    np.random.seed(RANDOM_SEED)

    def xavier(fan_in, fan_out):
        return np.random.randn(fan_in, fan_out).astype(np.float32) * np.sqrt(2.0 / fan_in)

    return {
        "W_emb1": xavier(EMBEDDING_DIM, 256), "b_emb1": np.zeros(256, dtype=np.float32),
        "W_emb2": xavier(256, 128),           "b_emb2": np.zeros(128, dtype=np.float32),
        "W_age1": xavier(AGE_DIM, 16),        "b_age1": np.zeros(16, dtype=np.float32),
        "W_age2": xavier(16, 8),              "b_age2": np.zeros(8, dtype=np.float32),
        "W_fc1":  xavier(136, 64),            "b_fc1":  np.zeros(64, dtype=np.float32),
        "W_fc2":  xavier(64, n_classes),      "b_fc2":  np.zeros(n_classes, dtype=np.float32),
    }


def _relu(x):
    return np.maximum(0, x)


def _softmax_batch(x):
    x = x - x.max(axis=1, keepdims=True)
    e = np.exp(x)
    return e / (e.sum(axis=1, keepdims=True) + 1e-9)


def _forward_two_branch(params, X_emb, X_age):
    """Forward pass returning logits (before softmax)."""
    h_emb1 = _relu(X_emb @ params["W_emb1"] + params["b_emb1"])
    h_emb2 = _relu(h_emb1 @ params["W_emb2"] + params["b_emb2"])

    h_age1 = _relu(X_age @ params["W_age1"] + params["b_age1"])
    h_age2 = _relu(h_age1 @ params["W_age2"] + params["b_age2"])

    h_concat = np.concatenate([h_emb2, h_age2], axis=1)
    h_fc1 = _relu(h_concat @ params["W_fc1"] + params["b_fc1"])
    logits = h_fc1 @ params["W_fc2"] + params["b_fc2"]
    return logits


def _train_two_branch(X_emb, X_age, y, n_classes, epochs=50, lr=0.001, reg=1e-4, batch_size=32):
    """Train two-branch network with full manual backpropagation.

    Improvements over naive fixed-LR loop:
    - Exponential LR decay (0.95 per epoch, floor 1e-5): takes big steps early,
      fine-tunes later without overshooting.
    - Early stopping (patience=8, min_delta=0.001): stops when validation loss
      stops improving, returns the best checkpoint — not the final overfit state.
    - Internal val split (15% of training data) used only for early stopping;
      the outer val split in _step_train is still used for final accuracy reporting.
    """
    params = _init_params(n_classes)
    n_samples = len(X_emb)
    losses = []

    # Early stopping / LR decay config
    PATIENCE = 8
    MIN_DELTA = 0.001
    LR_DECAY = 0.95
    MIN_LR = 1e-5

    # Internal val split for early stopping (15% of training data)
    n_internal_val = max(1, int(n_samples * 0.15))
    perm_init = np.random.permutation(n_samples)
    iv_idx = perm_init[:n_internal_val]
    it_idx = perm_init[n_internal_val:]

    X_emb_t, X_age_t, y_t = X_emb[it_idx], X_age[it_idx], y[it_idx]
    X_emb_v, X_age_v, y_v = X_emb[iv_idx], X_age[iv_idx], y[iv_idx]

    best_val_loss = float("inf")
    epochs_no_improve = 0
    best_params = None
    current_lr = lr

    for epoch in range(epochs):
        # LR decay
        current_lr = max(MIN_LR, lr * (LR_DECAY ** epoch))

        perm = np.random.permutation(len(X_emb_t))
        X_emb_s = X_emb_t[perm]
        X_age_s = X_age_t[perm]
        y_s = y_t[perm]

        epoch_loss = 0.0
        n_batches = 0

        for start in range(0, len(X_emb_t), batch_size):
            end = min(start + batch_size, len(X_emb_t))
            xe = X_emb_s[start:end]
            xa = X_age_s[start:end]
            yb = y_s[start:end]
            bs = len(xe)

            # Forward pass with activations cached
            z_emb1 = xe @ params["W_emb1"] + params["b_emb1"]
            h_emb1 = _relu(z_emb1)
            z_emb2 = h_emb1 @ params["W_emb2"] + params["b_emb2"]
            h_emb2 = _relu(z_emb2)

            z_age1 = xa @ params["W_age1"] + params["b_age1"]
            h_age1 = _relu(z_age1)
            z_age2 = h_age1 @ params["W_age2"] + params["b_age2"]
            h_age2 = _relu(z_age2)

            h_concat = np.concatenate([h_emb2, h_age2], axis=1)
            z_fc1 = h_concat @ params["W_fc1"] + params["b_fc1"]
            h_fc1 = _relu(z_fc1)
            logits = h_fc1 @ params["W_fc2"] + params["b_fc2"]

            probs = _softmax_batch(logits)

            # Loss (cross-entropy + L2 regularisation)
            loss = -np.log(probs[np.arange(bs), yb] + 1e-9).mean()
            for k in params:
                if k.startswith("W_"):
                    loss += 0.5 * reg * np.sum(params[k] ** 2)
            epoch_loss += loss
            n_batches += 1

            # Backward
            dlogits = probs.copy()
            dlogits[np.arange(bs), yb] -= 1
            dlogits /= bs

            # fc2
            dW_fc2 = h_fc1.T @ dlogits + reg * params["W_fc2"]
            db_fc2 = dlogits.sum(axis=0)
            dh_fc1 = dlogits @ params["W_fc2"].T

            # fc1 (relu)
            dz_fc1 = dh_fc1 * (z_fc1 > 0)
            dW_fc1 = h_concat.T @ dz_fc1 + reg * params["W_fc1"]
            db_fc1 = dz_fc1.sum(axis=0)
            dh_concat = dz_fc1 @ params["W_fc1"].T

            # Split concat gradient
            dh_emb2 = dh_concat[:, :128]
            dh_age2 = dh_concat[:, 128:]

            # emb2 (relu)
            dz_emb2 = dh_emb2 * (z_emb2 > 0)
            dW_emb2 = h_emb1.T @ dz_emb2 + reg * params["W_emb2"]
            db_emb2 = dz_emb2.sum(axis=0)
            dh_emb1 = dz_emb2 @ params["W_emb2"].T

            # emb1 (relu)
            dz_emb1 = dh_emb1 * (z_emb1 > 0)
            dW_emb1 = xe.T @ dz_emb1 + reg * params["W_emb1"]
            db_emb1 = dz_emb1.sum(axis=0)

            # age2 (relu)
            dz_age2 = dh_age2 * (z_age2 > 0)
            dW_age2 = h_age1.T @ dz_age2 + reg * params["W_age2"]
            db_age2 = dz_age2.sum(axis=0)
            dh_age1 = dz_age2 @ params["W_age2"].T

            # age1 (relu)
            dz_age1 = dh_age1 * (z_age1 > 0)
            dW_age1 = xa.T @ dz_age1 + reg * params["W_age1"]
            db_age1 = dz_age1.sum(axis=0)

            # Update all params with current (decayed) LR
            grads = {
                "W_emb1": dW_emb1, "b_emb1": db_emb1,
                "W_emb2": dW_emb2, "b_emb2": db_emb2,
                "W_age1": dW_age1, "b_age1": db_age1,
                "W_age2": dW_age2, "b_age2": db_age2,
                "W_fc1": dW_fc1,   "b_fc1": db_fc1,
                "W_fc2": dW_fc2,   "b_fc2": db_fc2,
            }
            for k in params:
                params[k] -= current_lr * grads[k]

        avg_loss = epoch_loss / max(1, n_batches)
        losses.append(float(avg_loss))

        # --- Early stopping: compute validation loss ---
        val_logits = _forward_two_branch(params, X_emb_v, X_age_v)
        val_probs = _softmax_batch(val_logits)
        val_loss = float(-np.log(val_probs[np.arange(len(y_v)), y_v] + 1e-9).mean())

        if val_loss < best_val_loss - MIN_DELTA:
            best_val_loss = val_loss
            epochs_no_improve = 0
            best_params = {k: v.copy() for k, v in params.items()}
        else:
            epochs_no_improve += 1

        if (epoch + 1) % 10 == 0:
            logger.info(
                f"Epoch {epoch+1}/{epochs} loss={avg_loss:.4f} "
                f"val_loss={val_loss:.4f} lr={current_lr:.6f}"
            )

        if epochs_no_improve >= PATIENCE:
            logger.info(
                f"Early stopping at epoch {epoch+1} "
                f"(no improvement for {PATIENCE} epochs, best_val_loss={best_val_loss:.4f})"
            )
            break

    # Return best checkpoint (not final — avoids returning overfit weights)
    return best_params if best_params is not None else params, losses


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_active_model_accuracy() -> float:
    if not MODEL_VERSIONS_TABLE:
        return 0.0
    try:
        mv_table = dynamodb.Table(MODEL_VERSIONS_TABLE)
        from boto3.dynamodb.conditions import Key, Attr
        # Query by partition key (model_type) — no scan needed
        response = mv_table.query(
            KeyConditionExpression=Key("model_type").eq("emotion_classifier"),
            FilterExpression=Attr("active").eq(True),
            Limit=5,
        )
        items = response.get("Items", [])
        if items:
            return float(items[0].get("accuracy", 0))
    except Exception as e:
        logger.warning(f"Failed to get active model accuracy: {e}")
    return 0.0


def _get_active_model_version(bucket_type: str = "global", bucket_value: str = "all") -> int:
    """Get the active model version for a specific bucket."""
    if not MODEL_VERSIONS_TABLE:
        return 0
    try:
        mv_table = dynamodb.Table(MODEL_VERSIONS_TABLE)
        from boto3.dynamodb.conditions import Key, Attr
        # Query by partition key (model_type), filter by bucket and active
        response = mv_table.query(
            KeyConditionExpression=Key("model_type").eq("emotion_classifier"),
            FilterExpression=(
                Attr("active").eq(True) &
                Attr("age_bucket_type").eq(bucket_type) &
                Attr("age_bucket_value").eq(bucket_value)
            ),
            Limit=5,
        )
        items = response.get("Items", [])
        if items:
            return int(items[0].get("version", 0))
    except Exception as e:
        logger.warning(f"Failed to get active model version: {e}")
    return 0


def _mark_features_as_trained(bucket, prefix, train_id):
    try:
        obj = s3_client.get_object(Bucket=bucket, Key=f"{prefix}/feature_ids.json")
        feature_ids = json.loads(obj["Body"].read().decode("utf-8"))

        if not TRAINING_FEATURES_TABLE:
            return

        table = dynamodb.Table(TRAINING_FEATURES_TABLE)
        now = datetime.now(timezone.utc).isoformat()

        for fid in feature_ids:
            try:
                table.update_item(
                    Key={"feature_id": fid},
                    UpdateExpression="SET included_in_training = :tid, trained_at = :ts",
                    ExpressionAttributeValues={
                        ":tid": train_id,
                        ":ts": now,
                    },
                )
            except Exception:
                pass

        logger.info(f"Marked {len(feature_ids)} features as trained")
    except Exception as e:
        logger.warning(f"Failed to mark features as trained: {e}")


def _upload_numpy(bucket, key, arr):
    buf = io.BytesIO()
    np.save(buf, arr)
    buf.seek(0)
    s3_client.put_object(Bucket=bucket, Key=key, Body=buf.read())


def _download_numpy(bucket, key):
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    buf = io.BytesIO(obj["Body"].read())
    return np.load(buf, allow_pickle=True)
