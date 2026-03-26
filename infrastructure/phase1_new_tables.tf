# Phase 1: New DynamoDB Tables for QLEAM Evolution
# These tables support the daily-age precision and individual baby tracking features
#
# USAGE: Add these resources to infrastructure/modules/dynamodb/main.tf
# or deploy as a separate module with proper variable declarations.

# =============================================================================
# Variables (declare these if using as standalone module)
# =============================================================================
variable "project" {
  description = "Project name"
  type        = string
  default     = "qleam"
}

variable "environment" {
  description = "Environment name (dev/prod)"
  type        = string
  default     = "dev"
}

variable "enable_pitr" {
  description = "Enable Point-In-Time Recovery for DynamoDB tables"
  type        = bool
  default     = true
}

# =============================================================================
# BabyDailyAtlas Table
# Stores population-level acoustic feature distributions per age-day
# =============================================================================
resource "aws_dynamodb_table" "baby_daily_atlas" {
  name           = "${var.project}-${var.environment}-BabyDailyAtlas"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "age_day"
  range_key      = "feature_key"

  attribute {
    name = "age_day"
    type = "N"
  }

  attribute {
    name = "feature_key"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${var.project}-${var.environment}-BabyDailyAtlas"
    Environment = var.environment
    Table       = "BabyDailyAtlas"
    Purpose     = "Population acoustic feature distributions per age-day"
  }
}

# =============================================================================
# BabyTrajectory Table
# Stores individual baby's acoustic history and personal baseline
# =============================================================================
resource "aws_dynamodb_table" "baby_trajectory" {
  name           = "${var.project}-${var.environment}-BabyTrajectory"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "child_id"
  range_key      = "session_date"

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "session_date"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name        = "${var.project}-${var.environment}-BabyTrajectory"
    Environment = var.environment
    Table       = "BabyTrajectory"
    Purpose     = "Individual baby acoustic history and trajectory"
  }
}

# =============================================================================
# Outputs
# =============================================================================
output "baby_daily_atlas_table_name" {
  value       = aws_dynamodb_table.baby_daily_atlas.name
  description = "BabyDailyAtlas table name"
}

output "baby_daily_atlas_table_arn" {
  value       = aws_dynamodb_table.baby_daily_atlas.arn
  description = "BabyDailyAtlas table ARN"
}

output "baby_trajectory_table_name" {
  value       = aws_dynamodb_table.baby_trajectory.name
  description = "BabyTrajectory table name"
}

output "baby_trajectory_table_arn" {
  value       = aws_dynamodb_table.baby_trajectory.arn
  description = "BabyTrajectory table ARN"
}
