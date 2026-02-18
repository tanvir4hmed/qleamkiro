variable "aws_region" {
  description = "AWS region for global resources"
  type        = string
  default     = "us-east-1"
}

variable "tf_state_bucket_name" {
  description = "S3 bucket name for Terraform remote state"
  type        = string
  default     = "qleam-terraform-state"
}

variable "tf_state_lock_table_name" {
  description = "DynamoDB table name for Terraform state locking"
  type        = string
  default     = "qleam-terraform-state-lock"
}
