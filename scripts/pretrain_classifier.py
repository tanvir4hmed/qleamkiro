#!/usr/bin/env python3
"""
Qleam — Pre-Train Emotion Classifier on Public Datasets
Trains a Dense classifier on HuBERT embeddings for 7-class cry emotion.

Usage:
    # Step 1: Extract embeddings (requires SageMaker endpoint or local HuBERT)
    python scripts/pretrain_classifier.py extract-embeddings \
        --manifest data/prepared/manifest.json \
        --endpoint qleam-dev-hubert-endpoint \
        --output data/embeddings/

    # Step 2: Train classifier
    python scripts/pretrain_classifier.py train \
        --embeddings data/embeddings/ \
        --output models/emotion_classifier.tflite

    # Step 3: Evaluate
    python scripts/pretrain_classifier.py evaluate \
        --embeddings data/embeddings/ \
        --model models/emotion_classifier.tflite
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EMOTION_CLASSES = ["hungry", "tired", "discomfort", "gas", "pain", "burp", "content"]
EMBEDDING_DIM = 768
RANDOM_SEED = 42


def extract_embeddings(manifest_path: str, endpoint_name: str, output_dir: str,
                       use_local: bool = False):
    """Extract HuBERT embeddings for all audio in the manifest."""
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    with open(manifest_path) as f:
        manifest = json.load(f)

    base_dir = Path(manifest_path).parent
    embeddings = []
    labels = []
    skipped = 0

    if use_local:
        logger.info("Using local HuBERT model (transformers library)")
        model, processor = _load_local_hubert()
    else:
        logger.info(f"Using SageMaker endpoint: {endpoint_name}")
        from hubert_client import extract_hubert_embeddings

    for i, entry in enumerate(manifest):
        audio_path = base_dir / entry["file"]
        if not audio_path.exists():
            skipped += 1
            continue

        try:
            import soundfile as sf
            audio, sr = sf.read(str(audio_path), dtype="float32")
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)

            if use_local:
                emb = _extract_local(model, processor, audio, sr)
            else:
                result = extract_hubert_embeddings(audio, sr, endpoint_name)
                emb = result["embeddings"]

            embeddings.append(emb)
            labels.append(entry["label"])

            if (i + 1) % 50 == 0:
                logger.info(f"Processed {i + 1}/{len(manifest)} samples")

        except Exception as e:
            logger.warning(f"Failed to process {entry['file']}: {e}")
            skipped += 1

    embeddings_array = np.array(embeddings, dtype=np.float32)
    labels_array = np.array(labels)

    np.save(output / "embeddings.npy", embeddings_array)
    np.save(output / "labels.npy", labels_array)

    logger.info(f"\nEmbeddings extracted: {len(embeddings)} samples, {skipped} skipped")
    logger.info(f"Shape: {embeddings_array.shape}")
    logger.info(f"Saved to: {output}")

    # Label distribution
    unique, counts = np.unique(labels_array, return_counts=True)
    for label, count in zip(unique, counts):
        logger.info(f"  {label}: {count}")


def _load_local_hubert():
    """Load HuBERT model locally using transformers."""
    from transformers import HubertModel, Wav2Vec2Processor
    processor = Wav2Vec2Processor.from_pretrained("facebook/hubert-base-ls960")
    model = HubertModel.from_pretrained("facebook/hubert-base-ls960")
    model.eval()
    return model, processor


def _extract_local(model, processor, audio: np.ndarray, sr: int) -> np.ndarray:
    """Extract embeddings using local HuBERT model."""
    import torch

    # Resample to 16kHz
    if sr != 16000:
        n = int(len(audio) * 16000 / sr)
        audio = np.interp(np.linspace(0, len(audio) - 1, n),
                          np.arange(len(audio)), audio).astype(np.float32)

    inputs = processor(audio, sampling_rate=16000, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
    # Mean pool across time
    hidden = outputs.last_hidden_state[0].numpy()
    return np.mean(hidden, axis=0)


def train(embeddings_dir: str, output_path: str, epochs: int = 50, val_split: float = 0.2):
    """Train Dense classifier on pre-extracted embeddings."""
    emb_dir = Path(embeddings_dir)
    embeddings = np.load(emb_dir / "embeddings.npy")
    labels = np.load(emb_dir / "labels.npy")

    # Encode labels to integers
    label_to_idx = {c: i for i, c in enumerate(EMOTION_CLASSES)}
    y = np.array([label_to_idx.get(l, -1) for l in labels])

    # Filter unknown labels
    valid = y >= 0
    embeddings = embeddings[valid]
    y = y[valid]

    logger.info(f"Training on {len(embeddings)} samples, {len(EMOTION_CLASSES)} classes")

    # Train/val split (stratified)
    np.random.seed(RANDOM_SEED)
    indices = np.arange(len(embeddings))
    np.random.shuffle(indices)
    n_val = int(len(indices) * val_split)
    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    X_train, y_train = embeddings[train_idx], y[train_idx]
    X_val, y_val = embeddings[val_idx], y[val_idx]

    logger.info(f"Train: {len(X_train)}, Val: {len(X_val)}")

    # Build and train model
    try:
        import tensorflow as tf
    except ImportError:
        logger.error("TensorFlow is required for training. Install with: pip install tensorflow")
        sys.exit(1)

    tf.random.set_seed(RANDOM_SEED)

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(EMBEDDING_DIM,)),
        tf.keras.layers.Dense(256, activation="relu"),
        tf.keras.layers.Dropout(0.3),
        tf.keras.layers.Dense(128, activation="relu"),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(len(EMOTION_CLASSES), activation="softmax"),
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3),
        loss="sparse_categorical_crossentropy",
        metrics=["accuracy"],
    )

    # Class weights for imbalanced data
    class_counts = np.bincount(y_train, minlength=len(EMOTION_CLASSES))
    total = len(y_train)
    class_weights = {
        i: total / (len(EMOTION_CLASSES) * max(1, c))
        for i, c in enumerate(class_counts)
    }

    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=epochs,
        batch_size=32,
        class_weight=class_weights,
        verbose=1,
    )

    # Evaluate
    val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
    logger.info(f"\nValidation accuracy: {val_acc:.3f}")
    logger.info(f"Validation loss: {val_loss:.3f}")

    # Per-class metrics
    y_pred = np.argmax(model.predict(X_val, verbose=0), axis=1)
    _print_classification_report(y_val, y_pred)

    # Export to TFLite
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    tflite_model = converter.convert()

    with open(output_file, "wb") as f:
        f.write(tflite_model)

    size_mb = len(tflite_model) / (1024 * 1024)
    logger.info(f"\nTFLite model saved: {output_file} ({size_mb:.2f} MB)")

    # Save training metadata
    meta = {
        "emotion_classes": EMOTION_CLASSES,
        "embedding_dim": EMBEDDING_DIM,
        "train_samples": len(X_train),
        "val_samples": len(X_val),
        "val_accuracy": round(float(val_acc), 4),
        "val_loss": round(float(val_loss), 4),
        "epochs": epochs,
        "model_version": "phase2-pretrained",
    }
    meta_path = output_file.with_suffix(".json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    logger.info(f"Metadata saved: {meta_path}")


def evaluate(embeddings_dir: str, model_path: str):
    """Evaluate a trained TFLite model on the validation set."""
    emb_dir = Path(embeddings_dir)
    embeddings = np.load(emb_dir / "embeddings.npy")
    labels = np.load(emb_dir / "labels.npy")

    label_to_idx = {c: i for i, c in enumerate(EMOTION_CLASSES)}
    y = np.array([label_to_idx.get(l, -1) for l in labels])
    valid = y >= 0
    embeddings = embeddings[valid]
    y = y[valid]

    # Use last 20% as val (same split as training)
    np.random.seed(RANDOM_SEED)
    indices = np.arange(len(embeddings))
    np.random.shuffle(indices)
    n_val = int(len(indices) * 0.2)
    val_idx = indices[:n_val]
    X_val, y_val = embeddings[val_idx], y[val_idx]

    # Load TFLite model
    try:
        import tensorflow as tf
        interpreter = tf.lite.Interpreter(model_path=model_path)
    except ImportError:
        import tflite_runtime.interpreter as tflite
        interpreter = tflite.Interpreter(model_path=model_path)

    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    y_pred = []
    for x in X_val:
        interpreter.set_tensor(input_details[0]["index"], x.reshape(1, -1))
        interpreter.invoke()
        output = interpreter.get_tensor(output_details[0]["index"])[0]
        y_pred.append(np.argmax(output))

    y_pred = np.array(y_pred)
    accuracy = np.mean(y_pred == y_val)
    logger.info(f"\nTFLite model accuracy: {accuracy:.3f}")
    _print_classification_report(y_val, y_pred)


def _print_classification_report(y_true: np.ndarray, y_pred: np.ndarray):
    """Print per-class precision, recall, F1."""
    n_classes = len(EMOTION_CLASSES)
    for i, cls in enumerate(EMOTION_CLASSES):
        tp = np.sum((y_pred == i) & (y_true == i))
        fp = np.sum((y_pred == i) & (y_true != i))
        fn = np.sum((y_pred != i) & (y_true == i))
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-9, precision + recall)
        support = np.sum(y_true == i)
        logger.info(f"  {cls:15s}  P={precision:.3f}  R={recall:.3f}  F1={f1:.3f}  n={support}")

    accuracy = np.mean(y_pred == y_true)
    logger.info(f"  {'accuracy':15s}  {accuracy:.3f}  (n={len(y_true)})")


def main():
    parser = argparse.ArgumentParser(description="Pre-train emotion classifier")
    subparsers = parser.add_subparsers(dest="command")

    # extract-embeddings
    ext_parser = subparsers.add_parser("extract-embeddings", help="Extract HuBERT embeddings")
    ext_parser.add_argument("--manifest", required=True, help="Path to manifest.json")
    ext_parser.add_argument("--endpoint", default="", help="SageMaker endpoint name")
    ext_parser.add_argument("--output", required=True, help="Output directory for embeddings")
    ext_parser.add_argument("--local", action="store_true",
                            help="Use local HuBERT model instead of SageMaker")

    # train
    train_parser = subparsers.add_parser("train", help="Train classifier")
    train_parser.add_argument("--embeddings", required=True, help="Embeddings directory")
    train_parser.add_argument("--output", required=True, help="Output .tflite model path")
    train_parser.add_argument("--epochs", type=int, default=50, help="Training epochs")

    # evaluate
    eval_parser = subparsers.add_parser("evaluate", help="Evaluate model")
    eval_parser.add_argument("--embeddings", required=True, help="Embeddings directory")
    eval_parser.add_argument("--model", required=True, help="Path to .tflite model")

    args = parser.parse_args()

    if args.command == "extract-embeddings":
        extract_embeddings(args.manifest, args.endpoint, args.output, use_local=args.local)
    elif args.command == "train":
        train(args.embeddings, args.output, epochs=args.epochs)
    elif args.command == "evaluate":
        evaluate(args.embeddings, args.model)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
