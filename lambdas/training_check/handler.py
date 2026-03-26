"""
Qleam — Training Check Lambda (Phase 3: Age-Bucket Training)
Triggered by EventBridge (daily) to check if model retraining is needed.

Phase 3 Changes:
- Per-bucket training: each age-day/week/slot trains separately
- Multiple independent training runs triggered per check
- Bucket-specific thresholds and sample counts

Conditions to trigger retraining (per bucket):
1. Batch trigger: >= 50 new confirmed samples since last training
2. Weekly trigger: >= 10 new samples since last training AND >= 7 days since last train
3. Minimum threshold: total confirmed samples >= 30

If conditions met, starts the training Step Function with bucket parameters.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../shared"))
sys.path.insert(0, "/var/task/shared")

from constants import TRAINING_FEATURES_TABLE

log_level = os.environ.get("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, log_level))
logger = logging.getLogger(__name__)

dynamodb = boto3.resource("dynamodb")
sfn_client = boto3.client("stepfunctions")

TRAINING_STEP_FUNCTION_ARN = os.environ.get("TRAINING_STEP_FUNCTION_ARN", "")
BATCH_TRIGGER_THRESHOLD = 50
WEEKLY_TRIGGER_THRESHOLD = 10
MIN_TOTAL_SAMPLES = 30


def lambda_handler(event, context):
    """Check if retraining conditions are met per bucket and trigger Step Functions."""
    try:
        if not TRAINING_FEATURES_TABLE:
            logger.info("TRAINING_FEATURES_TABLE not configured, skipping")
            return {"triggered": False, "reason": "no_table"}

        training_features_table = dynamodb.Table(TRAINING_FEATURES_TABLE)

        # Count samples per bucket
        bucket_stats = _count_samples_per_bucket(training_features_table)
        logger.info(f"Training check: found {len(bucket_stats)} buckets with samples")

        # Check each bucket for training conditions
        buckets_to_train = _check_buckets_for_training(bucket_stats, training_features_table)

        if not buckets_to_train:
            logger.info("No buckets meet training conditions")
            return {
                "triggered": False,
                "reason": "no_buckets_ready",
                "total_buckets": len(bucket_stats),
            }

        # Start training for each bucket
        triggered_runs = []
        for bucket_info in buckets_to_train:
            try:
                run_id = _start_training_for_bucket(bucket_info)
                triggered_runs.append({
                    "bucket_type": bucket_info["bucket_type"],
                    "bucket_value": bucket_info["bucket_value"],
                    "run_id": run_id,
                    "reason": bucket_info["trigger_reason"],
                })
            except Exception as e:
                logger.error(f"Failed to start training for bucket {bucket_info}: {e}")

        logger.info(f"Triggered {len(triggered_runs)} training runs")
        return {
            "triggered": True,
            "training_runs": triggered_runs,
            "total_buckets_checked": len(bucket_stats),
        }

    except Exception as e:
        logger.error(f"Training check error: {e}", exc_info=True)
        return {"triggered": False, "reason": f"error:{e}"}


def _scan_confirmed_samples(table, projection_expression: str = None) -> List[Dict]:
    """Scan confirmed training samples with pagination support."""
    from boto3.dynamodb.conditions import Attr

    scan_kwargs = {
        "FilterExpression": Attr("is_confirmed").eq(True),
    }
    if projection_expression:
        scan_kwargs["ProjectionExpression"] = projection_expression

    response = table.scan(**scan_kwargs)
    items = response.get("Items", [])

    while "LastEvaluatedKey" in response:
        paged_kwargs = {
            **scan_kwargs,
            "ExclusiveStartKey": response["LastEvaluatedKey"],
        }
        response = table.scan(**paged_kwargs)
        items.extend(response.get("Items", []))

    return items


def _count_samples(table) -> Tuple[int, int]:
    """
    Backward-compatible sample counts for total confirmed and untrained samples.

    This preserves the pre-bucket helper contract used by tests and older callers
    while the Lambda itself now evaluates bucket-specific counts separately.
    """
    items = _scan_confirmed_samples(table, "included_in_training")
    total = len(items)
    since_last = sum(1 for item in items if "included_in_training" not in item)
    return total, since_last


def _count_samples_per_bucket(table) -> Dict[str, Dict]:
    """
    Count confirmed samples grouped by age buckets.
    
    Returns:
        Dict mapping bucket_key to stats:
        {
            "day_45": {
                "bucket_type": "day",
                "bucket_value": "45",
                "total": 120,
                "since_last_train": 15,
                "communication_stage": "A",
            },
            ...
        }
    """
    items = _scan_confirmed_samples(
        table,
        "age_day_bucket,age_week_bucket,age_slot_bucket,communication_stage,included_in_training",
    )

    # Group by buckets
    bucket_stats = {}

    for item in items:
        age_day = item.get("age_day_bucket")
        age_week = item.get("age_week_bucket")
        age_slot = item.get("age_slot_bucket")
        stage = item.get("communication_stage", "A")
        is_untrained = "included_in_training" not in item

        # Day bucket (most specific)
        if age_day is not None:
            key = f"day_{age_day}"
            if key not in bucket_stats:
                bucket_stats[key] = {
                    "bucket_type": "day",
                    "bucket_value": str(age_day),
                    "communication_stage": stage,
                    "total": 0,
                    "since_last_train": 0,
                }
            bucket_stats[key]["total"] += 1
            if is_untrained:
                bucket_stats[key]["since_last_train"] += 1

        # Week bucket
        if age_week is not None:
            key = f"week_{age_week}"
            if key not in bucket_stats:
                bucket_stats[key] = {
                    "bucket_type": "week",
                    "bucket_value": str(age_week),
                    "communication_stage": stage,
                    "total": 0,
                    "since_last_train": 0,
                }
            bucket_stats[key]["total"] += 1
            if is_untrained:
                bucket_stats[key]["since_last_train"] += 1

        # Slot bucket (least specific)
        if age_slot:
            key = f"slot_{age_slot}"
            if key not in bucket_stats:
                bucket_stats[key] = {
                    "bucket_type": "slot",
                    "bucket_value": age_slot,
                    "communication_stage": stage,
                    "total": 0,
                    "since_last_train": 0,
                }
            bucket_stats[key]["total"] += 1
            if is_untrained:
                bucket_stats[key]["since_last_train"] += 1

    return bucket_stats


def _check_buckets_for_training(
    bucket_stats: Dict[str, Dict],
    table,
) -> List[Dict]:
    """
    Check which buckets meet training conditions.
    
    Returns:
        List of bucket info dicts ready for training.
    """
    buckets_to_train = []

    for bucket_key, stats in bucket_stats.items():
        total = stats["total"]
        since_last = stats["since_last_train"]

        if total < MIN_TOTAL_SAMPLES:
            continue

        should_trigger = False
        trigger_reason = ""

        # Batch trigger
        if since_last >= BATCH_TRIGGER_THRESHOLD:
            should_trigger = True
            trigger_reason = f"batch_threshold:{since_last}"

        # Weekly trigger
        if not should_trigger and since_last >= WEEKLY_TRIGGER_THRESHOLD:
            last_train_date = _get_last_training_date_for_bucket(
                stats["bucket_type"],
                stats["bucket_value"],
            )
            if last_train_date:
                days_since = (datetime.now(timezone.utc) - last_train_date).days
                if days_since >= 7:
                    should_trigger = True
                    trigger_reason = f"weekly:{since_last}_samples_{days_since}_days"
            else:
                # No previous training for this bucket
                should_trigger = True
                trigger_reason = f"first_training:{since_last}_samples"

        if should_trigger:
            buckets_to_train.append({
                **stats,
                "trigger_reason": trigger_reason,
            })
            logger.info(
                f"Bucket {bucket_key} ready for training: "
                f"total={total}, new={since_last}, reason={trigger_reason}"
            )

    return buckets_to_train


def _get_last_training_date_for_bucket(
    bucket_type: str,
    bucket_value: str,
) -> datetime:
    """Get the date of the most recent training run for this bucket."""
    try:
        model_versions_table_name = os.environ.get("MODEL_VERSIONS_TABLE", "")
        if not model_versions_table_name:
            return None

        mv_table = dynamodb.Table(model_versions_table_name)
        from boto3.dynamodb.conditions import Key, Attr

        # Query by model_type, filter by bucket
        response = mv_table.query(
            KeyConditionExpression=Key("model_type").eq("emotion_classifier"),
            FilterExpression=(
                Attr("age_bucket_type").eq(bucket_type) &
                Attr("age_bucket_value").eq(bucket_value)
            ),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            trained_at = items[0].get("trained_at", "")
            if trained_at:
                return datetime.fromisoformat(trained_at.replace("Z", "+00:00"))
    except Exception as e:
        logger.warning(f"Failed to get last training date for bucket: {e}")
    return None


def _start_training_for_bucket(bucket_info: Dict) -> str:
    """Start the training Step Function for a specific bucket."""
    if not TRAINING_STEP_FUNCTION_ARN:
        logger.warning("TRAINING_STEP_FUNCTION_ARN not configured, cannot trigger")
        return ""

    try:
        now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        bucket_type = bucket_info["bucket_type"]
        bucket_value = bucket_info["bucket_value"]
        run_id = f"retrain-{bucket_type}-{bucket_value}-{now}"

        sfn_client.start_execution(
            stateMachineArn=TRAINING_STEP_FUNCTION_ARN,
            name=run_id,
            input=json.dumps({
                "step": "load",
                "bucket_type": bucket_type,
                "bucket_value": bucket_value,
                "communication_stage": bucket_info.get("communication_stage", "A"),
                "total_samples": bucket_info["total"],
                "new_samples": bucket_info["since_last_train"],
                "trigger_reason": bucket_info["trigger_reason"],
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }),
        )
        logger.info(f"Started training Step Function: {run_id}")
        return run_id
    except Exception as e:
        logger.error(f"Failed to start training Step Function: {e}")
        return ""
