project     = "qleam"
environment = "dev"
aws_region  = "us-east-1"

# VPC
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a"]
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
use_bedrock                  = true
use_sagemaker_intent_endpoint = false  # Set to true to activate SageMaker HuBERT (paid per call)
bedrock_model_id             = "anthropic.claude-3-haiku-20240307-v1:0"
use_transcribe_for_linguistic = true
transcribe_timeout_seconds    = 25
log_retention_days           = 30

# Monitoring
alert_email                  = ""
lambda_error_threshold       = 5
lambda_duration_threshold_ms = 25000
api_error_threshold          = 10
sfn_failure_threshold        = 3

# Domain Configuration
# Set custom_domain and acm_certificate_arn to enable custom domain for CloudFront
# Leave empty if certificate doesn't exist - it will use default CloudFront domain
custom_domain              = "ai.qleam.com"
acm_certificate_arn        = "arn:aws:acm:us-east-1:552794253321:certificate/cd25c78a-320a-4cff-b6a1-6a47b96d2532"

additional_allowed_origins = []
additional_callback_urls   = []
additional_logout_urls     = []
