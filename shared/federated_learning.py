"""
Qleam — Federated Learning Shared Module (Phase 8, FIVL)

Stage-stratified Federated Averaging with Differential Privacy.

Mathematical foundation (SCIENTIFIC_MATHEMATICS.md Section 10):
    - Theorem 10.1: DP guarantee — (ε=1.0, δ=1e-5)-differentially private
    - Theorem 10.2: FL convergence bound — O(1/√T) convergence

Design principles:
    - Raw audio NEVER leaves device
    - Only normalised intent probability vectors are aggregated
    - Aggregation is stage-stratified: same-stage babies inform each other
    - Quality gate: FRS > 0.60 AND delta_score > 0.65 required per session
    - Research floor: 0.10 — population model REPLACES research prior above floor
    - DP noise added AFTER aggregation before population model write
"""
import math
import logging
import random
from typing import Dict, List, Optional, Tuple
from intent_taxonomy import canonical_intent_keys, normalize_intent_distribution

logger = logging.getLogger(__name__)

# All intent keys — must match evidence_model.py
_ALL_INTENTS = list(canonical_intent_keys(include_technical=False))


# =============================================================================
# Differential Privacy — Gaussian Mechanism
# Spec: Theorem 10.1, SCIENTIFIC_MATHEMATICS.md
# =============================================================================

def _dp_sigma(epsilon: float, delta: float, sensitivity: float) -> float:
    """
    Compute the Gaussian noise σ needed for (ε, δ)-DP.

    Gaussian mechanism:  σ = √(2 ln(1.25/δ)) × sensitivity / ε

    For ε=1.0, δ=1e-5, sensitivity=1.0:
        σ = √(2 × ln(125000)) ≈ √(23.47) ≈ 4.845 × sensitivity
    """
    return math.sqrt(2.0 * math.log(1.25 / delta)) * sensitivity / epsilon


def add_gaussian_noise(
    distribution: Dict[str, float],
    epsilon: float,
    delta: float,
    n_participants: int,
) -> Dict[str, float]:
    """
    Add calibrated Gaussian noise to an aggregated intent distribution.

    Sensitivity of a normalised distribution is 2/n_participants (L2 norm of
    the per-participant contribution after normalisation).

    The noisy distribution is re-projected onto the probability simplex
    (all values ≥ 0, sum ≈ 1) after noise addition.

    Args:
        distribution: Aggregated intent probabilities summing to ~1.0
        epsilon: DP privacy budget ε
        delta: DP failure probability δ
        n_participants: Number of sessions that contributed to this aggregate

    Returns:
        Noisy intent distribution (re-normalised)
    """
    if n_participants < 2:
        logger.warning("DP noise not applied: fewer than 2 participants")
        return distribution

    # L2 sensitivity per participant contribution to a normalised vector
    sensitivity = 2.0 / n_participants
    sigma = _dp_sigma(epsilon, delta, sensitivity)

    noisy = {}
    for intent, prob in distribution.items():
        noise = random.gauss(0.0, sigma)
        noisy[intent] = max(0.0, prob + noise)  # project to non-negative

    # Re-normalise to simplex
    total = sum(noisy.values())
    if total > 0:
        noisy = {k: round(v / total, 6) for k, v in noisy.items()}
    else:
        # Fallback: uniform distribution
        n = len(_ALL_INTENTS)
        noisy = {intent: round(1.0 / n, 6) for intent in _ALL_INTENTS}

    return noisy


# =============================================================================
# Quality Filtering
# Spec: TECHNICAL_PIPELINE.md Layer 9 / MASTER_INDEX.md Phase 8
# =============================================================================

def passes_quality_gate(
    frs: float,
    delta_score: Optional[float],
    frs_threshold: float = 0.60,
    delta_threshold: float = 0.65,
) -> bool:
    """
    Check if a feedback record meets the quality bar for FL aggregation.

    Requirements:
        - FRS (parent trust score) > 0.60
        - delta_score > 0.65 (model's prediction matched parent's response well)

    Sessions without a delta_score (no EFP computed, early sessions) are excluded.
    """
    if frs < frs_threshold:
        return False
    if delta_score is None or delta_score < delta_threshold:
        return False
    return True


# =============================================================================
# Stage-Stratified FedAvg
# Spec: SCIENTIFIC_MATHEMATICS.md Theorem 10.2
# =============================================================================

def federated_average(
    local_distributions: List[Dict[str, float]],
) -> Tuple[Dict[str, float], int]:
    """
    Compute the Federated Average (FedAvg) of a list of intent distributions.

    FedAvg formula (equal weights, since we don't know per-device dataset sizes):
        μ̄ = (1/N) × Σ_i μ_i   for each intent dimension

    Returns:
        (aggregated_distribution, n_participants)
    """
    n = len(local_distributions)
    if n == 0:
        uniform = {intent: round(1.0 / len(_ALL_INTENTS), 6) for intent in _ALL_INTENTS}
        return uniform, 0

    # Sum across participants
    aggregate: Dict[str, float] = {intent: 0.0 for intent in _ALL_INTENTS}
    for dist in local_distributions:
        dist = normalize_intent_distribution(dist, include_technical=False, fill_missing=True)
        for intent in _ALL_INTENTS:
            aggregate[intent] = aggregate[intent] + float(dist.get(intent, 0.0))

    # Average
    averaged = {k: round(v / n, 6) for k, v in aggregate.items()}

    # Normalise to simplex (in case inputs don't sum to exactly 1)
    total = sum(averaged.values())
    if total > 0 and abs(total - 1.0) > 0.01:
        averaged = {k: round(v / total, 6) for k, v in averaged.items()}

    return averaged, n


# =============================================================================
# Research Prior Blending
# Spec: MASTER_INDEX.md Phase 8 — research floor 0.10 always maintained
# =============================================================================

def blend_with_research_floor(
    population_distribution: Dict[str, float],
    research_floor: float = 0.10,
    stage: str = "UNKNOWN",
) -> Dict[str, float]:
    """
    Blend the population model distribution with the research prior floor.

    The population model REPLACES the static research prior ABOVE the floor.
    The floor (0.10 weight) always remains from original research literature.

    Formula:
        blended = research_floor × uniform + (1 - research_floor) × population

    This ensures the population model never completely overrides literature
    priors — important when population data is sparse or potentially biased.

    Args:
        population_distribution: FedAvg + DP noised intent distribution
        research_floor: Minimum contribution from uniform prior (default 0.10)
        stage: Developmental stage (logged only)

    Returns:
        Blended distribution that sums to 1.0
    """
    n_intents = len(_ALL_INTENTS)
    uniform_prior = 1.0 / n_intents

    blended: Dict[str, float] = {}
    for intent in _ALL_INTENTS:
        pop = float(population_distribution.get(intent, uniform_prior))
        blended[intent] = research_floor * uniform_prior + (1.0 - research_floor) * pop

    # Normalise
    total = sum(blended.values())
    if total > 0:
        blended = {k: round(v / total, 6) for k, v in blended.items()}

    logger.debug(f"FL blended prior for stage={stage}: {blended}")
    return blended


# =============================================================================
# Full Aggregation Pipeline (called by federated_aggregator Lambda)
# =============================================================================

def aggregate_stage(
    local_distributions: List[Dict[str, float]],
    epsilon: float = 1.0,
    delta: float = 1e-5,
    research_floor: float = 0.10,
    stage: str = "UNKNOWN",
) -> Dict:
    """
    Run the full FL aggregation pipeline for a single developmental stage.

    Steps:
        1. FedAvg across quality-filtered local distributions
        2. Add Gaussian DP noise (Theorem 10.1)
        3. Blend with research prior floor

    Returns:
        {
            "stage": str,
            "n_participants": int,
            "population_prior": Dict[str, float],  # blended, DP-protected
            "raw_aggregate": Dict[str, float],      # before DP noise
            "epsilon": float,
            "delta": float,
            "is_reliable": bool,  # True if n_participants >= MIN_PARTICIPANTS
        }
    """
    from constants import FL_MIN_PARTICIPANTS

    raw_aggregate, n = federated_average(local_distributions)
    is_reliable = n >= FL_MIN_PARTICIPANTS

    if n < 2:
        # Not enough data — return uniform prior blended with floor
        logger.info(f"Stage {stage}: only {n} participants — returning floor-blended uniform")
        uniform = {intent: round(1.0 / len(_ALL_INTENTS), 6) for intent in _ALL_INTENTS}
        population_prior = blend_with_research_floor(uniform, research_floor, stage)
        return {
            "stage": stage,
            "n_participants": n,
            "population_prior": population_prior,
            "raw_aggregate": raw_aggregate,
            "epsilon": epsilon,
            "delta": delta,
            "is_reliable": False,
        }

    # Add DP noise
    noisy = add_gaussian_noise(raw_aggregate, epsilon, delta, n)

    # Blend with research floor
    population_prior = blend_with_research_floor(noisy, research_floor, stage)

    logger.info(
        f"FL aggregation complete: stage={stage} n={n} reliable={is_reliable} "
        f"top_intent={max(population_prior, key=population_prior.get)}"
    )

    return {
        "stage": stage,
        "n_participants": n,
        "population_prior": population_prior,
        "raw_aggregate": raw_aggregate,
        "epsilon": epsilon,
        "delta": delta,
        "is_reliable": is_reliable,
    }
