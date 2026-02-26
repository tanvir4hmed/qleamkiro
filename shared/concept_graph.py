"""
Qleam — Concept Graph Shared Module
Operations for the Personal Concept Graph (Phase 5).

Each child has a growing map of semantic concepts linked to acoustic clusters.
Universal concepts (hunger, sleep, etc.) are pre-populated at registration.
Personal concepts (bunny_toy, nap_time, etc.) are discovered from parent free text.
"""
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Universal concepts pre-populated for every child at registration
UNIVERSAL_CONCEPTS = [
    # Canonical v2 baby-state taxonomy
    "hunger",
    "sleep",
    "pain",
    "discomfort",
    "closeness",
    "frustration",
    "happy",
    "exploration",
    "distress_unknown",
    # Additional universal needs/context concepts
    "thirst",
    "comfort",
    "connection",
    "attention",
    "fear",
    "cold",
    "hot",
]


def _float_to_decimal(val: Any) -> Any:
    if isinstance(val, float):
        return Decimal(str(val))
    if isinstance(val, int) and not isinstance(val, bool):
        return Decimal(val)
    if isinstance(val, dict):
        return {k: _float_to_decimal(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_float_to_decimal(i) for i in val]
    return val


def _decimal_to_float(val: Any) -> Any:
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, dict):
        return {k: _decimal_to_float(v) for k, v in val.items()}
    if isinstance(val, list):
        return [_decimal_to_float(i) for i in val]
    return val


def pre_populate_universal_concepts(child_id: str, table) -> None:
    """
    Write universal concepts for a newly registered child.
    Called from api_handler.create_child() immediately after profile creation.
    Uses batch_writer for efficiency.
    """
    now = datetime.now(timezone.utc).isoformat()
    with table.batch_writer() as batch:
        for label in UNIVERSAL_CONCEPTS:
            batch.put_item(Item={
                "child_id": child_id,
                "concept_id": str(uuid.uuid4()),
                "label": label,
                "category": "universal",
                "first_appeared": now,
                "acoustic_clusters": [],
                "parent_descriptions": [],
                "confidence": Decimal("0.5"),
                "confirmation_count": 0,
            })
    logger.info(f"Pre-populated {len(UNIVERSAL_CONCEPTS)} universal concepts for child {child_id}")


def get_concepts(child_id: str, table, limit: int = 20) -> List[Dict]:
    """
    Return all concepts for a child, sorted by confirmation_count descending.
    Used by GET /child/{child_id}/concepts endpoint.
    """
    response = table.query(
        KeyConditionExpression="child_id = :cid",
        ExpressionAttributeValues={":cid": child_id},
    )
    items = [_decimal_to_float(item) for item in response.get("Items", [])]
    items.sort(key=lambda x: x.get("confirmation_count", 0), reverse=True)
    return items[:limit]


def upsert_concept(
    child_id: str,
    label: str,
    category: str,
    table,
    cluster_id: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """
    Find existing concept by label (case-insensitive) or create a new one.
    - Appends cluster_id to acoustic_clusters (if provided and not already present)
    - Appends description to parent_descriptions (if provided, capped at 10)
    - Increments confirmation_count and nudges confidence up (EMA α=0.10)

    Returns concept_id.
    """
    # Query all concepts for child to find existing by label
    response = table.query(
        KeyConditionExpression="child_id = :cid",
        ExpressionAttributeValues={":cid": child_id},
    )
    existing = None
    for item in response.get("Items", []):
        if item.get("label", "").lower() == label.lower():
            existing = _decimal_to_float(item)
            break

    now = datetime.now(timezone.utc).isoformat()

    if existing is None:
        # Create new concept
        concept_id = str(uuid.uuid4())
        clusters = [cluster_id] if cluster_id else []
        descriptions = [description] if description else []
        table.put_item(Item={
            "child_id": child_id,
            "concept_id": concept_id,
            "label": label.lower(),
            "category": category,
            "first_appeared": now,
            "acoustic_clusters": clusters,
            "parent_descriptions": descriptions,
            "confidence": Decimal("0.5"),
            "confirmation_count": 1,
        })
        logger.info(f"Created concept '{label}' ({category}) for child {child_id}")
        return concept_id
    else:
        # Update existing concept
        concept_id = existing["concept_id"]
        clusters = existing.get("acoustic_clusters", [])
        descriptions = existing.get("parent_descriptions", [])
        confirmation_count = existing.get("confirmation_count", 0) + 1
        old_confidence = existing.get("confidence", 0.5)
        new_confidence = round(min(1.0, 0.10 * 1.0 + 0.90 * old_confidence), 4)

        if cluster_id and cluster_id not in clusters:
            clusters = clusters + [cluster_id]
        if description:
            descriptions = (descriptions + [description])[-10:]  # keep last 10

        update_expr = (
            "SET confirmation_count = :cc, confidence = :conf, "
            "acoustic_clusters = :cl, parent_descriptions = :desc"
        )
        table.update_item(
            Key={"child_id": child_id, "concept_id": concept_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues={
                ":cc": confirmation_count,
                ":conf": _float_to_decimal(new_confidence),
                ":cl": clusters,
                ":desc": descriptions,
            },
        )
        logger.info(f"Updated concept '{label}' for child {child_id}: count={confirmation_count} confidence={new_confidence:.3f}")
        return concept_id
