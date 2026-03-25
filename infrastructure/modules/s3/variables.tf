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
  description = "Number of days before archiving audio to Glacier"
  type        = number
  default     = 90
}

variable "audio_max_retention_days" {
  description = "Number of days before permanent deletion of audio files"
  type        = number
  default     = 365
}

variable "allowed_origins" {
  description = "Allowed CORS origins for frontend uploads"
  type        = list(string)
  default     = ["*"]
}
