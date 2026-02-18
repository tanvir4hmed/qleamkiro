variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "step_functions_role_arn" {
  description = "IAM role ARN for Step Functions execution"
  type        = string
}

variable "feature_extraction_lambda_arn" {
  description = "ARN of the feature extraction Lambda"
  type        = string
}

variable "cluster_engine_lambda_arn" {
  description = "ARN of the cluster engine Lambda"
  type        = string
}

variable "insight_generator_lambda_arn" {
  description = "ARN of the insight generator Lambda"
  type        = string
}

variable "audio_bucket_name" {
  description = "S3 audio bucket name (for EventBridge trigger)"
  type        = string
}

variable "eventbridge_role_arn" {
  description = "IAM role ARN for EventBridge to trigger Step Functions"
  type        = string
  default     = ""
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}
