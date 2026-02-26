output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = module.api_gateway.api_endpoint
}

output "frontend_url" {
  description = "Frontend CloudFront URL"
  value       = module.frontend.frontend_url
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID for cache invalidation"
  value       = module.frontend.cloudfront_distribution_id
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito App Client ID"
  value       = module.cognito.client_id
}

output "audio_bucket_name" {
  description = "Audio S3 bucket name"
  value       = module.s3.bucket_name
}

output "cloudwatch_dashboard" {
  description = "CloudWatch dashboard name"
  value       = module.cloudwatch.dashboard_name
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = module.step_functions.state_machine_arn
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "ecr_repository_urls" {
  description = "ECR repository URLs for Lambda container images"
  value       = module.ecr.repository_urls
}
