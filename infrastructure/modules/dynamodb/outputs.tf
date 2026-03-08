output "child_profile_table_name" {
  description = "ChildProfile DynamoDB table name"
  value       = aws_dynamodb_table.child_profile.name
}

output "child_profile_table_arn" {
  description = "ChildProfile DynamoDB table ARN"
  value       = aws_dynamodb_table.child_profile.arn
}

output "session_table_name" {
  description = "Session DynamoDB table name"
  value       = aws_dynamodb_table.session.name
}

output "session_table_arn" {
  description = "Session DynamoDB table ARN"
  value       = aws_dynamodb_table.session.arn
}

output "sound_cluster_table_name" {
  description = "SoundCluster DynamoDB table name"
  value       = aws_dynamodb_table.sound_cluster.name
}

output "sound_cluster_table_arn" {
  description = "SoundCluster DynamoDB table ARN"
  value       = aws_dynamodb_table.sound_cluster.arn
}

output "semantic_bridge_table_name" {
  description = "SemanticBridge DynamoDB table name"
  value       = aws_dynamodb_table.semantic_bridge.name
}

output "semantic_bridge_table_arn" {
  description = "SemanticBridge DynamoDB table ARN"
  value       = aws_dynamodb_table.semantic_bridge.arn
}

output "feedback_table_name" {
  description = "Feedback DynamoDB table name"
  value       = aws_dynamodb_table.feedback.name
}

output "feedback_table_arn" {
  description = "Feedback DynamoDB table ARN"
  value       = aws_dynamodb_table.feedback.arn
}

output "concept_graph_table_name" {
  description = "ConceptGraph DynamoDB table name"
  value       = aws_dynamodb_table.concept_graph.name
}

output "concept_graph_table_arn" {
  description = "ConceptGraph DynamoDB table ARN"
  value       = aws_dynamodb_table.concept_graph.arn
}

output "milestones_table_name" {
  description = "Milestones DynamoDB table name"
  value       = aws_dynamodb_table.milestones.name
}

output "milestones_table_arn" {
  description = "Milestones DynamoDB table ARN"
  value       = aws_dynamodb_table.milestones.arn
}

output "population_model_table_name" {
  description = "PopulationModel DynamoDB table name"
  value       = aws_dynamodb_table.population_model.name
}

output "population_model_table_arn" {
  description = "PopulationModel DynamoDB table ARN"
  value       = aws_dynamodb_table.population_model.arn
}

output "training_candidate_table_name" {
  description = "TrainingCandidate DynamoDB table name"
  value       = aws_dynamodb_table.training_candidate.name
}

output "training_candidate_table_arn" {
  description = "TrainingCandidate DynamoDB table ARN"
  value       = aws_dynamodb_table.training_candidate.arn
}

output "model_registry_table_name" {
  description = "ModelRegistry DynamoDB table name"
  value       = aws_dynamodb_table.model_registry.name
}

output "model_registry_table_arn" {
  description = "ModelRegistry DynamoDB table ARN"
  value       = aws_dynamodb_table.model_registry.arn
}

output "training_features_table_name" {
  description = "TrainingFeatures DynamoDB table name"
  value       = aws_dynamodb_table.training_features.name
}

output "training_features_table_arn" {
  description = "TrainingFeatures DynamoDB table ARN"
  value       = aws_dynamodb_table.training_features.arn
}

output "model_versions_table_name" {
  description = "ModelVersions DynamoDB table name"
  value       = aws_dynamodb_table.model_versions.name
}

output "model_versions_table_arn" {
  description = "ModelVersions DynamoDB table ARN"
  value       = aws_dynamodb_table.model_versions.arn
}

output "all_table_names" {
  description = "Map of all DynamoDB table names"
  value = {
    child_profile      = aws_dynamodb_table.child_profile.name
    session            = aws_dynamodb_table.session.name
    sound_cluster      = aws_dynamodb_table.sound_cluster.name
    semantic_bridge    = aws_dynamodb_table.semantic_bridge.name
    feedback           = aws_dynamodb_table.feedback.name
    concept_graph      = aws_dynamodb_table.concept_graph.name
    milestones         = aws_dynamodb_table.milestones.name
    population_model   = aws_dynamodb_table.population_model.name
    training_candidate = aws_dynamodb_table.training_candidate.name
    model_registry     = aws_dynamodb_table.model_registry.name
    training_features  = aws_dynamodb_table.training_features.name
    model_versions     = aws_dynamodb_table.model_versions.name
  }
}
