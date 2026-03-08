"""
Qleam — Training Check Lambda (Phase 3)
Triggered by EventBridge (daily) to check if model retraining is needed.

Conditions to trigger retraining:
1. Batch trigger: >= 50 new confirmed samples since last training
2. Weekly trigger: >= 10 new samples since last training AND >= 7 days since last train
3. Minimum threshold: total confirmed samples >= 30

If conditions met, starts the training Step Function.
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

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
    """Check if retraining conditions are met and trigger Step Function."""
    try:
        if not TRAINING_FEATURES_TABLE:
            logger.info("TRAINING_FEATURES_TABLE not configured, skipping")
            return {"triggered": False, "reason": "no_table"}

        training_features_table = dynamodb.Table(TRAINING_FEATURES_TABLE)

        # Count confirmed samples
        total, since_last_train = _count_samples(training_features_table)
        logger.info(
            f"Training check: total_confirmed={total}, "
            f"since_last_train={since_last_train}"
        )

        if total < MIN_TOTAL_SAMPLES:
            logger.info(f"Not enough total samples ({total} < {MIN_TOTAL_SAMPLES})")
            return {"triggered": False, "reason": "insufficient_total",
                    "total": total}

        should_trigger = False
        trigger_reason = ""

        # Batch trigger
        if since_last_train >= BATCH_TRIGGER_THRESHOLD:
            should_trigger = True
            trigger_reason = f"batch_threshold:{since_last_train}"

        # Weekly trigger
        if not should_trigger and since_last_train >= WEEKLY_TRIGGER_THRESHOLD:
            last_train_date = _get_last_training_date(training_features_table)
            if last_train_date:
                days_since = (datetime.now(timezone.utc) - last_train_date).days
                if days_since >= 7:
                    should_trigger = True
                    trigger_reason = f"weekly:{since_last_train}_samples_{days_since}_days"

        if should_trigger:
            logger.info(f"Triggering retraining: {trigger_reason}")
            _start_training(total, since_last_train, trigger_reason)
            return {"triggered": True, "reason": trigger_reason,
                    "total": total, "new_samples": since_last_train}
        else:
            logger.info("No retraining needed")
            return {"triggered": False, "reason": "below_threshold",
                    "total": total, "new_samples": since_last_train}

    except Exception as e:
        logger.error(f"Training check error: {e}", exc_info=True)
        return {"triggered": False, "reason": f"error:{e}"}


def _count_samples(table):
    """Count total confirmed samples and samples since last training."""
    from boto3.dynamodb.conditions import Attr

    # Total confirmed
    total_resp = table.scan(
        FilterExpression=Attr("is_confirmed").eq(True),
        Select="COUNT",
    )
    total = total_resp.get("Count", 0)

    # Samples since last training (confirmed but not yet trained on)
    new_resp = table.scan(
        FilterExpression=(
            Attr("is_confirmed").eq(True) &
            Attr("included_in_training").not_exists()
        ),
        Select="COUNT",
    )
    since_last = new_resp.get("Count", 0)

    return total, since_last


def _get_last_training_date(table):
    """Get the date of the most recent training run from model versions."""
    try:
        model_versions_table_name = os.environ.get(
            "MODEL_VERSIONS_TABLE", ""
        )
        if not model_versions_table_name:
            return None

        mv_table = dynamodb.Table(model_versions_table_name)
        response = mv_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key("model_type").eq("emotion_classifier"),
            ScanIndexForward=False,
            Limit=1,
        )
        items = response.get("Items", [])
        if items:
            trained_at = items[0].get("trained_at", "")
            if trained_at:
                return datetime.fromisoformat(trained_at.replace("Z", "+00:00"))
    except Exception as e:
        logger.warning(f"Failed to get last training date: {e}")
    return None


def _start_training(total_samples, new_samples, trigger_reason):
    """Start the training Step Function."""
    if not TRAINING_STEP_FUNCTION_ARN:
        logger.warning("TRAINING_STEP_FUNCTION_ARN not configured, cannot trigger")
        return

    try:
        now = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        sfn_client.start_execution(
            stateMachineArn=TRAINING_STEP_FUNCTION_ARN,
            name=f"retrain-{now}",
            input=json.dumps({
                "step": "load",
                "total_samples": total_samples,
                "new_samples": new_samples,
                "trigger_reason": trigger_reason,
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            }),
        )
        logger.info(f"Started training Step Function: retrain-{now}")
    except Exception as e:
        logger.error(f"Failed to start training Step Function: {e}")
