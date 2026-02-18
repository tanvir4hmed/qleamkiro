# =============================================================================
# Qleam — PROD Environment Variables
# =============================================================================

variable "project" {
  description = "Project name"
  type        = string
  default     = "qleam"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

# VPC
variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.1.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "enable_nat_gateway" {
  description = "Enable NAT gateway for private subnets"
  type        = bool
  default     = true
}

# DynamoDB
variable "enable_pitr" {
  description = "Enable Point-in-Time Recovery for DynamoDB"
  type        = bool
  default     = true
}

# Cognito
variable "enable_mfa" {
  description = "Enable MFA for Cognito"
  type        = bool
  default     = true
}

# S3
variable "audio_retention_days" {
  description = "Days to retain audio files in S3"
  type        = number
  default     = 180
}

# Lambda
variable "alpha_value" {
  description = "EMA smoothing factor for baseline updates"
  type        = number
  default     = 0.3
}

variable "cluster_similarity_threshold" {
  description = "Cosine similarity threshold for cluster assignment"
  type        = number
  default     = 0.85
}

variable "use_bedrock" {
  description = "Use Amazon Bedrock for insight generation"
  type        = bool
  default     = true
}

variable "bedrock_model_id" {
  description = "Bedrock model ID"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 90
}

# Lambda artifact paths (set by CI/CD)
variable "audio_layer_zip_path" {
  description = "Path to audio processing Lambda layer zip"
  type        = string
  default     = "../../../lambdas/layers/audio_processing.zip"
}

variable "shared_utils_zip_path" {
  description = "Path to shared utils Lambda layer zip"
  type        = string
  default     = "../../../lambdas/layers/shared_utils.zip"
}

variable "feature_extraction_zip_path" {
  description = "Path to feature extraction Lambda zip"
  type        = string
  default     = "../../../lambdas/feature_extraction/dist/feature_extraction.zip"
}

variable "cluster_engine_zip_path" {
  description = "Path to cluster engine Lambda zip"
  type        = string
  default     = "../../../lambdas/cluster_engine/dist/cluster_engine.zip"
}

variable "reinforcement_engine_zip_path" {
  description = "Path to reinforcement engine Lambda zip"
  type        = string
  default     = "../../../lambdas/reinforcement_engine/dist/reinforcement_engine.zip"
}

variable "insight_generator_zip_path" {
  description = "Path to insight generator Lambda zip"
  type        = string
  default     = "../../../lambdas/insight_generator/dist/insight_generator.zip"
}

variable "feedback_processor_zip_path" {
  description = "Path to feedback processor Lambda zip"
  type        = string
  default     = "../../../lambdas/feedback_processor/dist/feedback_processor.zip"
}

variable "api_handler_zip_path" {
  description = "Path to API handler Lambda zip"
  type        = string
  default     = "../../../lambdas/api_handler/dist/api_handler.zip"
}

# Monitoring
variable "alert_email" {
  description = "Email address for CloudWatch alerts"
  type        = string
  default     = "alerts@qleam.io"
}

variable "lambda_error_threshold" {
  description = "Lambda error count threshold for alarm"
  type        = number
  default     = 3
}

variable "lambda_duration_threshold_ms" {
  description = "Lambda duration threshold in milliseconds for alarm"
  type        = number
  default     = 20000
}

variable "api_error_threshold" {
  description = "API Gateway 5xx error threshold for alarm"
  type        = number
  default     = 5
}

variable "sfn_failure_threshold" {
  description = "Step Function failure threshold for alarm"
  type        = number
  default     = 1
}
