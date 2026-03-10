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

output "feedback_table_name" {
  description = "Feedback DynamoDB table name"
  value       = aws_dynamodb_table.feedback.name
}

output "feedback_table_arn" {
  description = "Feedback DynamoDB table ARN"
  value       = aws_dynamodb_table.feedback.arn
}

output "population_model_table_name" {
  description = "PopulationModel DynamoDB table name"
  value       = aws_dynamodb_table.population_model.name
}

output "population_model_table_arn" {
  description = "PopulationModel DynamoDB table ARN"
  value       = aws_dynamodb_table.population_model.arn
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
    child_profile     = aws_dynamodb_table.child_profile.name
    session           = aws_dynamodb_table.session.name
    feedback          = aws_dynamodb_table.feedback.name
    population_model  = aws_dynamodb_table.population_model.name
    model_registry    = aws_dynamodb_table.model_registry.name
    training_features = aws_dynamodb_table.training_features.name
    model_versions    = aws_dynamodb_table.model_versions.name
  }
}
