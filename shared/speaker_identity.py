"""
Qleam — Speaker Identity / Enrollment Verification (Phase 2)

Pure functions for verifying that the current session matches the enrolled baby's
acoustic profile, using cosine similarity against historical session embeddings.

Design principles:
  - No AWS calls here — the Lambda fetches embeddings and passes them in
  - Builds enrollment gradually over first few sessions
  - Never hard-rejects on mismatch — flags for review only
  - Gives benefit of the doubt until >= MIN_SESSIONS_FOR_ENROLLMENT sessions exist
"""
import logging
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
MIN_SESSIONS_FOR_ENROLLMENT: int = 3     # Sessions needed before verification starts
ENROLLMENT_MATCH_THRESHOLD: float = 0.70  # Above → confirmed enrolled baby
ENROLLMENT_UNCERTAIN_THRESHOLD: float = 0.45  # Above → uncertain, below → mismatch
TOP_K_SIMILARITIES: int = 3              # Use mean of top-K matches for robustness


# ---------------------------------------------------------------------------
# Core similarity functions
# ---------------------------------------------------------------------------

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Compute cosine similarity between two embedding vectors.
    Returns value in [-1, 1]. Returns 0.0 for zero-norm vectors.
    """
    va = np.array(a, dtype=np.float64)
    vb = np.array(b, dtype=np.float64)

    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return float(np.clip(np.dot(va, vb) / (norm_a * norm_b), -1.0, 1.0))


def compute_enrollment_similarity(
    new_embedding: List[float],
    historical_embeddings: List[List[float]],
) -> float:
    """
    Compute a robust similarity score between the new session and the
    baby's historical embedding profile.

    Method: mean of top-K cosine similarities (robust to atypical past sessions).

    Returns:
        float in [0, 1] — higher means better match to enrolled baby
    """
    if not historical_embeddings or not new_embedding:
        return 0.0

    similarities = [
        max(0.0, cosine_similarity(new_embedding, h))
        for h in historical_embeddings
        if h  # skip empty embeddings
    ]

    if not similarities:
        return 0.0

    similarities.sort(reverse=True)
    top_k = similarities[:TOP_K_SIMILARITIES]
    return round(float(np.mean(top_k)), 4)


# ---------------------------------------------------------------------------
# Enrollment verification
# ---------------------------------------------------------------------------

def verify_enrolled_baby(
    new_embedding: List[float],
    historical_embeddings: List[List[float]],
    session_count: int,
) -> Dict:
    """
    Verify whether the current session matches the enrolled baby.

    Enrollment states:
      "building"           — not enough history yet, accepting all sessions
      "verified"           — similarity >= 0.70, strong match
      "uncertain"          — similarity 0.45–0.70, plausible match
      "mismatch_suspected" — similarity < 0.45, different baby suspected

    Args:
        new_embedding:         Embedding vector from current session audio
        historical_embeddings: List of embedding vectors from past sessions
        session_count:         Total session count for child (including this one)

    Returns:
        {
            "similarity_score": float,
            "is_enrolled_baby": bool,
            "enrollment_confidence": float,   # 0–1
            "sessions_used": int,
            "enrollment_status": str,
        }
    """
    n_history = len(historical_embeddings)

    # Phase: building enrollment — not enough history to compare
    if n_history < MIN_SESSIONS_FOR_ENROLLMENT:
        confidence = n_history / MIN_SESSIONS_FOR_ENROLLMENT
        return {
            "similarity_score": 1.0,          # Assume correct during building
            "is_enrolled_baby": True,
            "enrollment_confidence": round(confidence, 4),
            "sessions_used": n_history,
            "enrollment_status": "building",
        }

    similarity = compute_enrollment_similarity(new_embedding, historical_embeddings)

    if similarity >= ENROLLMENT_MATCH_THRESHOLD:
        return {
            "similarity_score": similarity,
            "is_enrolled_baby": True,
            "enrollment_confidence": round(min(similarity, 1.0), 4),
            "sessions_used": n_history,
            "enrollment_status": "verified",
        }

    if similarity >= ENROLLMENT_UNCERTAIN_THRESHOLD:
        return {
            "similarity_score": similarity,
            "is_enrolled_baby": True,          # Benefit of the doubt
            "enrollment_confidence": round(similarity * 0.7, 4),
            "sessions_used": n_history,
            "enrollment_status": "uncertain",
        }

    # Low similarity — flag but do not reject (could be natural vocal change)
    return {
        "similarity_score": similarity,
        "is_enrolled_baby": False,
        "enrollment_confidence": round(1.0 - similarity, 4),
        "sessions_used": n_history,
        "enrollment_status": "mismatch_suspected",
    }


# ---------------------------------------------------------------------------
# Routing decision
# ---------------------------------------------------------------------------

def determine_routing(
    developmental_stage: str,
    developmental_mode: str,
    bio_result: Dict,
    enrollment_result: Dict,
    age_classification: Optional[Dict] = None,
) -> Dict:
    """
    Determine which analysis pipeline to use for this session.

    Analysis types:
      "infant_vocalization"               — PRE_LINGUISTIC standard path
      "infant_vocalization_proto_word"    — TRANSITION: add proto-word detection
      "speech_analysis"                   — LINGUISTIC: MLU / vocabulary (Phase 7)
      "adult_mimicry_flagged"             — Adult confirmed by multi-feature evidence
      "low_confidence"                    — Classifier returned UNKNOWN, flag for review

    Adult detection priority (OR logic — any one triggers adult_mimicry_flagged):
      A. bio_result["mimicry_suspected"]=True AND bio_confidence ≥ 0.70
         (bio_result is already reconciled with Phase-4 probabilistic classifier)
      B. age_classification["is_adult"]=True AND confidence ≥ 0.70

    Returns:
        {
            "mode":          str,
            "stage":         str,
            "analysis_type": str,
            "adult_evidence": list,   # audit trail of what triggered adult detection
        }
    """
    mode_to_analysis = {
        "PRE_LINGUISTIC": "infant_vocalization",
        "TRANSITION":     "infant_vocalization_proto_word",
        "LINGUISTIC":     "speech_analysis",
    }

    analysis_type  = mode_to_analysis.get(developmental_mode, "infant_vocalization")
    adult_evidence: list = []

    # --- Adult detection path A: bio_result (already reconciled with Phase 4) ---
    bio_mimicry = bio_result.get("mimicry_suspected", False)
    bio_conf    = float(bio_result.get("bio_confidence", 0.0))
    if bio_mimicry and bio_conf >= 0.70:
        analysis_type = "adult_mimicry_flagged"
        adult_evidence.append(
            f"bio_mimicry:conf={bio_conf:.2f} "
            f"cat={bio_result.get('speaker_category', '?')} "
            f"src={bio_result.get('classifier_source', 'bio_validator')}"
        )

    # --- Adult detection path B: direct probabilistic classifier signal ---
    if age_classification:
        age_is_adult   = age_classification.get("is_adult", False)
        age_conf       = float(age_classification.get("confidence", 0.0))
        age_voice_type = age_classification.get("voice_type", "")

        if age_is_adult and age_conf >= 0.70:
            analysis_type = "adult_mimicry_flagged"
            adult_evidence.append(
                f"age_classifier:class={age_classification.get('final_class')} "
                f"conf={age_conf:.2f} voice_type={age_voice_type}"
            )

        # Low-confidence / noise signal — flag for review but don't block pipeline
        if (
            age_classification.get("is_unknown", False)
            and age_voice_type == "noise"
            and analysis_type != "adult_mimicry_flagged"
        ):
            analysis_type = "low_confidence"

    return {
        "mode":           developmental_mode,
        "stage":          developmental_stage,
        "analysis_type":  analysis_type,
        "adult_evidence": adult_evidence,
    }
