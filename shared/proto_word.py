"""
Qleam — Proto-Word Crystallization Module (Phase 6)

Evaluates whether an acoustic cluster has crystallised into a proto-word,
and computes the φ (phi) order parameter reflecting overall language readiness.
"""
from typing import Dict


def check_proto_word_criteria(cluster: Dict) -> Dict:
    """
    Evaluate 5 criteria to determine proto-word status for a given cluster.

    Uses existing cluster fields (no new data required):
        frequency_count         — number of times this cluster was observed
        semantic_alignment_score — context co-occurrence proxy (0–1)
        reinforcement_weight    — parent response effectiveness (0–1)

    Returns:
        {
            "criteria": {
                "stable_across_sessions": bool,   # freq >= 3
                "sufficient_observations": bool,  # freq >= 5
                "semantic_context":        bool,  # semantic_alignment_score >= 0.50
                "effective_response":      bool,  # reinforcement_weight >= 0.65
                "parent_confirmation":     bool,  # semantic_alignment_score > 0.0
            },
            "met_count": int,          # 0–5
            "proto_word_status": str,  # "NONE" | "CANDIDATE" | "CRYSTALLIZED"
        }

    Status rules:
        CRYSTALLIZED: all 5 met AND semantic_alignment_score >= 0.85
        CANDIDATE:   met_count >= 3
        NONE:        met_count < 3
    """
    freq = cluster.get("frequency_count", 0)
    alignment = float(cluster.get("semantic_alignment_score", 0.0))
    reinforcement = float(cluster.get("reinforcement_weight", 0.5))

    criteria = {
        "stable_across_sessions": freq >= 3,
        "sufficient_observations": freq >= 5,
        "semantic_context": alignment >= 0.50,
        "effective_response": reinforcement >= 0.65,
        "parent_confirmation": alignment > 0.0,
    }
    met_count = sum(1 for v in criteria.values() if v)

    all_met = met_count == 5
    if all_met and alignment >= 0.85:
        # Use CRYSTALLIZED across API/UI for consistent signal status naming.
        status = "CRYSTALLIZED"
    elif met_count >= 3:
        status = "CANDIDATE"
    else:
        status = "NONE"

    return {
        "criteria": criteria,
        "met_count": met_count,
        "proto_word_status": status,
    }


def compute_phi(
    cbr_ema: float,
    cluster_stability: float,
    f2_diversity: float,
    cross_situational: float,
    parent_trust: float,
) -> Dict:
    """
    Compute the φ (phi) order parameter — an aggregate measure of language readiness.

    Weights:
        0.30 × cbr_ema           — canonical babbling EMA (from child profile)
        0.25 × cluster_stability — ratio of clusters with freq>3 / total clusters
        0.20 × f2_diversity      — normalized F2 std across last 5 sessions (0–1)
        0.15 × cross_situational — context_reliability from child profile
        0.10 × parent_trust      — parent_trust_score from child profile

    Returns:
        {
            "phi":       float,  # [0, 1]
            "phi_label": str,
        }
    """
    phi = (
        0.30 * float(cbr_ema)
        + 0.25 * float(cluster_stability)
        + 0.20 * float(f2_diversity)
        + 0.15 * float(cross_situational)
        + 0.10 * float(parent_trust)
    )
    phi = round(min(1.0, max(0.0, phi)), 4)

    if phi < 0.25:
        label = "Early vocal exploration"
    elif phi < 0.45:
        label = "Language signals forming"
    elif phi < 0.65:
        label = "Patterns stabilizing"
    else:
        label = "Rich personal vocabulary"

    return {"phi": phi, "phi_label": label}
