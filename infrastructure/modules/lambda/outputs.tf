output "feature_extraction_function_name" {
  description = "Feature extraction Lambda function name"
  value       = aws_lambda_function.feature_extraction.function_name
}

output "feature_extraction_function_arn" {
  description = "Feature extraction Lambda function ARN"
  value       = aws_lambda_function.feature_extraction.arn
}

output "cluster_engine_function_name" {
  description = "Cluster engine Lambda function name"
  value       = aws_lambda_function.cluster_engine.function_name
}

output "cluster_engine_function_arn" {
  description = "Cluster engine Lambda function ARN"
  value       = aws_lambda_function.cluster_engine.arn
}

output "reinforcement_engine_function_name" {
  description = "Reinforcement engine Lambda function name"
  value       = aws_lambda_function.reinforcement_engine.function_name
}

output "reinforcement_engine_function_arn" {
  description = "Reinforcement engine Lambda function ARN"
  value       = aws_lambda_function.reinforcement_engine.arn
}

output "insight_generator_function_name" {
  description = "Insight generator Lambda function name"
  value       = aws_lambda_function.insight_generator.function_name
}

output "insight_generator_function_arn" {
  description = "Insight generator Lambda function ARN"
  value       = aws_lambda_function.insight_generator.arn
}

output "feedback_processor_function_name" {
  description = "Feedback processor Lambda function name"
  value       = aws_lambda_function.feedback_processor.function_name
}

output "feedback_processor_function_arn" {
  description = "Feedback processor Lambda function ARN"
  value       = aws_lambda_function.feedback_processor.arn
}

output "api_handler_function_name" {
  description = "API handler Lambda function name"
  value       = aws_lambda_function.api_handler.function_name
}

output "api_handler_function_arn" {
  description = "API handler Lambda function ARN"
  value       = aws_lambda_function.api_handler.arn
}

output "api_handler_invoke_arn" {
  description = "API handler Lambda invoke ARN (for API Gateway)"
  value       = aws_lambda_function.api_handler.invoke_arn
}
