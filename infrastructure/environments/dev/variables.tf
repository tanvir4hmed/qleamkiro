variable "project" {
  description = "Project name"
  type        = string
  default     = "qleam"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
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
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
}

variable "enable_nat_gateway" {
  description = "Enable NAT Gateway"
  type        = bool
  default     = true
}

# DynamoDB
variable "enable_pitr" {
  description = "Enable Point-In-Time Recovery"
  type        = bool
  default     = true
}

# Cognito
variable "enable_mfa" {
  description = "Enable MFA"
  type        = bool
  default     = false
}

# S3
variable "audio_retention_days" {
  description = "Days to retain raw audio"
  type        = number
  default     = 90
}

# Lambda config
variable "alpha_value" {
  description = "EMA alpha value"
  type        = number
  default     = 0.3
}

variable "cluster_similarity_threshold" {
  description = "Cosine similarity threshold"
  type        = number
  default     = 0.85
}

variable "use_bedrock" {
  description = "Use Amazon Bedrock for insights"
  type        = bool
  default     = false
}

variable "bedrock_model_id" {
  description = "Bedrock model ID"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "log_retention_days" {
  description = "CloudWatch log retention days"
  type        = number
  default     = 30
}

# Monitoring
variable "alert_email" {
  description = "Alert email address"
  type        = string
  default     = ""
}

variable "lambda_error_threshold" {
  description = "Lambda error alarm threshold"
  type        = number
  default     = 5
}

variable "lambda_duration_threshold_ms" {
  description = "Lambda duration alarm threshold (ms)"
  type        = number
  default     = 25000
}

variable "api_error_threshold" {
  description = "API 5XX error alarm threshold"
  type        = number
  default     = 10
}

variable "sfn_failure_threshold" {
  description = "Step Function failure alarm threshold"
  type        = number
  default     = 3
}

# Lambda package paths
variable "audio_layer_zip_path" {
  description = "Path to audio processing layer zip"
  type        = string
  default     = "../../../lambdas/layers/audio_processing.zip"
}

variable "shared_utils_zip_path" {
  description = "Path to shared utils layer zip"
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

# Lambda container image configuration
variable "lambda_image_tag" {
  description = "Docker image tag for Lambda container images"
  type        = string
  default     = "latest"
}

# Domain Configuration
variable "custom_domain" {
  description = "Custom domain for the application (e.g., dev.ai.qleam.com)"
  type        = string
  default     = ""
}

variable "additional_allowed_origins" {
  description = "Additional CORS allowed origins (e.g., ['https://dev.ai.qleam.com'])"
  type        = list(string)
  default     = []
}

variable "additional_callback_urls" {
  description = "Additional Cognito callback URLs"
  type        = list(string)
  default     = []
}

variable "additional_logout_urls" {
  description = "Additional Cognito logout URLs"
  type        = list(string)
  default     = []
}
