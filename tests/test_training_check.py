"""Tests for lambdas/training_check/handler.py — tests the core logic functions."""
import importlib.util
import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

# Load training_check handler explicitly by file path to avoid collision
# with model_trainer/handler.py (both are named "handler")
_tc_spec = importlib.util.spec_from_file_location(
    "training_check_handler",
    os.path.join(os.path.dirname(__file__), "..", "lambdas", "training_check", "handler.py"),
)
tc_handler = importlib.util.module_from_spec(_tc_spec)
_tc_spec.loader.exec_module(tc_handler)


class TestCountSamples:
    """Test the _count_samples helper directly."""

    @mock_aws
    def test_empty_table(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-TrainingFeatures",
            KeySchema=[{"AttributeName": "feature_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "feature_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        total, since_last = tc_handler._count_samples(table)
        assert total == 0
        assert since_last == 0

    @mock_aws
    def test_all_confirmed_none_trained(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-TrainingFeatures",
            KeySchema=[{"AttributeName": "feature_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "feature_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        for i in range(10):
            table.put_item(Item={"feature_id": f"f-{i}", "is_confirmed": True})

        total, since_last = tc_handler._count_samples(table)
        assert total == 10
        assert since_last == 10  # None have included_in_training

    @mock_aws
    def test_mix_trained_and_new(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-TrainingFeatures",
            KeySchema=[{"AttributeName": "feature_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "feature_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # 20 already trained
        for i in range(20):
            table.put_item(Item={
                "feature_id": f"old-{i}",
                "is_confirmed": True,
                "included_in_training": "train-001",
            })
        # 5 new confirmed
        for i in range(5):
            table.put_item(Item={
                "feature_id": f"new-{i}",
                "is_confirmed": True,
            })

        total, since_last = tc_handler._count_samples(table)
        assert total == 25
        assert since_last == 5

    @mock_aws
    def test_unconfirmed_not_counted(self):
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-TrainingFeatures",
            KeySchema=[{"AttributeName": "feature_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "feature_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        # 5 confirmed
        for i in range(5):
            table.put_item(Item={"feature_id": f"c-{i}", "is_confirmed": True})
        # 10 not confirmed
        for i in range(10):
            table.put_item(Item={"feature_id": f"nc-{i}", "is_confirmed": False})

        total, since_last = tc_handler._count_samples(table)
        assert total == 5
        assert since_last == 5


class TestTrainingCheckThresholds:
    """Test the threshold constants are reasonable."""

    def test_thresholds_exist(self):
        assert tc_handler.BATCH_TRIGGER_THRESHOLD == 50
        assert tc_handler.WEEKLY_TRIGGER_THRESHOLD == 10
        assert tc_handler.MIN_TOTAL_SAMPLES == 30
