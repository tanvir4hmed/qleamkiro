variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "cognito_user_pool_arn" {
  description = "ARN of the Cognito User Pool for authorization"
  type        = string
}

variable "api_handler_function_name" {
  description = "Name of the API handler Lambda function"
  type        = string
}

variable "api_handler_invoke_arn" {
  description = "Invoke ARN of the API handler Lambda function"
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}
