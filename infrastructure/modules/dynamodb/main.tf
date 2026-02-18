# =============================================================================
# Module: DynamoDB
# All Qleam data tables: ChildProfile, Session, SoundCluster, SemanticBridge, Feedback
# =============================================================================

# -----------------------------------------------------------------------------
# ChildProfile Table
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "child_profile" {
  name         = "${var.project}-${var.environment}-ChildProfile"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "child_id"

  attribute {
    name = "child_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-ChildProfile"
    Table = "ChildProfile"
  }
}

# -----------------------------------------------------------------------------
# Session Table
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "session" {
  name         = "${var.project}-${var.environment}-Session"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "session_id"

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  global_secondary_index {
    name            = "child_id-timestamp-index"
    hash_key        = "child_id"
    range_key       = "timestamp"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-Session"
    Table = "Session"
  }
}

# -----------------------------------------------------------------------------
# SoundCluster Table
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "sound_cluster" {
  name         = "${var.project}-${var.environment}-SoundCluster"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "cluster_id"

  attribute {
    name = "cluster_id"
    type = "S"
  }

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "last_updated"
    type = "S"
  }

  global_secondary_index {
    name            = "child_id-last_updated-index"
    hash_key        = "child_id"
    range_key       = "last_updated"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-SoundCluster"
    Table = "SoundCluster"
  }
}

# -----------------------------------------------------------------------------
# SemanticBridge Table
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "semantic_bridge" {
  name         = "${var.project}-${var.environment}-SemanticBridge"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "bridge_id"

  attribute {
    name = "bridge_id"
    type = "S"
  }

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "cluster_id"
    type = "S"
  }

  global_secondary_index {
    name            = "child_id-index"
    hash_key        = "child_id"
    projection_type = "ALL"
  }

  global_secondary_index {
    name            = "cluster_id-index"
    hash_key        = "cluster_id"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-SemanticBridge"
    Table = "SemanticBridge"
  }
}

# -----------------------------------------------------------------------------
# Feedback Table
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "feedback" {
  name         = "${var.project}-${var.environment}-Feedback"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "feedback_id"

  attribute {
    name = "feedback_id"
    type = "S"
  }

  attribute {
    name = "session_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "session_id-created_at-index"
    hash_key        = "session_id"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-Feedback"
    Table = "Feedback"
  }
}
