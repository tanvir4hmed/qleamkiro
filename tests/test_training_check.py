"""Tests for lambdas/training_check/handler.py — tests the core logic functions."""
import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "training_check"))


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

        from handler import _count_samples
        total, since_last = _count_samples(table)
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

        from handler import _count_samples
        total, since_last = _count_samples(table)
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

        from handler import _count_samples
        total, since_last = _count_samples(table)
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

        from handler import _count_samples
        total, since_last = _count_samples(table)
        assert total == 5
        assert since_last == 5


class TestTrainingCheckThresholds:
    """Test the threshold constants are reasonable."""

    def test_thresholds_exist(self):
        from handler import BATCH_TRIGGER_THRESHOLD, WEEKLY_TRIGGER_THRESHOLD, MIN_TOTAL_SAMPLES
        assert BATCH_TRIGGER_THRESHOLD == 50
        assert WEEKLY_TRIGGER_THRESHOLD == 10
        assert MIN_TOTAL_SAMPLES == 30
