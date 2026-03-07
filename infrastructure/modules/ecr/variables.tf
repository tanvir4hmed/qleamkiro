# =============================================================================
# Module: ECR - Variables
# =============================================================================

variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "lambda_functions" {
  description = "Map of Lambda function names to create ECR repos for"
  type        = map(string)
  default = {
    feature_extraction   = "Feature extraction Lambda"
    insight_generator    = "Insight generator Lambda"
    feedback_processor   = "Feedback processor Lambda"
    api_handler          = "API handler Lambda"
  }
}
