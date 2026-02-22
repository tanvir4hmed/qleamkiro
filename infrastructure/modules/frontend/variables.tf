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

variable "custom_domain" {
  description = "Custom domain name for CloudFront (e.g., ai.qleam.com)"
  type        = string
  default     = ""
}

variable "acm_certificate_arn" {
  description = "ACM certificate ARN for custom domain (must be in us-east-1)"
  type        = string
  default     = ""
}
