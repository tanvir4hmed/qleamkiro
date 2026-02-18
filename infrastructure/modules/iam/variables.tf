variable "project" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
}

variable "audio_bucket_name" {
  description = "Name of the S3 audio storage bucket"
  type        = string
}
