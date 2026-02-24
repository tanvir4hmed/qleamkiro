"""
Qleam — Three-Source Evidence Model (Phase 4)

Determines probable infant intent by blending three independent evidence sources:

  Source 1 (60%) — Acoustic signal:
      Real-time audio features from this session.
      Uses 4 summary scores (emotional_intensity, rhythm, repetition, expressive_flow)
      augmented by Phase 3 rich features (cry_fraction, jitter_percent, hnr_db,
      syllable_rate, pause_ratio).  This source is immune to parent bias.

  Source 2 (15%) — Research priors:
      Developmental-stage-specific probability distributions grounded in peer-reviewed
      infant vocalization research.  Adjusted by session context (Phase 3) — feeding
      time and health state shift the prior before blending.

  Source 3 (25%) — Feedback history:
      Parent reinforcement over many sessions, maintained by reinforcement_engine.
      Capped at 25% so a small number of incorrect feedback events cannot mislead
      the model.

Design principles:
  - Acoustic signal is ground truth — it cannot be overridden.
  - Research priors solve the cold-start problem and add domain knowledge.
  - Feedback personalises over time without dominating early sessions.
  - Confidence accounts for history depth, reinforcement quality, semantic alignment,
    and cross-source agreement.
  - Confidence is hard-capped at 0.92 — Qleam never claims certainty.
"""
import logging
from typing import Dict, Optional

from normalization import normalize_probability_distribution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence weights  (must sum to 1.0)
# ---------------------------------------------------------------------------
ACOUSTIC_WEIGHT: float = 0.60
RESEARCH_WEIGHT: float = 0.15
FEEDBACK_WEIGHT: float = 0.25

# ---------------------------------------------------------------------------
# Source 1 — Acoustic Intent Classifier
# ---------------------------------------------------------------------------

def compute_acoustic_intent_scores(
    feature_scores: Dict[str, float],
    rich_features: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Classify infant intent from acoustic features.

    Primary signal (4 summary scores):
        emotional_intensity — pitch variance + energy variance (0=calm, 1=distressed)
        rhythm              — regularity of sound bursts  (1=rhythmic, 0=irregular)
        repetition          — MFCC self-similarity        (1=repeated, 0=varied)
        expressive_flow     — vocalization continuity     (1=continuous, 0=bursts)

    Augmented signal (Phase 3 rich features, used when available):
        cry_fraction    — fraction of voiced frames with F0 > 350 Hz
                          (high → hunger / discomfort cry pattern)
        jitter_percent  — cycle-to-cycle F0 perturbation %
                          (high → distressed / discomfort)
        hnr_db          — Harmonics-to-Noise Ratio in dB
                          (high → clean harmonic voice → social / connection)
        syllable_rate   — onset detections per second
                          (high → active babbling → exploration)
        pause_ratio     — fraction of silent energy frames
                          (low → sustained vocalization → exploration / hunger)

    Returns:
        Normalized probability distribution over intent labels.
    """
    rf = rich_features or {}

    ei  = feature_scores.get("emotional_intensity", 0.5)
    rh  = feature_scores.get("rhythm", 0.5)
    rep = feature_scores.get("repetition", 0.5)
    ef  = feature_scores.get("expressive_flow", 0.5)

    # --- Base scores (derived from infant vocalization research) ---
    hunger         = ei * 0.50 + rh * 0.40 + rep * 0.10
    discomfort     = ei * 0.60 + (1.0 - rh) * 0.25 + rep * 0.15
    connection     = (1.0 - ei) * 0.45 + ef * 0.45 + rh * 0.10
    moderate_ei    = max(0.0, 1.0 - abs(ei - 0.45) * 2.2)
    fatigue        = rep * 0.35 + (1.0 - ef) * 0.35 + moderate_ei * 0.30
    overstimulation = ei * 0.50 + (1.0 - rh) * 0.30 + ef * 0.20
    exploration    = (1.0 - ei) * 0.35 + (1.0 - rep) * 0.35 + ef * 0.30

    # --- Rich feature augmentations ---
    cry_fraction   = float(rf.get("cry_fraction",   0.0))
    jitter_pct     = float(rf.get("jitter_percent", 0.0))
    hnr_db         = float(rf.get("hnr_db",         0.0))
    syllable_rate  = float(rf.get("syllable_rate",  0.0))
    pause_ratio    = float(rf.get("pause_ratio",    0.5))

    # High cry fraction → hunger & discomfort boost
    if cry_fraction > 0.20:
        boost = min(cry_fraction, 0.60)
        hunger     += boost * 0.35
        discomfort += boost * 0.20

    # High jitter → distress signal → discomfort boost
    if jitter_pct > 5.0:
        jitter_boost = min((jitter_pct - 5.0) / 15.0, 0.25)
        discomfort   += jitter_boost

    # High HNR → clean harmonics → social / connection boost
    if hnr_db > 5.0:
        hnr_boost  = min(hnr_db / 50.0, 0.20)
        connection += hnr_boost

    # High syllable rate → active babbling → exploration boost
    if syllable_rate > 2.5:
        syllable_boost = min((syllable_rate - 2.5) / 7.0, 0.20)
        exploration    += syllable_boost

    # Low pause ratio → sustained vocalization → exploration / hunger, not fatigue
    if pause_ratio < 0.30:
        sustained_boost  = (0.30 - pause_ratio) * 0.40
        exploration      += sustained_boost * 0.50
        hunger           += sustained_boost * 0.30
        fatigue          -= sustained_boost * 0.30

    raw = {
        "hunger":          max(0.0, hunger),
        "discomfort":      max(0.0, discomfort),
        "connection":      max(0.0, connection),
        "fatigue":         max(0.0, fatigue),
        "overstimulation": max(0.0, overstimulation),
        "exploration":     max(0.0, exploration),
    }

    return normalize_probability_distribution(raw)


# ---------------------------------------------------------------------------
# Source 2 — Research Priors (developmental norms + session context)
# ---------------------------------------------------------------------------

# Stage-specific base priors.
# Interpretation of published infant vocalization literature:
#   - Newborns vocalize predominantly to signal distress (hunger, discomfort).
#   - Social/exploratory vocalizations emerge and dominate from 3–6 months onward.
#   - By 12–24 months, exploration and proto-linguistic intent dominate.
_STAGE_PRIORS: Dict[str, Dict[str, float]] = {
    "NEWBORN": {            # 0–90 days
        "hunger":          0.30,
        "discomfort":      0.30,
        "connection":      0.20,
        "fatigue":         0.12,
        "overstimulation": 0.05,
        "exploration":     0.03,
    },
    "EARLY_VOCAL": {        # 91–180 days
        "hunger":          0.22,
        "discomfort":      0.22,
        "connection":      0.28,
        "fatigue":         0.10,
        "overstimulation": 0.05,
        "exploration":     0.13,
    },
    "CANONICAL_BABBLE": {   # 181–270 days
        "hunger":          0.15,
        "discomfort":      0.15,
        "connection":      0.25,
        "fatigue":         0.10,
        "overstimulation": 0.05,
        "exploration":     0.30,
    },
    "PROTO_WORDS": {        # 271–365 days
        "hunger":          0.10,
        "discomfort":      0.10,
        "connection":      0.25,
        "fatigue":         0.08,
        "overstimulation": 0.05,
        "exploration":     0.42,
    },
    "FIRST_WORDS": {        # 366–548 days
        "hunger":          0.08,
        "discomfort":      0.08,
        "connection":      0.23,
        "fatigue":         0.08,
        "overstimulation": 0.05,
        "exploration":     0.48,
    },
    "WORD_COMBINATIONS": {  # 549–730 days
        "hunger":          0.07,
        "discomfort":      0.07,
        "connection":      0.22,
        "fatigue":         0.08,
        "overstimulation": 0.05,
        "exploration":     0.51,
    },
    "EARLY_SENTENCES": {    # 731+ days
        "hunger":          0.06,
        "discomfort":      0.06,
        "connection":      0.22,
        "fatigue":         0.07,
        "overstimulation": 0.04,
        "exploration":     0.55,
    },
    "UNKNOWN": {
        "hunger":          0.17,
        "discomfort":      0.17,
        "connection":      0.22,
        "fatigue":         0.10,
        "overstimulation": 0.05,
        "exploration":     0.29,
    },
}


def compute_research_priors(
    developmental_stage: str,
    session_context: Optional[Dict] = None,
    context_reliability: float = 0.8,
) -> Dict[str, float]:
    """
    Return context-adjusted developmental research priors.

    Base prior: stage-specific distribution from infant vocalization literature.

    Context adjustments (from Phase 3 session_context) are scaled by context_reliability
    so that unreliable or potentially incorrect parent-provided data doesn't fully override
    the research prior.  context_reliability starts at 0.8 and is updated via EMA in the
    feedback_processor as parent-provided context is validated against actual outcomes.

        feeding_minutes_ago >= 120  → hunger += 0.15 × cr  (not fed in > 2 hours)
        feeding_minutes_ago <= 30   → hunger -= 0.10 × cr  (recently fed)
        health_state == "sick"      → discomfort += 0.15 × cr, overstimulation += 0.05 × cr
        health_state == "teething"  → discomfort += 0.20 × cr

    All adjustments are applied before normalization so distribution always sums to 1.

    Args:
        developmental_stage: One of the stage names from DEVELOPMENTAL_STAGE_MAP.
        session_context:     Optional Phase 3 context dict from session record.
        context_reliability: How much to trust parent-provided context (0.2–1.0, default 0.8).

    Returns:
        Normalized probability distribution over intent labels.
    """
    stage = (developmental_stage or "UNKNOWN").upper().strip()
    priors = dict(_STAGE_PRIORS.get(stage, _STAGE_PRIORS["UNKNOWN"]))

    if session_context:
        cr = max(0.2, min(1.0, context_reliability))   # clamp to safe range

        # --- Feeding time adjustment ---
        feeding_ago = session_context.get("feeding_minutes_ago")
        if isinstance(feeding_ago, (int, float)) and feeding_ago >= 0:
            if feeding_ago >= 120:
                priors["hunger"] += 0.15 * cr    # Not fed in > 2 hours
            elif feeding_ago <= 30:
                priors["hunger"] = max(0.0, priors["hunger"] - 0.10 * cr)  # Recently fed

        # --- Health state adjustment ---
        health = str(session_context.get("health_state", "")).lower().strip()
        if health == "sick":
            priors["discomfort"]      += 0.15 * cr
            priors["overstimulation"] += 0.05 * cr
        elif health == "teething":
            priors["discomfort"] += 0.20 * cr

    # Ensure all non-negative after adjustments
    priors = {k: max(0.0, v) for k, v in priors.items()}
    return normalize_probability_distribution(priors)


# ---------------------------------------------------------------------------
# Three-Source Blend
# ---------------------------------------------------------------------------

def blend_evidence_sources(
    acoustic_scores: Dict[str, float],
    research_priors: Dict[str, float],
    feedback_intents: Dict[str, float],
    acoustic_w: float = ACOUSTIC_WEIGHT,
    research_w: float = RESEARCH_WEIGHT,
    feedback_w: float = FEEDBACK_WEIGHT,
) -> Dict[str, float]:
    """
    Blend three evidence sources with the given weights.

    Default weights (overridden by dynamic FRS weighting in determine_probable_intent_v2):
        Acoustic  60% — real-time audio (primary truth source, immune to bias)
        Research  15% — developmental science (cold-start + domain knowledge)
        Feedback  25% — parent reinforcement history (long-term personalisation)

    Returns:
        Normalized blended probability distribution over all intent keys.
    """
    all_keys = (
        set(acoustic_scores.keys())
        | set(research_priors.keys())
        | set(feedback_intents.keys())
    )

    blended: Dict[str, float] = {}
    for key in all_keys:
        a = acoustic_scores.get(key, 0.0)
        r = research_priors.get(key, 0.0)
        f = feedback_intents.get(key, 0.0)
        blended[key] = acoustic_w * a + research_w * r + feedback_w * f

    return normalize_probability_distribution(blended)


# ---------------------------------------------------------------------------
# Confidence Calculation
# ---------------------------------------------------------------------------

def compute_intent_confidence(
    blended: Dict[str, float],
    cluster: Dict,
    acoustic_scores: Dict[str, float],
    research_priors: Dict[str, float],
    session_count: int = 0,
) -> float:
    """
    Compute confidence for the top blended intent.

    Factors:
      1. Blend strength          — top probability in the blended distribution
      2. Session history         — cluster frequency_count (saturates at 10 sessions)
      3. Reinforcement quality   — cluster.reinforcement_weight (parent confirmation)
      4. Semantic alignment      — cluster.semantic_alignment_score (word detected)
      5. Cross-source agreement  — acoustic AND research agree on top intent → +0.05

    Caps (applied after calculation):
      - Default ceiling: 0.92 — Qleam never claims certainty
      - Sessions 1–5: max 0.40 (still learning this baby's unique patterns)
      - Weak signal (top acoustic score < 0.30): max 0.35
      - Floor: 0.10

    Returns:
        float in [0.10, 0.92]
    """
    if not blended:
        return 0.05

    best_key    = max(blended, key=blended.get)
    best_weight = blended[best_key]

    frequency_count      = cluster.get("frequency_count", 1)
    reinforcement_weight = cluster.get("reinforcement_weight", 0.5)
    semantic_alignment   = cluster.get("semantic_alignment_score", 0.0)

    frequency_factor = min(frequency_count / 10.0, 1.0)
    semantic_factor  = 1.0 + (float(semantic_alignment) * 0.20)

    # Cross-source agreement bonus
    acoustic_best = max(acoustic_scores, key=acoustic_scores.get) if acoustic_scores else best_key
    research_best = max(research_priors, key=research_priors.get) if research_priors else best_key
    agreement_bonus = 0.05 if (acoustic_best == best_key and research_best == best_key) else 0.0

    confidence = (
        best_weight
        * (0.50 + float(reinforcement_weight) * 0.25 * frequency_factor)
        * semantic_factor
        + agreement_bonus
    )

    # Apply session-based and signal-strength caps
    ceiling = 0.92
    if session_count <= 5:
        ceiling = 0.40
    top_acoustic = max(acoustic_scores.values()) if acoustic_scores else 0.5
    if top_acoustic < 0.30:
        ceiling = min(ceiling, 0.35)
    return round(min(max(confidence, 0.10), ceiling), 3)


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def determine_probable_intent_v2(
    cluster: Dict,
    feature_scores: Dict[str, float],
    rich_features: Optional[Dict[str, float]] = None,
    developmental_stage: str = "UNKNOWN",
    session_context: Optional[Dict] = None,
    session_count: int = 0,
    parent_trust_score: float = 0.5,
    context_reliability: float = 0.8,
) -> Dict:
    """
    Three-Source Evidence Model intent determination (Phase 4).

    Supersedes the Phase 2 two-source model (70% acoustic + 30% feedback).
    Default split: 60% acoustic + 15% research priors + 25% feedback history.
    Feedback weight is dynamically scaled by parent_trust_score (FRS):
        effective_feedback_w = 0.25 × max(0.1, FRS)
        remaining weight redistributed proportionally to acoustic + research.

    Args:
        cluster:              SoundCluster DynamoDB item (probable_intents, reinforcement_weight)
        feature_scores:       4-score dict from feature_extraction (backward compat)
        rich_features:        65-feature dict from Phase 3 (optional, improves accuracy)
        developmental_stage:  Baby's current developmental stage (e.g. "CANONICAL_BABBLE")
        session_context:      Phase 3 context dict (feeding_minutes_ago, health_state, etc.)
        session_count:        Total sessions recorded for this child (drives confidence caps)
        parent_trust_score:   Parent Feedback Reliability Score — FRS in [0, 1] (default 0.5)
        context_reliability:  How much to trust parent-provided context data (0.2–1.0, default 0.8)

    Returns:
        {
            "label":       str,   # Human-readable intent label
            "key":         str,   # Intent key (e.g. "hunger")
            "confidence":  float, # 0.10–0.92 (capped by session count + signal strength)
            "top_intents": [...], # Top 3 [{key, label, weight}]
            "evidence": {         # Source breakdown (transparency layer)
                "acoustic":  {intent: weight, ...},
                "research":  {intent: weight, ...},
                "feedback":  {intent: weight, ...},
                "blended":   {intent: weight, ...},
                "weights":   {"acoustic": float, "research": float, "feedback": float},
                "agreement": bool,   # acoustic + research agree on top intent
            }
        }
    """
    # Inline import avoids circular-import risk when shared/ is loaded from multiple paths
    try:
        from constants import INTENT_LABELS as LABELS
    except ImportError:
        LABELS = {}

    # --- Source 1: Acoustic ---
    acoustic_scores = compute_acoustic_intent_scores(feature_scores, rich_features)

    # --- Source 2: Research priors + context (scaled by context_reliability) ---
    research_priors = compute_research_priors(developmental_stage, session_context, context_reliability)

    # --- Source 3: Feedback history (maintained by reinforcement_engine) ---
    feedback_intents: Dict[str, float] = cluster.get("probable_intents") or {}

    # --- Phase 4: Dynamic feedback weight scaled by parent trust score (FRS) ---
    feedback_w = 0.25 * max(0.1, min(1.0, parent_trust_score))
    remaining = 1.0 - feedback_w
    acoustic_w = remaining * (0.60 / 0.75)  # acoustic's original share of non-feedback
    research_w = remaining * (0.15 / 0.75)  # research's original share of non-feedback

    # --- Blend ---
    blended = blend_evidence_sources(acoustic_scores, research_priors, feedback_intents, acoustic_w, research_w, feedback_w)

    # --- Winner ---
    best_key = max(blended, key=blended.get)
    label    = LABELS.get(best_key, best_key.replace("_", " ").title())

    # --- Confidence ---
    confidence = compute_intent_confidence(blended, cluster, acoustic_scores, research_priors, session_count=session_count)

    # --- Cross-source agreement flag ---
    acoustic_best = max(acoustic_scores, key=acoustic_scores.get) if acoustic_scores else best_key
    research_best = max(research_priors, key=research_priors.get) if research_priors else best_key
    agreement = acoustic_best == best_key and research_best == best_key

    # --- Top-3 intents ---
    top_intents = sorted(blended.items(), key=lambda x: -x[1])[:3]

    logger.info(
        f"Evidence model: intent={best_key} confidence={confidence:.3f} "
        f"stage={developmental_stage} agreement={agreement} "
        f"session_count={session_count} frs={parent_trust_score:.3f}"
    )

    return {
        "label":      label,
        "key":        best_key,
        "confidence": confidence,
        "top_intents": [
            {
                "key":    k,
                "label":  LABELS.get(k, k.replace("_", " ").title()),
                "weight": round(v, 3),
            }
            for k, v in top_intents
        ],
        "evidence": {
            "acoustic":  {k: round(v, 3) for k, v in acoustic_scores.items()},
            "research":  {k: round(v, 3) for k, v in research_priors.items()},
            "feedback":  {k: round(v, 3) for k, v in feedback_intents.items()},
            "blended":   {k: round(v, 3) for k, v in blended.items()},
            "weights":   {
                "acoustic": round(acoustic_w, 4),
                "research": round(research_w, 4),
                "feedback": round(feedback_w, 4),
            },
            "agreement": agreement,
        },
    }
