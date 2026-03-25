# =============================================================================
# Module: DynamoDB
# All Qleam data tables: ChildProfile, Session, Feedback, TrainingFeatures, ModelVersions
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

  attribute {
    name = "parent_id"
    type = "S"
  }

  global_secondary_index {
    name            = "parent_id-index"
    hash_key        = "parent_id"
    projection_type = "ALL"
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

# -----------------------------------------------------------------------------
# TrainingFeatures Table
# HuBERT embedding metadata for each processed baby sound session
# PK: feature_id
# GSI: sound_type-age_days-index (query by emotion + age for training)
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "training_features" {
  name         = "${var.project}-${var.environment}-TrainingFeatures"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "feature_id"

  attribute {
    name = "feature_id"
    type = "S"
  }

  attribute {
    name = "sound_type"
    type = "S"
  }

  attribute {
    name = "age_days"
    type = "N"
  }

  global_secondary_index {
    name            = "sound_type-age_days-index"
    hash_key        = "sound_type"
    range_key       = "age_days"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-TrainingFeatures"
    Table = "TrainingFeatures"
  }
}

# -----------------------------------------------------------------------------
# ModelVersions Table
# Tracks trained model versions for emotion classifier (Phase 3)
# PK: model_type (e.g. "emotion_classifier"), SK: version (number)
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "model_versions" {
  name         = "${var.project}-${var.environment}-ModelVersions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_type"
  range_key    = "version"

  attribute {
    name = "model_type"
    type = "S"
  }

  attribute {
    name = "version"
    type = "N"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-ModelVersions"
    Table = "ModelVersions"
  }
}
