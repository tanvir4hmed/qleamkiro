"""
Qleam — Developmental Tracker Lambda (Phase 6, Layer 7)

Tracks CBR trend, VTL growth, stage-aware adaptive EMA, milestone logging, and φ order parameter.

Trigger: Step Function invocation after InsightGenerator
Input:  { child_id, session_id, cluster_id }
Output: { status, developmental_view }
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import (
    CHILD_PROFILE_TABLE,
    MILESTONES_TABLE,
    MILESTONE_TYPES,
    SESSION_TABLE,
)
from proto_word import compute_phi

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
session_table = dynamodb.Table(SESSION_TABLE)
child_profile_table = dynamodb.Table(CHILD_PROFILE_TABLE)
milestones_table = dynamodb.Table(MILESTONES_TABLE)


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


def _get_session(session_id: str) -> Optional[Dict]:
    resp = session_table.get_item(Key={"session_id": session_id})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def _get_child_profile(child_id: str) -> Optional[Dict]:
    resp = child_profile_table.get_item(Key={"child_id": child_id})
    item = resp.get("Item")
    return _decimal_to_float(item) if item else None


def _get_recent_sessions(child_id: str, limit: int = 5) -> List[Dict]:
    """Query last N sessions for a child (most recent first) using the child_id-timestamp-index."""
    resp = session_table.query(
        IndexName="child_id-timestamp-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
        ScanIndexForward=False,
        Limit=limit,
    )
    return [_decimal_to_float(item) for item in resp.get("Items", [])]


def _milestone_already_logged(child_id: str, milestone_type: str) -> bool:
    """Check if a milestone of this type has already been logged for this child."""
    resp = milestones_table.query(
        IndexName="child_id-first_date-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
    )
    for item in resp.get("Items", []):
        if item.get("milestone_type") == milestone_type:
            return True
    return False


def _log_milestone(child_id: str, milestone_type: str, session_id: str, details: Dict) -> str:
    """Write a new milestone record. Returns milestone_id."""
    milestone_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    milestones_table.put_item(Item={
        "child_id": child_id,
        "milestone_id": milestone_id,
        "milestone_type": milestone_type,
        "description": MILESTONE_TYPES.get(milestone_type, milestone_type),
        "first_date": now,
        "session_id": session_id,
        "details": _float_to_decimal(details),
    })
    logger.info(f"Milestone logged: {milestone_type} for child {child_id}")
    return milestone_id


def _categorize_cbr(cbr: float) -> str:
    if cbr >= 0.50:
        return "CANONICAL_ESTABLISHED"
    if cbr >= 0.15:
        return "EMERGING_CANONICAL"
    return "PRE_CANONICAL"


def _compute_cbr_trend(cbr_values: List[float]) -> str:
    if len(cbr_values) < 2:
        return "STABLE"
    delta = cbr_values[0] - cbr_values[-1]  # most recent minus oldest
    if delta > 0.08:
        return "RISING"
    if delta < -0.08:
        return "FALLING"
    return "STABLE"


def lambda_handler(event: dict, context) -> dict:
    """
    Developmental Tracker handler.

    Args:
        event: { "child_id": str, "session_id": str, "cluster_id": str }
    """
    child_id = event.get("child_id", "")
    session_id = event.get("session_id", "")
    cluster_id = event.get("cluster_id", "")

    if not child_id or not session_id:
        logger.warning("DevelopmentalTracker called with missing child_id or session_id")
        return {"status": "skipped", "reason": "missing_fields"}

    logger.info(f"DevelopmentalTracker: child={child_id} session={session_id}")

    # --- Load current session ---
    session = _get_session(session_id)
    if not session:
        logger.warning(f"Session {session_id} not found")
        return {"status": "skipped", "reason": "session_not_found"}

    admission_status = str((session.get("admission_gate") or {}).get("status", "")).upper().strip()
    if admission_status and admission_status != "BABY_PASS":
        logger.info(
            f"DevelopmentalTracker: skipping non-admitted session {session_id} "
            f"(admission_status={admission_status})"
        )
        return {"status": "skipped", "reason": "not_admitted_baby", "admission_status": admission_status}

    rich_features = session.get("rich_features", {})
    biological = session.get("biological", {})
    current_cbr = float(rich_features.get("cbr_estimate", 0.0))
    vtl_cm = float(biological.get("vtl_cm", 0.0))
    developmental_stage = session.get("developmental_stage", "")
    developmental_mode = session.get("developmental_mode", "")

    # --- Rolling CBR window (last 5 sessions) ---
    recent_sessions = _get_recent_sessions(child_id, limit=5)
    cbr_history = [
        float(s.get("rich_features", {}).get("cbr_estimate", 0.0))
        for s in recent_sessions
        if s.get("session_id") != session_id
    ]
    cbr_window = [current_cbr] + cbr_history[:4]
    cbr_trend = _compute_cbr_trend(cbr_window)
    cbr_category = _categorize_cbr(current_cbr)

    # --- Load child profile ---
    profile = _get_child_profile(child_id) or {}
    old_cbr_ema = float(profile.get("cbr_ema", 0.0))
    context_reliability = float(profile.get("context_reliability", 0.5))
    parent_trust = float(profile.get("parent_trust_score", 0.5))

    # Count clusters for stability ratio
    from constants import SOUND_CLUSTER_TABLE
    cluster_table = dynamodb.Table(SOUND_CLUSTER_TABLE)
    cluster_resp = cluster_table.query(
        IndexName="child_id-last_updated-index",
        KeyConditionExpression=Key("child_id").eq(child_id),
    )
    all_clusters = cluster_resp.get("Items", [])
    total_clusters = len(all_clusters)
    stable_clusters = sum(
        1 for c in all_clusters if int(c.get("frequency_count", 0)) >= 3
    )
    cluster_stability = (stable_clusters / total_clusters) if total_clusters > 0 else 0.0

    # F2 diversity: std of formant_f2 across recent sessions (normalized to 0–1, max=500Hz)
    f2_values = [
        float(s.get("rich_features", {}).get("formant_f2", 0.0))
        for s in recent_sessions
        if s.get("rich_features", {}).get("formant_f2", 0.0) > 0
    ]
    if len(f2_values) > 1:
        import statistics
        f2_std = statistics.stdev(f2_values)
        f2_diversity = min(1.0, f2_std / 500.0)
    else:
        f2_diversity = 0.0

    # --- Detect stage transition ---
    prev_mode = profile.get("last_developmental_mode", "")
    is_transition = (
        (prev_mode and prev_mode != developmental_mode)
        or abs(current_cbr - old_cbr_ema) > 0.15
    )

    # --- Adaptive EMA alpha ---
    alpha = 0.30
    if is_transition:
        alpha = min(0.80, alpha + 0.50)
    elif cbr_trend == "FALLING":
        alpha = max(0.10, alpha - 0.10)

    new_cbr_ema = round(alpha * current_cbr + (1.0 - alpha) * old_cbr_ema, 4)

    # --- φ order parameter ---
    phi_result = compute_phi(
        cbr_ema=new_cbr_ema,
        cluster_stability=cluster_stability,
        f2_diversity=f2_diversity,
        cross_situational=context_reliability,
        parent_trust=parent_trust,
    )

    # --- Update child profile ---
    try:
        child_profile_table.update_item(
            Key={"child_id": child_id},
            UpdateExpression=(
                "SET cbr_ema = :ema, last_developmental_mode = :mode, "
                "last_phi = :phi, last_phi_label = :label"
            ),
            ExpressionAttributeValues={
                ":ema": _float_to_decimal(new_cbr_ema),
                ":mode": developmental_mode,
                ":phi": _float_to_decimal(phi_result["phi"]),
                ":label": phi_result["phi_label"],
            },
        )
    except Exception as e:
        logger.warning(f"Failed to update child profile CBR EMA: {e}")

    # --- Milestone checks ---
    milestones_this_session = []

    if current_cbr > 0.20 and not _milestone_already_logged(child_id, "FIRST_CANONICAL_BABBLE"):
        _log_milestone(child_id, "FIRST_CANONICAL_BABBLE", session_id, {"cbr": current_cbr})
        milestones_this_session.append("FIRST_CANONICAL_BABBLE")

    if developmental_mode == "LINGUISTIC" and not _milestone_already_logged(child_id, "LINGUISTIC_MODE_TRANSITION"):
        _log_milestone(child_id, "LINGUISTIC_MODE_TRANSITION", session_id, {"stage": developmental_stage})
        milestones_this_session.append("LINGUISTIC_MODE_TRANSITION")

    # --- Build developmental_view and store on session ---
    developmental_view = {
        "current_stage": developmental_stage,
        "current_mode": developmental_mode,
        "cbr": current_cbr,
        "cbr_trend": cbr_trend,
        "cbr_category": cbr_category,
        "cbr_ema": new_cbr_ema,
        "vtl_cm": vtl_cm,
        "phi": phi_result["phi"],
        "phi_label": phi_result["phi_label"],
        "milestones_this_session": milestones_this_session,
    }

    try:
        session_table.update_item(
            Key={"session_id": session_id},
            UpdateExpression="SET developmental_view = :dv",
            ExpressionAttributeValues={":dv": _float_to_decimal(developmental_view)},
        )
    except Exception as e:
        logger.warning(f"Failed to store developmental_view on session: {e}")

    logger.info(
        f"DevelopmentalTracker: cbr={current_cbr:.3f} trend={cbr_trend} "
        f"phi={phi_result['phi']:.3f} milestones={milestones_this_session}"
    )
    return {
        "status": "ok",
        "child_id": child_id,
        "session_id": session_id,
        "developmental_view": developmental_view,
    }
