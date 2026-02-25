"""
Qleam — Federated Aggregator Lambda (Phase 8, FIVL)

Stage-stratified Federated Averaging with Differential Privacy.
Triggered daily via EventBridge. Produces population model priors
that replace the static research priors in evidence_model.py.

Trigger: EventBridge scheduled rule (daily / configurable)
Input:   {} (no payload required — reads all qualifying feedback)
Output:  { status, stages_aggregated, total_sessions_used }

Architecture:
    1. Scan feedback table for quality-filtered sessions (FRS > 0.60, DS > 0.65)
    2. Group sessions by developmental_stage
    3. For each stage: FedAvg → DP noise → blend with research floor
    4. Write population prior to PopulationModel DynamoDB table
    5. Log aggregation stats (no raw data stored — privacy preserving)

Privacy guarantees (SCIENTIFIC_MATHEMATICS.md Theorem 10.1):
    - (ε=1.0, δ=1e-5)-differentially private Gaussian mechanism
    - Raw audio never stored or transmitted
    - Only normalised intent probability vectors aggregated
    - Noise calibrated per participant count
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    FEEDBACK_TABLE,
    FL_DELTA,
    FL_DELTA_QUALITY_GATE,
    FL_EPSILON,
    FL_FRS_QUALITY_GATE,
    FL_MIN_PARTICIPANTS,
    FL_RESEARCH_FLOOR,
    POPULATION_MODEL_TABLE,
    SESSION_TABLE,
)
from federated_learning import aggregate_stage, passes_quality_gate

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
feedback_table = dynamodb.Table(FEEDBACK_TABLE)
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
population_model_table = dynamodb.Table(POPULATION_MODEL_TABLE)

# All intent keys — must match evidence_model.py
_ALL_INTENTS = ["hunger", "discomfort", "connection", "fatigue", "overstimulation", "exploration"]

# Developmental stages to aggregate separately
_AGGREGATION_STAGES = [
    "NEWBORN",
    "EARLY_VOCAL",
    "CANONICAL_BABBLE",
    "PROTO_WORDS",
    "FIRST_WORDS",
    "WORD_COMBINATIONS",
    "EARLY_SENTENCES",
]


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _decimal_to_float(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_decimal_to_float(i) for i in val]
    return val


def _float_to_decimal(val: Any) -> Any:
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, dict):
        return {k: _float_to_decimal(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_float_to_decimal(i) for i in val]
    return val


def _scan_quality_feedback(limit: int = 5000) -> List[Dict]:
    """
    Scan the feedback table for all records with alignment_score + frs_after.

    Uses scan (not query) — this is a batch aggregation job that runs infrequently.
    Results are filtered in memory for quality gate compliance.

    Returns only records with: delta_score, frs_after, session_id, child_id.
    """
    paginator_kwargs = {
        "FilterExpression": "attribute_exists(delta_score) AND attribute_exists(frs_after)",
        "ProjectionExpression": "session_id, child_id, delta_score, frs_after, developmental_stage, response_type",
    }

    results = []
    try:
        response = feedback_table.scan(**paginator_kwargs)
        results.extend(response.get("Items", []))

        # Paginate if needed (up to limit)
        while "LastEvaluatedKey" in response and len(results) < limit:
            response = feedback_table.scan(
                ExclusiveStartKey=response["LastEvaluatedKey"],
                **paginator_kwargs,
            )
            results.extend(response.get("Items", []))
    except Exception as e:
        logger.error(f"Failed to scan feedback table: {e}")

    return [_decimal_to_float(item) for item in results]


def _get_session_intent_distribution(session_id: str) -> Optional[Dict[str, float]]:
    """
    Retrieve the blended intent distribution from a session's insight.
    This is the "local model weight" contributed by this session to FedAvg.

    Uses the EFP (Expected Feedback Profile) stored in the session, which
    is the model's intent probability distribution from evidence_model.py.
    """
    try:
        response = session_table.get_item(
            Key={"session_id": session_id},
            ProjectionExpression="efp, developmental_stage",
        )
        item = response.get("Item")
        if not item:
            return None
        efp = _decimal_to_float(item.get("efp") or {})
        # Validate it's a valid intent distribution
        if efp and all(k in _ALL_INTENTS for k in efp.keys()):
            return efp
    except Exception as e:
        logger.warning(f"Failed to get session {session_id} intent distribution: {e}")
    return None


def _get_parent_frs(child_id: str) -> float:
    """Retrieve the current FRS for a child's parent from the child profile."""
    try:
        response = child_profile_table.get_item(
            Key={"child_id": child_id},
            ProjectionExpression="parent_trust_score",
        )
        item = _decimal_to_float(response.get("Item", {}))
        return float(item.get("parent_trust_score") or 0.5)
    except Exception as e:
        logger.warning(f"Failed to get FRS for child {child_id}: {e}")
        return 0.5


def _write_population_prior(stage: str, result: Dict) -> None:
    """Write the aggregated population prior for a stage to DynamoDB."""
    now = datetime.now(timezone.utc).isoformat()
    item = {
        "stage": stage,
        "population_prior": result["population_prior"],
        "n_participants": result["n_participants"],
        "is_reliable": result["is_reliable"],
        "epsilon": result["epsilon"],
        "delta": str(result["delta"]),  # stored as string to avoid float precision
        "aggregated_at": now,
    }
    population_model_table.put_item(Item=_float_to_decimal(item))
    logger.info(
        f"Written population prior for stage={stage} n={result['n_participants']} "
        f"reliable={result['is_reliable']}"
    )


def lambda_handler(event: Dict, context: Any) -> Dict:
    """
    Federated Aggregator Lambda handler.

    Triggered by EventBridge on a schedule (default: daily).
    Reads all qualifying feedback, groups by developmental stage,
    runs FedAvg + DP noise + research floor blend per stage,
    and writes population priors to the PopulationModel table.

    No input payload required.
    """
    logger.info("Federated aggregator started")
    logger.info(
        f"Config: ε={FL_EPSILON} δ={FL_DELTA} FRS_gate={FL_FRS_QUALITY_GATE} "
        f"DS_gate={FL_DELTA_QUALITY_GATE} min_participants={FL_MIN_PARTICIPANTS}"
    )

    # 1. Scan feedback table for records with delta_score + frs
    all_feedback = _scan_quality_feedback()
    logger.info(f"Scanned {len(all_feedback)} feedback records with scoring data")

    # 2. Apply quality gate
    qualified = []
    for fb in all_feedback:
        frs = float(fb.get("frs_after") or 0.0)
        delta_score = float(fb.get("delta_score") or 0.0)
        if passes_quality_gate(frs, delta_score, FL_FRS_QUALITY_GATE, FL_DELTA_QUALITY_GATE):
            qualified.append(fb)

    logger.info(f"Quality gate: {len(qualified)}/{len(all_feedback)} sessions passed (FRS>{FL_FRS_QUALITY_GATE} DS>{FL_DELTA_QUALITY_GATE})")

    # 3. Group qualified sessions by developmental_stage
    # Retrieve EFP (intent distribution) for each qualifying session
    stage_distributions: Dict[str, List[Dict[str, float]]] = {s: [] for s in _AGGREGATION_STAGES}
    skipped_no_efp = 0
    skipped_no_stage = 0

    for fb in qualified:
        session_id = fb.get("session_id", "")
        stage = str(fb.get("developmental_stage", "") or "").upper()

        if not stage or stage not in _AGGREGATION_STAGES:
            skipped_no_stage += 1
            continue

        efp = _get_session_intent_distribution(session_id)
        if efp is None:
            skipped_no_efp += 1
            continue

        stage_distributions[stage].append(efp)

    logger.info(
        f"Sessions grouped: skipped_no_stage={skipped_no_stage} "
        f"skipped_no_efp={skipped_no_efp}"
    )

    # 4. Aggregate per stage
    stages_aggregated = []
    total_sessions_used = 0

    for stage in _AGGREGATION_STAGES:
        distributions = stage_distributions[stage]
        n = len(distributions)
        logger.info(f"Aggregating stage={stage}: {n} sessions")

        result = aggregate_stage(
            local_distributions=distributions,
            epsilon=FL_EPSILON,
            delta=FL_DELTA,
            research_floor=FL_RESEARCH_FLOOR,
            stage=stage,
        )

        # 5. Write to DynamoDB
        try:
            _write_population_prior(stage, result)
            stages_aggregated.append({
                "stage": stage,
                "n_participants": result["n_participants"],
                "is_reliable": result["is_reliable"],
                "top_intent": max(result["population_prior"], key=result["population_prior"].get),
            })
            total_sessions_used += result["n_participants"]
        except Exception as e:
            logger.error(f"Failed to write population prior for stage={stage}: {e}")

    logger.info(
        f"Federated aggregation complete: {len(stages_aggregated)} stages "
        f"{total_sessions_used} total sessions used"
    )

    return {
        "status": "ok",
        "stages_aggregated": len(stages_aggregated),
        "total_sessions_used": total_sessions_used,
        "stages": stages_aggregated,
        "config": {
            "epsilon": FL_EPSILON,
            "delta": FL_DELTA,
            "frs_quality_gate": FL_FRS_QUALITY_GATE,
            "delta_quality_gate": FL_DELTA_QUALITY_GATE,
            "min_participants": FL_MIN_PARTICIPANTS,
            "research_floor": FL_RESEARCH_FLOOR,
        },
    }
