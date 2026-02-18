project     = "qleam"
environment = "dev"
aws_region  = "us-east-1"

# VPC
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b"]
enable_nat_gateway = true

# DynamoDB
enable_pitr = true

# Cognito
enable_mfa = false

# S3
audio_retention_days = 90

# Lambda
alpha_value                  = 0.3
cluster_similarity_threshold = 0.85
use_bedrock                  = false
bedrock_model_id             = "anthropic.claude-3-haiku-20240307-v1:0"
log_retention_days           = 30

# Monitoring
alert_email                  = ""
lambda_error_threshold       = 5
lambda_duration_threshold_ms = 25000
api_error_threshold          = 10
sfn_failure_threshold        = 3
