variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "bucket_name" {
  description = "Name of the S3 audio storage bucket"
  type        = string
}

variable "audio_retention_days" {
  description = "Number of days to retain raw audio files before deletion"
  type        = number
  default     = 90
}

variable "allowed_origins" {
  description = "Allowed CORS origins for frontend uploads"
  type        = list(string)
  default     = ["*"]
}
