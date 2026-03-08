"""
Pytest configuration and shared fixtures for Qleam tests
"""
import os
import pytest
import boto3
from moto import mock_aws

# Set test environment variables before any imports
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("CHILD_PROFILE_TABLE", "test-ChildProfile")
os.environ.setdefault("SESSION_TABLE", "test-Session")
os.environ.setdefault("SOUND_CLUSTER_TABLE", "test-SoundCluster")
os.environ.setdefault("SEMANTIC_BRIDGE_TABLE", "test-SemanticBridge")
os.environ.setdefault("FEEDBACK_TABLE", "test-Feedback")
os.environ.setdefault("S3_BUCKET_NAME", "test-audio-bucket")
os.environ.setdefault("TRAINING_FEATURES_TABLE", "test-TrainingFeatures")
os.environ.setdefault("SAGEMAKER_HUBERT_ENDPOINT", "")


@pytest.fixture
def aws_credentials():
    """Mock AWS credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def dynamodb_tables(aws_credentials):
    """Create all DynamoDB tables for testing."""
    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")

        # ChildProfile (with parent_id-index GSI matching production schema)
        dynamodb.create_table(
            TableName="test-ChildProfile",
            KeySchema=[{"AttributeName": "child_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "child_id", "AttributeType": "S"},
                {"AttributeName": "parent_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "parent_id-index",
                "KeySchema": [{"AttributeName": "parent_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        # Session
        dynamodb.create_table(
            TableName="test-Session",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "child_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "child_id-timestamp-index",
                "KeySchema": [
                    {"AttributeName": "child_id", "KeyType": "HASH"},
                    {"AttributeName": "timestamp", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        # SoundCluster
        dynamodb.create_table(
            TableName="test-SoundCluster",
            KeySchema=[{"AttributeName": "cluster_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "cluster_id", "AttributeType": "S"},
                {"AttributeName": "child_id", "AttributeType": "S"},
                {"AttributeName": "last_updated", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "child_id-last_updated-index",
                "KeySchema": [
                    {"AttributeName": "child_id", "KeyType": "HASH"},
                    {"AttributeName": "last_updated", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        # SemanticBridge
        dynamodb.create_table(
            TableName="test-SemanticBridge",
            KeySchema=[{"AttributeName": "bridge_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "bridge_id", "AttributeType": "S"},
                {"AttributeName": "child_id", "AttributeType": "S"},
                {"AttributeName": "cluster_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "child_id-index",
                    "KeySchema": [{"AttributeName": "child_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "cluster_id-index",
                    "KeySchema": [{"AttributeName": "cluster_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Feedback
        dynamodb.create_table(
            TableName="test-Feedback",
            KeySchema=[{"AttributeName": "feedback_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "feedback_id", "AttributeType": "S"},
                {"AttributeName": "session_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "session_id-created_at-index",
                "KeySchema": [
                    {"AttributeName": "session_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )

        yield dynamodb


@pytest.fixture
def s3_bucket(aws_credentials):
    """Create test S3 bucket."""
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-audio-bucket")
        yield s3


@pytest.fixture
def sample_embedding():
    """Sample 26-dimensional embedding vector (2 * 13 MFCC)."""
    import math
    v = [float(i) / 26.0 for i in range(26)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


@pytest.fixture
def sample_feature_scores():
    return {
        "rhythm": 0.65,
        "repetition": 0.72,
        "emotional_intensity": 0.48,
        "expressive_flow": 0.81,
    }
