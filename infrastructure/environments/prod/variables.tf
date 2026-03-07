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
variable "use_bedrock" {
  description = "Use Amazon Bedrock for insight generation"
  type        = bool
  default     = true
}

variable "use_sagemaker_intent_endpoint" {
  description = "Use SageMaker endpoint override for infant intent acoustic scores"
  type        = bool
  default     = false
}

variable "sagemaker_intent_endpoint_name" {
  description = "SageMaker endpoint name for infant intent model"
  type        = string
  default     = ""
}

variable "use_transcribe_for_linguistic" {
  description = "Use Amazon Transcribe for linguistic-mode transcripts"
  type        = bool
  default     = false
}

variable "transcribe_timeout_seconds" {
  description = "Timeout in seconds for Transcribe polling"
  type        = number
  default     = 25
}

variable "enable_s3_event_trigger" {
  description = "Whether S3 uploads should auto-trigger the Step Functions pipeline"
  type        = bool
  default     = false
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

# Lambda container image configuration
variable "lambda_image_tag" {
  description = "Docker image tag for Lambda container images"
  type        = string
  default     = "latest"
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

# Domain Configuration
variable "custom_domain" {
  description = "Custom domain for the application (e.g., ai.qleam.com)"
  type        = string
  default     = ""
}

variable "additional_allowed_origins" {
  description = "Additional CORS allowed origins (e.g., ['https://ai.qleam.com'])"
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
