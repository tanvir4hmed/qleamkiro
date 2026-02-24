# =============================================================================
# Module: Lambda - Variables
# =============================================================================

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

variable "concept_graph_table" {
  description = "DynamoDB ConceptGraph table name"
  type        = string
}

variable "milestones_table" {
  description = "DynamoDB Milestones table name"
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
  description = "ARN of the processing Step Function state machine (deprecated - use SSM parameter)"
  type        = string
  default     = ""
}

variable "step_function_arn_param_name" {
  description = "SSM parameter name containing the Step Function ARN (for runtime lookup)"
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

# Container image configuration
variable "ecr_repository_urls" {
  description = "Map of Lambda function names to ECR repository URLs"
  type        = map(string)
}

variable "image_tag" {
  description = "Docker image tag for Lambda container images"
  type        = string
  default     = "latest"
}

variable "allowed_origins" {
  description = "List of allowed CORS origins (CloudFront URLs)"
  type        = list(string)
  default     = []
}