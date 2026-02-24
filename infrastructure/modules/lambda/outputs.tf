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

output "nlp_processor_function_name" {
  description = "NLP processor Lambda function name"
  value       = aws_lambda_function.nlp_processor.function_name
}

output "nlp_processor_function_arn" {
  description = "NLP processor Lambda function ARN"
  value       = aws_lambda_function.nlp_processor.arn
}

output "developmental_tracker_function_name" {
  description = "Developmental tracker Lambda function name"
  value       = aws_lambda_function.developmental_tracker.function_name
}

output "developmental_tracker_function_arn" {
  description = "Developmental tracker Lambda function ARN"
  value       = aws_lambda_function.developmental_tracker.arn
}

output "concept_decoder_function_name" {
  description = "Concept decoder Lambda function name"
  value       = aws_lambda_function.concept_decoder.function_name
}

output "concept_decoder_function_arn" {
  description = "Concept decoder Lambda function ARN"
  value       = aws_lambda_function.concept_decoder.arn
}

output "speech_analyzer_function_name" {
  description = "Speech analyzer Lambda function name"
  value       = aws_lambda_function.speech_analyzer.function_name
}

output "speech_analyzer_function_arn" {
  description = "Speech analyzer Lambda function ARN"
  value       = aws_lambda_function.speech_analyzer.arn
}
