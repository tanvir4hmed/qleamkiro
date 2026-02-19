variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution IAM role"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for Lambda VPC config"
  type        = list(string)
}

variable "lambda_security_group_id" {
  description = "Security group ID for Lambda functions"
  type        = string
}

variable "s3_bucket_name" {
  description = "S3 audio bucket name"
  type        = string
}

variable "child_profile_table" {
  description = "DynamoDB ChildProfile table name"
  type        = string
}

variable "session_table" {
  description = "DynamoDB Session table name"
  type        = string
}

variable "sound_cluster_table" {
  description = "DynamoDB SoundCluster table name"
  type        = string
}

variable "semantic_bridge_table" {
  description = "DynamoDB SemanticBridge table name"
  type        = string
}

variable "feedback_table" {
  description = "DynamoDB Feedback table name"
  type        = string
}

variable "alpha_value" {
  description = "EMA alpha value for baseline aggregation"
  type        = number
  default     = 0.3
}

variable "cluster_similarity_threshold" {
  description = "Cosine similarity threshold for cluster assignment"
  type        = number
  default     = 0.85
}

variable "step_function_arn" {
  description = "ARN of the processing Step Function state machine"
  type        = string
  default     = ""
}

variable "bedrock_model_id" {
  description = "Amazon Bedrock model ID for insight generation"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "use_bedrock" {
  description = "Whether to use Bedrock for insight generation"
  type        = bool
  default     = false
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "tf_state_bucket" {
  description = "S3 bucket used to store large Lambda layer zips (audio processing)"
  type        = string
  default     = "qleam-terraform-state"
}

# Lambda deployment package paths
variable "audio_layer_zip_path" {
  description = "Path to audio processing Lambda layer zip (used only when small enough for direct upload)"
  type        = string
  default     = "../../../lambdas/layers/audio_processing.zip"
}

variable "shared_utils_zip_path" {
  description = "Path to shared utilities Lambda layer zip"
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

variable "allowed_origins" {
  description = "List of allowed CORS origins (CloudFront URLs)"
  type        = list(string)
  default     = []
}
