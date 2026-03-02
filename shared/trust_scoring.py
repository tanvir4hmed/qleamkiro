"""
Qleam — Trust Scoring Module (Phase 11)

Implements parent trust scoring (FRS), context reliability (CRS),
delta score (DS), and fraud signal detection.

Feedback is NOT a direct evidence source — instead it drives trust metrics
that gate training candidate acceptance and FL quality.

FRS (Feedback Reliability Score):
  - Asymmetric EMA: trust increases 3x faster than it decreases
  - Floor 0.05, ceiling 0.95 — never fully trust or distrust
  - Parents never see their FRS

CRS (Context Reliability Score):
  - How much to trust parent-provided context (feeding time, health)
  - Updated when context predictions match/mismatch outcomes

Delta Score (DS):
  - Measures distance between feedback and acoustic evidence
  - Gates training candidate acceptance (high DS = good quality sample)
"""
import logging
import math
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agreement Signal
# ---------------------------------------------------------------------------

def compute_agreement_signal(
    feedback_intent: str,
    acoustic_top: str,
    research_top: str,
    blended_top: str,
    confidences: Optional[Dict[str, float]] = None,
) -> Tuple[str, float]:
    """
    Compute agreement between parent feedback and model sources.

    Agreement levels:
      STRONG_AGREE:     feedback matches acoustic AND research top → +0.8 to +1.0
      PARTIAL_AGREE:    feedback matches acoustic OR research → +0.4
      NEUTRAL:          feedback matches blended but not individual sources → +0.1
      MILD_CONTRADICT:  feedback differs, model confidence < 0.5 → -0.2
      STRONG_CONTRADICT: feedback differs, acoustic+research tightly agree → -0.6 to -0.9

    Returns:
        (level_name, agreement_score) where score is in [-1.0, 1.0]
    """
    if not feedback_intent:
        return "NEUTRAL", 0.0

    fb = feedback_intent.lower().strip()
    ac = (acoustic_top or "").lower().strip()
    re = (research_top or "").lower().strip()
    bl = (blended_top or "").lower().strip()

    confs = confidences or {}
    acoustic_conf = float(confs.get("acoustic", 0.5))
    blended_conf = float(confs.get("blended", 0.5))

    # Strong agreement: matches both acoustic and research
    if fb == ac and fb == re:
        score = 0.8 + 0.2 * min(acoustic_conf, 1.0)
        return "STRONG_AGREE", round(min(score, 1.0), 4)

    # Partial agreement: matches one of acoustic/research
    if fb == ac or fb == re:
        return "PARTIAL_AGREE", 0.4

    # Neutral: matches blended but not individual sources
    if fb == bl:
        return "NEUTRAL", 0.1

    # Contradiction — severity depends on model confidence
    if acoustic_conf < 0.5:
        return "MILD_CONTRADICT", -0.2

    # Strong contradiction: acoustic and research agree on something else
    if ac == re and acoustic_conf >= 0.6:
        score = -0.6 - 0.3 * min(acoustic_conf, 1.0)
        return "STRONG_CONTRADICT", round(max(score, -1.0), 4)

    return "MILD_CONTRADICT", round(-0.2 - 0.1 * acoustic_conf, 4)


# ---------------------------------------------------------------------------
# Fraud Signal Detection
# ---------------------------------------------------------------------------

def detect_fraud_signal(
    feedback_timestamp: Optional[str],
    insight_generated_at: Optional[str],
    recent_responses: Optional[List[str]] = None,
    current_frs: float = 0.5,
) -> Dict:
    """
    Detect potential fraud signals in parent feedback.

    Signals:
      MISCLICK_SUSPECTED: < 3s after insight → alpha=0.0 (discard)
      UNIFORM_PATTERN:    ≥80% same response in last 10 → alpha=0.02
      ADVERSARIAL:        FRS < 0.20 → alpha=0.25 (fast re-assessment)
      NONE:               Normal → None (use agreement-based alpha)

    Returns:
        {"signal": str, "alpha_override": float|None, "detail": str}
    """
    try:
        from constants import (
            FRAUD_MISCLICK_SECONDS,
            FRAUD_UNIFORM_RATIO,
            FRAUD_UNIFORM_WINDOW,
            FRAUD_ADVERSARIAL_FRS,
            FRAUD_ADVERSARIAL_ALPHA,
        )
    except ImportError:
        FRAUD_MISCLICK_SECONDS = 3.0
        FRAUD_UNIFORM_RATIO = 0.80
        FRAUD_UNIFORM_WINDOW = 10
        FRAUD_ADVERSARIAL_FRS = 0.20
        FRAUD_ADVERSARIAL_ALPHA = 0.25

    # Check misclick (< 3s after insight)
    if feedback_timestamp and insight_generated_at:
        try:
            from datetime import datetime, timezone
            fb_time = datetime.fromisoformat(feedback_timestamp.replace("Z", "+00:00"))
            ins_time = datetime.fromisoformat(insight_generated_at.replace("Z", "+00:00"))
            seconds_diff = (fb_time - ins_time).total_seconds()
            if 0 <= seconds_diff < FRAUD_MISCLICK_SECONDS:
                return {
                    "signal": "MISCLICK_SUSPECTED",
                    "alpha_override": 0.0,
                    "detail": f"Feedback {seconds_diff:.1f}s after insight (< {FRAUD_MISCLICK_SECONDS}s)",
                }
        except (ValueError, TypeError):
            pass

    # Check uniform pattern (≥80% same response in last window)
    responses = recent_responses or []
    if len(responses) >= FRAUD_UNIFORM_WINDOW:
        window = responses[-FRAUD_UNIFORM_WINDOW:]
        if window:
            from collections import Counter
            counts = Counter(window)
            most_common_count = counts.most_common(1)[0][1]
            ratio = most_common_count / len(window)
            if ratio >= FRAUD_UNIFORM_RATIO:
                return {
                    "signal": "UNIFORM_PATTERN",
                    "alpha_override": 0.02,
                    "detail": f"{ratio:.0%} same response in last {FRAUD_UNIFORM_WINDOW}",
                }

    # Check adversarial (very low FRS)
    if current_frs < FRAUD_ADVERSARIAL_FRS:
        return {
            "signal": "ADVERSARIAL",
            "alpha_override": FRAUD_ADVERSARIAL_ALPHA,
            "detail": f"FRS={current_frs:.3f} below {FRAUD_ADVERSARIAL_FRS}",
        }

    return {"signal": "NONE", "alpha_override": None, "detail": ""}


# ---------------------------------------------------------------------------
# FRS Update (Asymmetric EMA)
# ---------------------------------------------------------------------------

def update_frs(
    current_frs: float,
    agreement_score: float,
    fraud_signal: Optional[Dict] = None,
) -> Tuple[float, Dict]:
    """
    Update parent Feedback Reliability Score using asymmetric EMA.

    Trust increases 3x faster than decreases:
      alpha = 0.12 if agreement_score >= 0  (trust grows fast)
      alpha = 0.04 if agreement_score < 0   (trust shrinks slowly)
      alpha = fraud.alpha_override if fraud detected

    target = 0.5 + 0.5 × agreement_score  (maps -1..1 → 0..1)
    new_frs = (1 - alpha) × current_frs + alpha × target
    clamped to [0.05, 0.95]

    Returns:
        (new_frs, metadata_dict)
    """
    try:
        from constants import (
            FRS_ALPHA_INCREASE, FRS_ALPHA_DECREASE,
            FRS_FLOOR, FRS_CEILING,
        )
    except ImportError:
        FRS_ALPHA_INCREASE = 0.12
        FRS_ALPHA_DECREASE = 0.04
        FRS_FLOOR = 0.05
        FRS_CEILING = 0.95

    fraud = fraud_signal or {"signal": "NONE", "alpha_override": None}
    alpha_override = fraud.get("alpha_override")

    if alpha_override is not None:
        alpha = float(alpha_override)
    elif agreement_score >= 0:
        alpha = FRS_ALPHA_INCREASE
    else:
        alpha = FRS_ALPHA_DECREASE

    target = 0.5 + 0.5 * max(-1.0, min(1.0, agreement_score))
    new_frs = (1.0 - alpha) * current_frs + alpha * target
    new_frs = round(max(FRS_FLOOR, min(FRS_CEILING, new_frs)), 4)

    return new_frs, {
        "previous_frs": round(current_frs, 4),
        "new_frs": new_frs,
        "alpha": round(alpha, 4),
        "target": round(target, 4),
        "agreement_score": round(agreement_score, 4),
        "fraud_signal": fraud.get("signal", "NONE"),
    }


# ---------------------------------------------------------------------------
# CRS Update (Context Reliability Score)
# ---------------------------------------------------------------------------

def update_crs(
    current_crs: float,
    context_matched: bool,
    fraud_signal: Optional[Dict] = None,
) -> Tuple[float, Dict]:
    """
    Update Context Reliability Score.

    alpha = 0.10 normal, 0.0 misclick, 0.40 adversarial
    target = 1.0 if context helped, 0.3 if misleading

    Returns:
        (new_crs, metadata_dict)
    """
    try:
        from constants import (
            CRS_ALPHA_NORMAL, CRS_ALPHA_ADVERSARIAL,
            CRS_FLOOR, CRS_CEILING,
        )
    except ImportError:
        CRS_ALPHA_NORMAL = 0.10
        CRS_ALPHA_ADVERSARIAL = 0.40
        CRS_FLOOR = 0.20
        CRS_CEILING = 1.00

    fraud = fraud_signal or {"signal": "NONE", "alpha_override": None}
    signal = fraud.get("signal", "NONE")

    if signal == "MISCLICK_SUSPECTED":
        alpha = 0.0
    elif signal == "ADVERSARIAL":
        alpha = CRS_ALPHA_ADVERSARIAL
    else:
        alpha = CRS_ALPHA_NORMAL

    target = 1.0 if context_matched else 0.3
    new_crs = (1.0 - alpha) * current_crs + alpha * target
    new_crs = round(max(CRS_FLOOR, min(CRS_CEILING, new_crs)), 4)

    return new_crs, {
        "previous_crs": round(current_crs, 4),
        "new_crs": new_crs,
        "alpha": round(alpha, 4),
        "target": target,
        "context_matched": context_matched,
    }


# ---------------------------------------------------------------------------
# Delta Score
# ---------------------------------------------------------------------------

def compute_delta_score(
    acoustic_scores: Dict[str, float],
    feedback_intent: str,
) -> float:
    """
    Compute Delta Score — distance between feedback and acoustic evidence.

    DS = 0.60 × RMS_distance + 0.40 × EPS (entropy profile similarity)
    RMS = sqrt(mean((feedback_onehot - acoustic)²))
    EPS = 1 - |entropy(acoustic) / max_entropy - 0.5| × 2

    Higher DS = feedback aligns well with acoustic → good training candidate.

    Returns:
        float in [0.0, 1.0]
    """
    if not acoustic_scores or not feedback_intent:
        return 0.0

    fb = feedback_intent.lower().strip()
    all_keys = list(acoustic_scores.keys())
    n = len(all_keys)
    if n == 0:
        return 0.0

    # One-hot for feedback
    fb_onehot = {k: (1.0 if k.lower().strip() == fb else 0.0) for k in all_keys}

    # RMS distance (inverted — higher when closer)
    rms_sum = sum(
        (fb_onehot.get(k, 0.0) - float(acoustic_scores.get(k, 0.0))) ** 2
        for k in all_keys
    )
    rms = math.sqrt(rms_sum / max(1, n))
    rms_similarity = max(0.0, 1.0 - rms)

    # Entropy profile similarity
    max_entropy = math.log(max(n, 2))
    entropy = 0.0
    for v in acoustic_scores.values():
        p = max(float(v), 1e-10)
        entropy -= p * math.log(p)
    if max_entropy > 0:
        norm_entropy = entropy / max_entropy
    else:
        norm_entropy = 0.5
    eps = 1.0 - abs(norm_entropy - 0.5) * 2.0

    ds = 0.60 * rms_similarity + 0.40 * eps
    return round(max(0.0, min(1.0, ds)), 4)
