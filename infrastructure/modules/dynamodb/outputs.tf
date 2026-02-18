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

output "all_table_names" {
  description = "Map of all DynamoDB table names"
  value = {
    child_profile  = aws_dynamodb_table.child_profile.name
    session        = aws_dynamodb_table.session.name
    sound_cluster  = aws_dynamodb_table.sound_cluster.name
    semantic_bridge = aws_dynamodb_table.semantic_bridge.name
    feedback       = aws_dynamodb_table.feedback.name
  }
}
