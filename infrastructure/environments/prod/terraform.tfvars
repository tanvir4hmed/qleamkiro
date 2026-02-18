project     = "qleam"
environment = "prod"
aws_region  = "us-east-1"

# VPC
vpc_cidr           = "10.1.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]
enable_nat_gateway = true

# DynamoDB
enable_pitr = true

# Cognito
enable_mfa = true

# S3
audio_retention_days = 180

# Lambda
alpha_value                  = 0.3
cluster_similarity_threshold = 0.85
use_bedrock                  = true
bedrock_model_id             = "anthropic.claude-3-haiku-20240307-v1:0"
log_retention_days           = 90

# Monitoring
alert_email                  = "alerts@qleam.io"
lambda_error_threshold       = 3
lambda_duration_threshold_ms = 20000
api_error_threshold          = 5
sfn_failure_threshold        = 1
