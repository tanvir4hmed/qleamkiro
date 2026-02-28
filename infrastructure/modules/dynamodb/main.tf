# =============================================================================
# Module: DynamoDB
# All Qleam data tables: ChildProfile, Session, SoundCluster, SemanticBridge, Feedback, ConceptGraph
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

# -----------------------------------------------------------------------------
# ConceptGraph Table
# Personal concept graph: maps each child's acoustic clusters to semantic concepts
# PK: child_id, SK: concept_id (enables all-concepts-for-child query)
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "concept_graph" {
  name         = "${var.project}-${var.environment}-ConceptGraph"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "child_id"
  range_key    = "concept_id"

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "concept_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-ConceptGraph"
    Table = "ConceptGraph"
  }
}

# -----------------------------------------------------------------------------
# Milestones Table
# Tracks developmental milestone events per child
# PK: child_id, SK: milestone_id
# GSI: child_id-first_date-index (chronological milestone queries)
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "milestones" {
  name         = "${var.project}-${var.environment}-Milestones"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "child_id"
  range_key    = "milestone_id"

  attribute {
    name = "child_id"
    type = "S"
  }

  attribute {
    name = "milestone_id"
    type = "S"
  }

  attribute {
    name = "first_date"
    type = "S"
  }

  global_secondary_index {
    name            = "child_id-first_date-index"
    hash_key        = "child_id"
    range_key       = "first_date"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-Milestones"
    Table = "Milestones"
  }
}

# -----------------------------------------------------------------------------
# PopulationModel Table
# Stage-level online/federated priors used by insight_generator evidence model
# PK: stage
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "population_model" {
  name         = "${var.project}-${var.environment}-PopulationModel"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "stage"

  attribute {
    name = "stage"
    type = "S"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-PopulationModel"
    Table = "PopulationModel"
  }
}

# -----------------------------------------------------------------------------
# TrainingCandidate Table
# De-identified accepted samples for supervised training dataset construction
# PK: candidate_id
# GSI: developmental_stage-accepted_at-index
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "training_candidate" {
  name         = "${var.project}-${var.environment}-TrainingCandidate"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "candidate_id"

  attribute {
    name = "candidate_id"
    type = "S"
  }

  attribute {
    name = "developmental_stage"
    type = "S"
  }

  attribute {
    name = "accepted_at"
    type = "S"
  }

  global_secondary_index {
    name            = "developmental_stage-accepted_at-index"
    hash_key        = "developmental_stage"
    range_key       = "accepted_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = var.enable_pitr
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name  = "${var.project}-${var.environment}-TrainingCandidate"
    Table = "TrainingCandidate"
  }
}

# -----------------------------------------------------------------------------
# ModelRegistry Table
# Stores stage-level trained acoustic model versions and promotion status
# PK: model_id
# GSI: developmental_stage-created_at-index
# -----------------------------------------------------------------------------
resource "aws_dynamodb_table" "model_registry" {
  name         = "${var.project}-${var.environment}-ModelRegistry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_id"

  attribute {
    name = "model_id"
    type = "S"
  }

  attribute {
    name = "developmental_stage"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "developmental_stage-created_at-index"
    hash_key        = "developmental_stage"
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
    Name  = "${var.project}-${var.environment}-ModelRegistry"
    Table = "ModelRegistry"
  }
}
