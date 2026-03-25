#!/usr/bin/env python3
"""
Qleam — Download and Prepare DonateACry Dataset

Downloads the DonateACry corpus from GitHub (CC license, free for research).
Converts labels to Qleam's 7-class emotion format and creates a manifest.json
ready for the pretrain_classifier.py script.

Dataset: https://github.com/gveres/donateacry-corpus
License: Creative Commons (free for research use)
Samples: ~457 labeled baby cry recordings

Label mapping (DonateACry -> Qleam):
  belly_pain -> pain
  burping     -> burp (needs_burping)
  discomfort  -> discomfort
  hungry      -> hungry
  tired       -> tired

Usage:
    python scripts/download_donateacry.py

Output:
    data/donateacry/audio/          - WAV files
    data/donateacry/manifest.json   - [{file, label, source, original_label}, ...]
"""
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/gveres/donateacry-corpus.git"
CLONE_DIR = Path("data/donateacry/_raw")
OUTPUT_DIR = Path("data/donateacry")
AUDIO_DIR = OUTPUT_DIR / "audio"
MANIFEST_PATH = OUTPUT_DIR / "manifest.json"

# DonateACry label folders -> Qleam emotion classes
LABEL_MAP = {
    "belly_pain": "pain",
    "burping": "burp",
    "discomfort": "discomfort",
    "hungry": "hungry",
    "tired": "tired",
}

# DonateACry labels we skip (not in Qleam's 7-class set)
SKIP_LABELS = {"ch", "dc", "hu", "lo", "mu", "bp"}


def main():
    # Step 1: Clone or update the repository
    if CLONE_DIR.exists():
        logger.info(f"Repository already cloned at {CLONE_DIR}")
    else:
        logger.info(f"Cloning DonateACry corpus from {REPO_URL}...")
        CLONE_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", REPO_URL, str(CLONE_DIR)],
            check=True,
        )
        logger.info("Clone complete.")

    # Step 2: Find audio files and map labels
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    skipped = 0
    copied = 0

    # DonateACry structure: donateacry-corpus/donateacry_corpus_cleaned_and_updated_data/
    corpus_root = CLONE_DIR / "donateacry_corpus_cleaned_and_updated_data"
    if not corpus_root.exists():
        # Try alternative paths
        for candidate in CLONE_DIR.rglob("*.wav"):
            corpus_root = candidate.parent
            break

    if not corpus_root.exists():
        logger.error(f"Could not find audio files in {CLONE_DIR}")
        sys.exit(1)

    logger.info(f"Scanning for audio files in {corpus_root}...")

    for wav_file in sorted(corpus_root.rglob("*.wav")):
        # DonateACry filenames encode the label in the path or filename
        # Format varies: some have label folders, some encode in filename
        parent_name = wav_file.parent.name.lower()
        filename = wav_file.stem.lower()

        # Try to determine label from parent directory name
        label = None
        for donor_label, qleam_label in LABEL_MAP.items():
            if donor_label in parent_name or donor_label in filename:
                label = qleam_label
                break

        if label is None:
            skipped += 1
            continue

        # Copy to output directory with clean name
        dest_name = f"donateacry_{copied:04d}_{label}.wav"
        dest_path = AUDIO_DIR / dest_name
        shutil.copy2(wav_file, dest_path)

        manifest.append({
            "file": f"audio/{dest_name}",
            "label": label,
            "source": "donateacry",
            "original_file": str(wav_file.relative_to(CLONE_DIR)),
        })
        copied += 1

    # Step 3: Write manifest
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    # Step 4: Summary
    label_counts = {}
    for entry in manifest:
        label_counts[entry["label"]] = label_counts.get(entry["label"], 0) + 1

    logger.info(f"\nDataset prepared: {copied} samples, {skipped} skipped")
    logger.info(f"Manifest: {MANIFEST_PATH}")
    logger.info(f"\nLabel distribution:")
    for label, count in sorted(label_counts.items()):
        logger.info(f"  {label:15s}: {count}")

    logger.info(f"\nNext steps:")
    logger.info(f"  1. Extract embeddings:")
    logger.info(f"     python scripts/pretrain_classifier.py extract-embeddings \\")
    logger.info(f"       --manifest {MANIFEST_PATH} --local --output data/embeddings/")
    logger.info(f"  2. Train classifier:")
    logger.info(f"     python scripts/pretrain_classifier.py train \\")
    logger.info(f"       --embeddings data/embeddings/ --output models/emotion_classifier.tflite")

    # Cleanup raw clone (optional)
    logger.info(f"\nTo save disk space, delete the raw clone:")
    logger.info(f"  rm -rf {CLONE_DIR}")


if __name__ == "__main__":
    main()
