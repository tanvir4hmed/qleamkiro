output "feature_extraction_function_name" {
  description = "Feature extraction Lambda function name"
  value       = aws_lambda_function.feature_extraction.function_name
}

output "feature_extraction_function_arn" {
  description = "Feature extraction Lambda function ARN"
  value       = aws_lambda_function.feature_extraction.arn
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

output "training_check_function_name" {
  description = "Training check Lambda function name"
  value       = aws_lambda_function.training_check.function_name
}

output "training_check_function_arn" {
  description = "Training check Lambda function ARN"
  value       = aws_lambda_function.training_check.arn
}

output "model_trainer_function_name" {
  description = "Model trainer Lambda function name"
  value       = aws_lambda_function.model_trainer.function_name
}

output "model_trainer_function_arn" {
  description = "Model trainer Lambda function ARN"
  value       = aws_lambda_function.model_trainer.arn
}
