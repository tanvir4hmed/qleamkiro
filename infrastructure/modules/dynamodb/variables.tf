variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "enable_pitr" {
  description = "Enable Point-In-Time Recovery for DynamoDB tables"
  type        = bool
  default     = true
}
