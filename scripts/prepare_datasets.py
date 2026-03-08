#!/usr/bin/env python3
"""
Qleam — Prepare Public Datasets for Pre-Training
Downloads and unifies Dunstan Baby Language + DonateACry datasets.
Baby Chillanto requires manual request from CONACYT Mexico.

Usage:
    python scripts/prepare_datasets.py --output-dir data/prepared

Output structure:
    data/prepared/
        manifest.json          # [{file, label, source, duration_s}, ...]
        audio/                 # Resampled 16kHz mono WAV files
            dunstan_0001.wav
            donateacry_0001.wav
            ...
"""
import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add shared to path for label mapping
sys.path.insert(0, str(Path(__file__).parent.parent / "shared"))

TARGET_SR = 16000
TARGET_CHANNELS = 1
MAX_DURATION_S = 10.0
MIN_DURATION_S = 0.5

# Unified 7-class taxonomy
VALID_LABELS = {"hungry", "tired", "discomfort", "gas", "pain", "burp", "content"}

# Label mapping from raw dataset labels
DUNSTAN_LABEL_MAP = {
    "hungry": "hungry",
    "tired": "tired",
    "discomfort": "discomfort",
    "stomachache": "gas",
    "burping": "burp",
    "scared": "pain",
    # Discarded labels (too few samples or too ambiguous)
    # "unknown": None, "lonely": None, "cold_hot": None,
}

DONATEACRY_LABEL_MAP = {
    "hunger": "hungry",
    "tired": "tired",
    "discomfort": "discomfort",
    "belly_pain": "gas",
    "burping": "burp",
}

CHILLANTO_LABEL_MAP = {
    "hunger": "hungry",
    "normal": "content",
    "pain": "pain",
    # Discarded (pathological, different domain)
    # "asphyxia": None, "deaf": None,
}


def download_donateacry(output_dir: Path) -> List[Dict]:
    """
    Download DonateACry corpus from GitHub.
    Repository: https://github.com/gveres/donateacry-corpus
    """
    repo_url = "https://github.com/gveres/donateacry-corpus.git"
    clone_dir = output_dir / "_raw" / "donateacry"

    if not clone_dir.exists():
        logger.info(f"Cloning DonateACry to {clone_dir}...")
        subprocess.run(
            ["git", "clone", "--depth=1", repo_url, str(clone_dir)],
            check=True,
        )
    else:
        logger.info(f"DonateACry already downloaded at {clone_dir}")

    # DonateACry structure: donateacry_corpus_cleaned_and_updated_data/
    # Files named like: 0D1AD73E-4C5E-45F3-85C4-9A3CB71E8856-1430742197-1.0-m-04-hu.wav
    # Last part before .wav: hu=hunger, bp=belly_pain, bu=burping, dc=discomfort, ti=tired
    suffix_map = {
        "hu": "hunger",
        "bp": "belly_pain",
        "bu": "burping",
        "dc": "discomfort",
        "ti": "tired",
    }

    corpus_dir = clone_dir / "donateacry_corpus_cleaned_and_updated_data"
    if not corpus_dir.exists():
        # Try alternate structure
        for d in clone_dir.iterdir():
            if d.is_dir() and "corpus" in d.name.lower():
                corpus_dir = d
                break

    entries = []
    if not corpus_dir.exists():
        logger.warning(f"DonateACry corpus directory not found at {corpus_dir}")
        return entries

    for wav_file in sorted(corpus_dir.glob("*.wav")):
        stem = wav_file.stem
        # Extract label suffix
        parts = stem.rsplit("-", 1)
        if len(parts) < 2:
            continue
        suffix = parts[-1].lower()
        raw_label = suffix_map.get(suffix)
        if raw_label is None:
            continue
        mapped = DONATEACRY_LABEL_MAP.get(raw_label)
        if mapped is None or mapped not in VALID_LABELS:
            continue
        entries.append({
            "source_path": str(wav_file),
            "label": mapped,
            "source": "donateacry",
        })

    logger.info(f"DonateACry: found {len(entries)} labeled samples")
    return entries


def scan_dunstan(dunstan_dir: Path) -> List[Dict]:
    """
    Scan a local Dunstan Baby Language dataset directory.
    Expected structure: dunstan_dir/{label}/*.wav
    User must provide this — not publicly downloadable as a single repo.
    """
    if not dunstan_dir.exists():
        logger.warning(f"Dunstan directory not found: {dunstan_dir}")
        logger.info("To use Dunstan data, place audio files in: data/raw/dunstan/{label}/*.wav")
        return []

    entries = []
    for label_dir in sorted(dunstan_dir.iterdir()):
        if not label_dir.is_dir():
            continue
        raw_label = label_dir.name.lower()
        mapped = DUNSTAN_LABEL_MAP.get(raw_label)
        if mapped is None or mapped not in VALID_LABELS:
            logger.info(f"Skipping Dunstan label: {raw_label}")
            continue
        for wav_file in sorted(label_dir.glob("*.wav")):
            entries.append({
                "source_path": str(wav_file),
                "label": mapped,
                "source": "dunstan",
            })

    logger.info(f"Dunstan: found {len(entries)} labeled samples")
    return entries


def scan_chillanto(chillanto_dir: Path) -> List[Dict]:
    """
    Scan a local Baby Chillanto dataset directory.
    Must be requested from CONACYT Mexico.
    Expected structure: chillanto_dir/{label}/*.wav
    """
    if not chillanto_dir.exists():
        logger.warning(f"Chillanto directory not found: {chillanto_dir}")
        logger.info("To use Chillanto data, request from CONACYT and place in: data/raw/chillanto/{label}/*.wav")
        return []

    entries = []
    for label_dir in sorted(chillanto_dir.iterdir()):
        if not label_dir.is_dir():
            continue
        raw_label = label_dir.name.lower()
        mapped = CHILLANTO_LABEL_MAP.get(raw_label)
        if mapped is None or mapped not in VALID_LABELS:
            logger.info(f"Skipping Chillanto label: {raw_label}")
            continue
        for wav_file in sorted(label_dir.glob("*.wav")):
            entries.append({
                "source_path": str(wav_file),
                "label": mapped,
                "source": "chillanto",
            })

    logger.info(f"Chillanto: found {len(entries)} labeled samples")
    return entries


def process_audio(source_path: str, dest_path: Path) -> Optional[float]:
    """
    Resample audio to 16kHz mono WAV.
    Returns duration in seconds, or None if processing failed.
    """
    try:
        import soundfile as sf
        import numpy as np

        data, sr = sf.read(source_path, dtype="float32")
        if data.ndim > 1:
            data = np.mean(data, axis=1)

        duration_s = len(data) / sr
        if duration_s < MIN_DURATION_S or duration_s > MAX_DURATION_S:
            return None

        # Resample if needed
        if sr != TARGET_SR:
            n_samples = int(len(data) * TARGET_SR / sr)
            indices = np.linspace(0, len(data) - 1, n_samples)
            data = np.interp(indices, np.arange(len(data)), data).astype(np.float32)

        # Normalize
        peak = np.max(np.abs(data))
        if peak > 1e-8:
            data = data / peak

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(dest_path), data, TARGET_SR)
        return len(data) / TARGET_SR

    except Exception as e:
        logger.warning(f"Failed to process {source_path}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Prepare baby cry datasets for pre-training")
    parser.add_argument("--output-dir", type=str, default="data/prepared",
                        help="Output directory for prepared dataset")
    parser.add_argument("--dunstan-dir", type=str, default="data/raw/dunstan",
                        help="Path to Dunstan dataset directory")
    parser.add_argument("--chillanto-dir", type=str, default="data/raw/chillanto",
                        help="Path to Baby Chillanto dataset directory")
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip downloading DonateACry (use if already downloaded)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    audio_dir = output_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    # Collect all entries
    all_entries = []

    if not args.skip_download:
        all_entries.extend(download_donateacry(output_dir))

    all_entries.extend(scan_dunstan(Path(args.dunstan_dir)))
    all_entries.extend(scan_chillanto(Path(args.chillanto_dir)))

    if not all_entries:
        logger.error("No dataset entries found. Check paths and try again.")
        sys.exit(1)

    # Process and build manifest
    manifest = []
    counts = {}
    for i, entry in enumerate(all_entries):
        source = entry["source"]
        label = entry["label"]
        dest_name = f"{source}_{i:05d}.wav"
        dest_path = audio_dir / dest_name

        duration = process_audio(entry["source_path"], dest_path)
        if duration is None:
            continue

        manifest.append({
            "file": f"audio/{dest_name}",
            "label": label,
            "source": source,
            "duration_s": round(duration, 2),
        })
        counts[label] = counts.get(label, 0) + 1

    # Save manifest
    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    logger.info(f"\nDataset prepared: {len(manifest)} samples")
    logger.info(f"Manifest saved to: {manifest_path}")
    logger.info("Label distribution:")
    for label in sorted(counts.keys()):
        logger.info(f"  {label}: {counts[label]}")

    # Check balance
    min_count = min(counts.values()) if counts else 0
    max_count = max(counts.values()) if counts else 0
    if max_count > 3 * min_count and min_count > 0:
        logger.warning(
            f"Dataset is imbalanced (min={min_count}, max={max_count}). "
            "Consider augmenting underrepresented classes during training."
        )


if __name__ == "__main__":
    main()
