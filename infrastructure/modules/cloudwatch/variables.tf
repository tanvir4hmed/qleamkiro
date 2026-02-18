variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "alert_email" {
  description = "Email address for CloudWatch alarm notifications"
  type        = string
  default     = ""
}

variable "lambda_function_names" {
  description = "List of Lambda function names to monitor"
  type        = list(string)
  default     = []
}

variable "lambda_error_threshold" {
  description = "Lambda error count threshold for alarm"
  type        = number
  default     = 5
}

variable "lambda_duration_threshold_ms" {
  description = "Lambda p95 duration threshold in milliseconds"
  type        = number
  default     = 25000
}

variable "api_error_threshold" {
  description = "API Gateway 5XX error count threshold for alarm"
  type        = number
  default     = 10
}

variable "sfn_failure_threshold" {
  description = "Step Function failure count threshold for alarm"
  type        = number
  default     = 3
}

variable "state_machine_arn" {
  description = "ARN of the Step Functions state machine to monitor"
  type        = string
}
