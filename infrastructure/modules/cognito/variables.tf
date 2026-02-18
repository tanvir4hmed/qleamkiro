variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "enable_mfa" {
  description = "Enable MFA for Cognito User Pool"
  type        = bool
  default     = false
}

variable "callback_urls" {
  description = "OAuth callback URLs for the app client"
  type        = list(string)
  default     = ["http://localhost:3000/callback"]
}

variable "logout_urls" {
  description = "OAuth logout URLs for the app client"
  type        = list(string)
  default     = ["http://localhost:3000/logout"]
}

variable "cognito_auth_role_arn" {
  description = "IAM role ARN for authenticated Cognito identity pool users"
  type        = string
}
