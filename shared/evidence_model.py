"""
Qleam â€” Three-Source Evidence Model (Phase 4)

Determines probable infant intent by blending three independent evidence sources:

  Source 1 (60%) â€” Acoustic signal:
      Real-time audio features from this session.
      Uses 4 summary scores (emotional_intensity, rhythm, repetition, expressive_flow)
      augmented by Phase 3 rich features (cry_fraction, jitter_percent, hnr_db,
      syllable_rate, pause_ratio).  This source is immune to parent bias.

  Source 2 (15%) â€” Research priors:
      Developmental-stage-specific probability distributions grounded in peer-reviewed
      infant vocalization research.  Adjusted by session context (Phase 3) â€” feeding
      time and health state shift the prior before blending.

  Source 3 (25%) â€” Feedback history:
      Parent reinforcement over many sessions, maintained by reinforcement_engine.
      Capped at 25% so a small number of incorrect feedback events cannot mislead
      the model.

Design principles:
  - Acoustic signal is ground truth â€” it cannot be overridden.
  - Research priors solve the cold-start problem and add domain knowledge.
  - Feedback personalises over time without dominating early sessions.
  - Confidence accounts for history depth, reinforcement quality, semantic alignment,
    and cross-source agreement.
  - Confidence is hard-capped at 0.92 â€” Qleam never claims certainty.
"""
import logging
import math
from typing import Dict, Optional

from normalization import normalize_probability_distribution
from intent_taxonomy import normalize_intent_distribution

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence weights  (must sum to 1.0)
# ---------------------------------------------------------------------------
ACOUSTIC_WEIGHT: float = 0.60
RESEARCH_WEIGHT: float = 0.15
FEEDBACK_WEIGHT: float = 0.25

_STAGE_BASE_WEIGHTS: Dict[str, Dict[str, float]] = {
    "NEWBORN": {"acoustic": 0.45, "research": 0.40, "feedback": 0.15},
    "EARLY_VOCAL": {"acoustic": 0.50, "research": 0.30, "feedback": 0.20},
    "CANONICAL_BABBLE": {"acoustic": 0.55, "research": 0.25, "feedback": 0.20},
    "PROTO_WORDS": {"acoustic": 0.58, "research": 0.20, "feedback": 0.22},
    "FIRST_WORDS": {"acoustic": 0.62, "research": 0.15, "feedback": 0.23},
    "WORD_COMBINATIONS": {"acoustic": 0.65, "research": 0.12, "feedback": 0.23},
    "EARLY_SENTENCES": {"acoustic": 0.70, "research": 0.10, "feedback": 0.20},
    "UNKNOWN": {"acoustic": 0.60, "research": 0.20, "feedback": 0.20},
}

_INFANT_STAGE_SET = {"NEWBORN", "EARLY_VOCAL", "CANONICAL_BABBLE", "PROTO_WORDS"}


def _base_weights_for_stage(developmental_stage: str) -> Dict[str, float]:
    stage = (developmental_stage or "UNKNOWN").upper().strip()
    return _STAGE_BASE_WEIGHTS.get(stage, _STAGE_BASE_WEIGHTS["UNKNOWN"])

# ---------------------------------------------------------------------------
# Source 1 â€” Acoustic Intent Classifier
# ---------------------------------------------------------------------------

def compute_acoustic_intent_scores(
    feature_scores: Dict[str, float],
    rich_features: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Classify infant intent from acoustic features.

    Primary signal (4 summary scores):
        emotional_intensity - pitch variance + energy variance (0=calm, 1=distressed)
        rhythm              - regularity of sound bursts  (1=rhythmic, 0=irregular)
        repetition          - MFCC self-similarity        (1=repeated, 0=varied)
        expressive_flow     - vocalization continuity     (1=continuous, 0=bursts)

    Augmented signal (Phase 3 rich features, used when available):
        cry_fraction, jitter_percent, hnr_db, syllable_rate, pause_ratio

    Returns:
        Normalized probability distribution over v2 intent labels.
    """
    rf = rich_features or {}

    ei = float(feature_scores.get("emotional_intensity", 0.5))
    rh = float(feature_scores.get("rhythm", 0.5))
    rep = float(feature_scores.get("repetition", 0.5))
    ef = float(feature_scores.get("expressive_flow", 0.5))

    cry_fraction = float(rf.get("cry_fraction", 0.0))
    jitter_pct = float(rf.get("jitter_percent", 0.0))
    hnr_db = float(rf.get("hnr_db", 0.0))
    syllable_rate = float(rf.get("syllable_rate", 0.0))
    pause_ratio = float(rf.get("pause_ratio", 0.5))

    distress = max(0.0, min(1.0, ei * 0.65 + min(cry_fraction, 0.8) * 0.35))
    calm = max(0.0, min(1.0, 1.0 - ei))
    irregular = max(0.0, min(1.0, 1.0 - rh))
    bursty = max(0.0, min(1.0, 1.0 - ef))
    social_harmonic = max(0.0, min(1.0, hnr_db / 20.0))
    high_jitter = max(0.0, min(1.0, (jitter_pct - 3.0) / 17.0))
    high_pause = max(0.0, min(1.0, (pause_ratio - 0.45) / 0.55))
    syllable_activity = max(0.0, min(1.0, syllable_rate / 6.0))

    hunger = distress * 0.36 + rh * 0.24 + rep * 0.14 + min(cry_fraction, 0.8) * 0.26
    fatigue = calm * 0.20 + rep * 0.26 + bursty * 0.30 + high_pause * 0.24
    pain = distress * 0.40 + high_jitter * 0.35 + irregular * 0.15 + min(cry_fraction, 0.8) * 0.10
    discomfort = distress * 0.34 + irregular * 0.24 + high_jitter * 0.20 + rep * 0.12 + min(cry_fraction, 0.6) * 0.10
    closeness = calm * 0.30 + ef * 0.30 + social_harmonic * 0.25 + (1.0 - high_pause) * 0.15
    frustration = ei * 0.34 + irregular * 0.22 + rep * 0.20 + bursty * 0.14 + high_jitter * 0.10
    happy = calm * 0.28 + ef * 0.24 + social_harmonic * 0.32 + syllable_activity * 0.16
    exploration = calm * 0.24 + (1.0 - rep) * 0.26 + ef * 0.20 + syllable_activity * 0.18 + social_harmonic * 0.12

    distress_competitors = max(hunger, pain, discomfort, frustration)
    distress_unknown = (
        distress * 0.55
        + irregular * 0.15
        + high_jitter * 0.10
        + (0.35 if distress_competitors < 0.55 else 0.05)
        + (0.10 if abs(discomfort - frustration) < 0.05 else 0.0)
    )

    raw = {
        "hunger": max(0.0, hunger),
        "fatigue": max(0.0, fatigue),
        "pain": max(0.0, pain),
        "discomfort": max(0.0, discomfort),
        "closeness": max(0.0, closeness),
        "frustration": max(0.0, frustration),
        "happy": max(0.0, happy),
        "exploration": max(0.0, exploration),
        "distress_unknown": max(0.0, distress_unknown),
    }

    return normalize_intent_distribution(raw, include_technical=False, fill_missing=True)

# ---------------------------------------------------------------------------
# Source 2 â€” Research Priors (developmental norms + session context)
# ---------------------------------------------------------------------------

# Stage-specific base priors.
# Interpretation of published infant vocalization literature:
#   - Newborns vocalize predominantly to signal distress (hunger, discomfort).
#   - Social/exploratory vocalizations emerge and dominate from 3â€“6 months onward.
#   - By 12â€“24 months, exploration and proto-linguistic intent dominate.
_STAGE_PRIORS: Dict[str, Dict[str, float]] = {
    "NEWBORN": {            # 0â€“90 days
        "hunger": 0.24,
        "fatigue": 0.10,
        "pain": 0.15,
        "discomfort": 0.20,
        "closeness": 0.11,
        "frustration": 0.07,
        "happy": 0.03,
        "exploration": 0.03,
        "distress_unknown": 0.07,
    },
    "EARLY_VOCAL": {        # 91â€“180 days
        "hunger": 0.20,
        "fatigue": 0.11,
        "pain": 0.12,
        "discomfort": 0.18,
        "closeness": 0.14,
        "frustration": 0.08,
        "happy": 0.05,
        "exploration": 0.07,
        "distress_unknown": 0.05,
    },
    "CANONICAL_BABBLE": {   # 181â€“270 days
        "hunger": 0.14,
        "fatigue": 0.10,
        "pain": 0.08,
        "discomfort": 0.14,
        "closeness": 0.14,
        "frustration": 0.11,
        "happy": 0.09,
        "exploration": 0.15,
        "distress_unknown": 0.05,
    },
    "PROTO_WORDS": {        # 271â€“365 days
        "hunger": 0.10,
        "fatigue": 0.08,
        "pain": 0.06,
        "discomfort": 0.10,
        "closeness": 0.14,
        "frustration": 0.12,
        "happy": 0.12,
        "exploration": 0.23,
        "distress_unknown": 0.05,
    },
    "FIRST_WORDS": {        # 366â€“548 days
        "hunger": 0.08,
        "fatigue": 0.08,
        "pain": 0.05,
        "discomfort": 0.08,
        "closeness": 0.13,
        "frustration": 0.11,
        "happy": 0.14,
        "exploration": 0.28,
        "distress_unknown": 0.05,
    },
    "WORD_COMBINATIONS": {  # 549â€“730 days
        "hunger": 0.07,
        "fatigue": 0.07,
        "pain": 0.04,
        "discomfort": 0.07,
        "closeness": 0.12,
        "frustration": 0.10,
        "happy": 0.16,
        "exploration": 0.32,
        "distress_unknown": 0.05,
    },
    "EARLY_SENTENCES": {    # 731+ days
        "hunger": 0.06,
        "fatigue": 0.06,
        "pain": 0.03,
        "discomfort": 0.06,
        "closeness": 0.10,
        "frustration": 0.09,
        "happy": 0.18,
        "exploration": 0.37,
        "distress_unknown": 0.05,
    },
    "UNKNOWN": {
        "hunger": 0.13,
        "fatigue": 0.09,
        "pain": 0.08,
        "discomfort": 0.13,
        "closeness": 0.13,
        "frustration": 0.10,
        "happy": 0.10,
        "exploration": 0.16,
        "distress_unknown": 0.08,
    },
}


def compute_research_priors(
    developmental_stage: str,
    session_context: Optional[Dict] = None,
    context_reliability: float = 0.8,
    population_prior: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Return context-adjusted developmental research priors.

    Base prior: stage-specific distribution from infant vocalization literature,
    OR the Phase 8 federated learning population prior if one is provided and
    has been validated as reliable (n_participants >= FL_MIN_PARTICIPANTS).

    Phase 8 override: if `population_prior` is supplied, it replaces the static
    _STAGE_PRIORS as the base distribution.  The research floor (10% uniform
    prior) is already baked into population_prior by the federated_aggregator,
    so no further floor blending is needed here.

    Context adjustments (from Phase 3 session_context) are scaled by context_reliability
    so that unreliable or potentially incorrect parent-provided data doesn't fully override
    the research prior.  context_reliability starts at 0.8 and is updated via EMA in the
    feedback_processor as parent-provided context is validated against actual outcomes.

        feeding_minutes_ago >= 120  â†’ hunger += 0.15 Ã— cr  (not fed in > 2 hours)
        feeding_minutes_ago <= 30   â†’ hunger -= 0.10 Ã— cr  (recently fed)
        health_state == "sick"      â†’ discomfort/pain/distress_unknown are boosted
        health_state == "teething"  â†’ pain/discomfort are boosted

    All adjustments are applied before normalization so distribution always sums to 1.

    Args:
        developmental_stage: One of the stage names from DEVELOPMENTAL_STAGE_MAP.
        session_context:     Optional Phase 3 context dict from session record.
        context_reliability: How much to trust parent-provided context (0.2â€“1.0, default 0.8).
        population_prior:    Phase 8 FL population model prior (already DP-protected +
                             research-floor-blended by federated_aggregator). When provided
                             and reliable, replaces static literature priors.

    Returns:
        Normalized probability distribution over intent labels.
    """
    stage = (developmental_stage or "UNKNOWN").upper().strip()

    # Phase 8: use FL population prior if supplied, otherwise fall back to literature
    if population_prior and len(population_prior) >= 3:
        priors = normalize_intent_distribution(population_prior, include_technical=False, fill_missing=True)
        logger.debug(f"Using FL population prior for stage={stage}")
    else:
        priors = normalize_intent_distribution(_STAGE_PRIORS.get(stage, _STAGE_PRIORS["UNKNOWN"]), include_technical=False, fill_missing=True)

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
            priors["discomfort"] += 0.12 * cr
            priors["pain"] += 0.08 * cr
            priors["distress_unknown"] += 0.03 * cr
        elif health == "teething":
            priors["pain"] += 0.12 * cr
            priors["discomfort"] += 0.10 * cr

    # Ensure all non-negative after adjustments
    priors = {k: max(0.0, v) for k, v in priors.items()}
    return normalize_intent_distribution(priors, include_technical=False, fill_missing=True)


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
        Acoustic  60% â€” real-time audio (primary truth source, immune to bias)
        Research  15% â€” developmental science (cold-start + domain knowledge)
        Feedback  25% â€” parent reinforcement history (long-term personalisation)

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
      1. Blend strength          â€” top probability in the blended distribution
      2. Session history         â€” cluster frequency_count (saturates at 10 sessions)
      3. Reinforcement quality   â€” cluster.reinforcement_weight (parent confirmation)
      4. Semantic alignment      â€” cluster.semantic_alignment_score (word detected)
      5. Cross-source agreement  â€” acoustic AND research agree on top intent â†’ +0.05

    Caps (applied after calculation):
      - Default ceiling: 0.92 â€” Qleam never claims certainty
      - Sessions 1â€“5: max 0.40 (still learning this baby's unique patterns)
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
    external_acoustic_scores: Optional[Dict[str, float]] = None,
    external_acoustic_meta: Optional[Dict] = None,
    developmental_stage: str = "UNKNOWN",
    session_context: Optional[Dict] = None,
    session_count: int = 0,
    parent_trust_score: float = 0.5,
    context_reliability: float = 0.8,
    acoustic_reliability: float = 1.0,
    population_prior: Optional[Dict[str, float]] = None,
    training_dataset_prior: Optional[Dict[str, float]] = None,
    training_dataset_n: int = 0,
    training_dataset_reliable: bool = False,
) -> Dict:
    """
    Three-Source Evidence Model intent determination (Phase 4).

    Supersedes the Phase 2 two-source model (70% acoustic + 30% feedback).
    Default split: 60% acoustic + 15% research priors + 25% feedback history.
    Feedback weight is dynamically scaled by parent_trust_score (FRS):
        effective_feedback_w = 0.25 Ã— max(0.1, FRS)
        remaining weight redistributed proportionally to acoustic + research.

    Args:
        cluster:              SoundCluster DynamoDB item (probable_intents, reinforcement_weight)
        feature_scores:       4-score dict from feature_extraction (backward compat)
        rich_features:        65-feature dict from Phase 3 (optional, improves accuracy)
        external_acoustic_scores:
                              Optional managed endpoint acoustic distribution.
                              Safely blended when reliability metadata is sufficient.
        developmental_stage:  Baby's current developmental stage (e.g. "CANONICAL_BABBLE")
        session_context:      Phase 3 context dict (feeding_minutes_ago, health_state, etc.)
        session_count:        Total sessions recorded for this child (drives confidence caps)
        parent_trust_score:   Parent Feedback Reliability Score â€” FRS in [0, 1] (default 0.5)
        context_reliability:  How much to trust parent-provided context data (0.2â€“1.0, default 0.8)
        acoustic_reliability: Signal-quality confidence in [0, 1] from quality+diarization checks.
        training_dataset_prior:
                              Optional stage-level prior from accepted training dataset.
                              Blended into research priors with a strict capped alpha.

    Returns:
        {
            "label":       str,   # Human-readable intent label
            "key":         str,   # Intent key (e.g. "hunger")
            "confidence":  float, # 0.10â€“0.92 (capped by session count + signal strength)
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
    # Base acoustic signal is always computed from local extraction.
    base_acoustic_scores = compute_acoustic_intent_scores(feature_scores, rich_features)
    acoustic_scores = dict(base_acoustic_scores)
    managed_acoustic_alpha = 0.0
    managed_acoustic_available = bool(external_acoustic_scores)

    # Optional managed endpoint signal is blended (not hard-overridden) when reliable.
    if external_acoustic_scores:
        managed_scores = normalize_intent_distribution(
            external_acoustic_scores, include_technical=False, fill_missing=True
        )

        managed_reliability = 0.0
        managed_training_samples = 0
        if isinstance(external_acoustic_meta, dict):
            try:
                managed_reliability = max(0.0, min(1.0, float(external_acoustic_meta.get("reliability", 0.0) or 0.0)))
            except Exception:
                managed_reliability = 0.0
            try:
                managed_training_samples = int(external_acoustic_meta.get("training_samples", 0) or 0)
            except Exception:
                managed_training_samples = 0

        try:
            from constants import (
                TRAINING_DATASET_MIN_SAMPLES,
                TRAINING_DATASET_BLEND_MAX_ALPHA,
            )
            managed_min_samples = int(TRAINING_DATASET_MIN_SAMPLES)
            managed_max_alpha = float(TRAINING_DATASET_BLEND_MAX_ALPHA)
        except Exception:
            managed_min_samples = 120
            managed_max_alpha = 0.18

        if managed_training_samples >= managed_min_samples and managed_reliability >= 0.70:
            rel_scale = (managed_reliability - 0.70) / 0.30
            rel_scale = max(0.0, min(1.0, rel_scale))
            managed_acoustic_alpha = round(max(0.0, min(managed_max_alpha, managed_max_alpha * rel_scale)), 4)

            acoustic_scores = normalize_probability_distribution(
                {
                    k: (1.0 - managed_acoustic_alpha) * base_acoustic_scores.get(k, 0.0)
                    + managed_acoustic_alpha * managed_scores.get(k, 0.0)
                    for k in set(base_acoustic_scores.keys()) | set(managed_scores.keys())
                }
            )

    # --- Source 2: Research priors + context (Phase 8: FL population prior if available) ---
    research_priors = compute_research_priors(
        developmental_stage, session_context, context_reliability, population_prior
    )

    dataset_alpha = 0.0
    if training_dataset_prior and training_dataset_reliable:
        dataset_priors = normalize_intent_distribution(
            training_dataset_prior, include_technical=False, fill_missing=True
        )

        try:
            from constants import (
                TRAINING_DATASET_BLEND_MAX_ALPHA,
                TRAINING_DATASET_MIN_SAMPLES,
                TRAINING_DATASET_BLEND_SATURATION_SAMPLES,
            )
            ds_max_alpha = max(0.0, float(TRAINING_DATASET_BLEND_MAX_ALPHA))
            ds_min = max(1, int(TRAINING_DATASET_MIN_SAMPLES))
            ds_sat = max(ds_min + 1, int(TRAINING_DATASET_BLEND_SATURATION_SAMPLES))
        except Exception:
            ds_max_alpha = 0.18
            ds_min = 120
            ds_sat = 2000

        n = max(0, int(training_dataset_n or 0))
        if n >= ds_min and ds_max_alpha > 0:
            # Smooth growth: 0 at min samples, approaches max alpha near saturation.
            span = max(1, ds_sat - ds_min)
            progress = max(0.0, min(1.0, math.log1p(n - ds_min + 1) / math.log1p(span)))
            dataset_alpha = round(ds_max_alpha * progress, 4)
            research_priors = normalize_probability_distribution(
                {
                    k: (1.0 - dataset_alpha) * research_priors.get(k, 0.0)
                    + dataset_alpha * dataset_priors.get(k, 0.0)
                    for k in set(research_priors.keys()) | set(dataset_priors.keys())
                }
            )

    # --- Source 3: Feedback history (maintained by reinforcement_engine) ---
    feedback_intents: Dict[str, float] = normalize_intent_distribution(cluster.get("probable_intents") or {}, include_technical=False, fill_missing=True)

    # --- Phase 4+: Stage-aware base weights + dynamic feedback scaling by FRS ---
    stage = (developmental_stage or "UNKNOWN").upper().strip()
    base = _base_weights_for_stage(developmental_stage)
    base_feedback_w = base["feedback"]
    feedback_w = base_feedback_w * max(0.1, min(1.0, parent_trust_score))
    non_feedback_base = max(base["acoustic"] + base["research"], 1e-6)
    remaining = max(0.0, 1.0 - feedback_w)
    acoustic_w = remaining * (base["acoustic"] / non_feedback_base)
    research_w = remaining * (base["research"] / non_feedback_base)

    # Confidence-gated rebalancing for infant stages:
    # If audio reliability is weak/noisy, shift some mass from acoustic -> research.
    rel = max(0.4, min(1.0, float(acoustic_reliability)))
    if stage in _INFANT_STAGE_SET:
        shift_by_reliability = acoustic_w * (1.0 - rel) * 0.55
        acoustic_w = max(0.0, acoustic_w - shift_by_reliability)
        research_w += shift_by_reliability

        top_acoustic = max(acoustic_scores.values()) if acoustic_scores else 0.0
        if top_acoustic < 0.36:
            extra_shift = min(acoustic_w * 0.22, (0.36 - top_acoustic) * 0.35)
            acoustic_w = max(0.0, acoustic_w - extra_shift)
            research_w += extra_shift

        # Age priors help cold-start, but when acoustic evidence is strong and
        # clean we reduce age influence to avoid stage-induced label flips.
        sorted_acoustic = sorted(acoustic_scores.values(), reverse=True)
        acoustic_margin = (
            (sorted_acoustic[0] - sorted_acoustic[1])
            if len(sorted_acoustic) > 1
            else (sorted_acoustic[0] if sorted_acoustic else 0.0)
        )
        strength = max(0.0, min(1.0, (top_acoustic - 0.34) / 0.22))
        separation = max(0.0, min(1.0, (acoustic_margin - 0.05) / 0.15))
        confidence_shift = strength * separation * rel
        if confidence_shift > 0:
            shift = min(research_w * 0.40, research_w * 0.40 * confidence_shift)
            research_w = max(0.0, research_w - shift)
            acoustic_w += shift

    # --- Blend ---
    blended = blend_evidence_sources(acoustic_scores, research_priors, feedback_intents, acoustic_w, research_w, feedback_w)

    # Infant-stage stability guard:
    # when blended top intents are nearly tied but acoustics are clearly decisive,
    # add a tiny acoustic-consistent boost to avoid age-prior driven label flips.
    acoustic_tiebreak_applied = False
    acoustic_tiebreak_key = ""
    if stage in _INFANT_STAGE_SET and acoustic_scores:
        blended_ranked = sorted(blended.items(), key=lambda x: -x[1])
        acoustic_ranked = sorted(acoustic_scores.items(), key=lambda x: -x[1])
        if len(blended_ranked) >= 2 and len(acoustic_ranked) >= 2:
            blended_best = blended_ranked[0][0]
            blended_margin = blended_ranked[0][1] - blended_ranked[1][1]
            acoustic_best_key = acoustic_ranked[0][0]
            acoustic_best_score = acoustic_ranked[0][1]
            acoustic_margin = acoustic_ranked[0][1] - acoustic_ranked[1][1]
            if (
                acoustic_best_key != blended_best
                and blended_margin <= 0.04
                and acoustic_best_score >= 0.35
                and acoustic_margin >= 0.07
                and rel >= 0.72
            ):
                boost = min(0.02, blended_margin + 0.006)
                blended[acoustic_best_key] = blended.get(acoustic_best_key, 0.0) + boost
                blended = normalize_probability_distribution(blended)
                acoustic_tiebreak_applied = True
                acoustic_tiebreak_key = acoustic_best_key

    # --- Winner ---
    best_key = max(blended, key=blended.get)
    label    = LABELS.get(best_key, best_key.replace("_", " ").title())

    # --- Confidence ---
    confidence = compute_intent_confidence(blended, cluster, acoustic_scores, research_priors, session_count=session_count)

    # Confidence calibration for infant sessions:
    #  - reduce overconfidence when top intents are close
    #  - account for measured acoustic reliability
    top_vals = sorted(blended.values(), reverse=True)
    margin = (top_vals[0] - top_vals[1]) if len(top_vals) > 1 else top_vals[0]
    if stage in _INFANT_STAGE_SET and margin < 0.08:
        confidence *= 0.86
    confidence *= (0.78 + 0.22 * rel)
    confidence = round(min(max(confidence, 0.10), 0.92), 3)

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
            "acoustic_reliability": round(rel, 3),
            "top_margin": round(max(margin, 0.0), 4),
            "agreement": agreement,
            "dataset_alpha": round(dataset_alpha, 4),
            "training_dataset_n": int(training_dataset_n or 0),
            "training_dataset_reliable": bool(training_dataset_reliable),
            "managed_acoustic_available": managed_acoustic_available,
            "managed_acoustic_alpha": round(managed_acoustic_alpha, 4),
            "acoustic_tiebreak_applied": acoustic_tiebreak_applied,
            "acoustic_tiebreak_key": acoustic_tiebreak_key,
        },
    }
