variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "frontend_bucket_name" {
  description = "S3 bucket name for frontend assets"
  type        = string
}
