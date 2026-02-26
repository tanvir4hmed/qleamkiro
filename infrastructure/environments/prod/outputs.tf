# =============================================================================
# Qleam — PROD Environment Outputs
# =============================================================================

output "api_endpoint" {
  description = "API Gateway endpoint URL"
  value       = module.api_gateway.api_endpoint
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = module.cognito.user_pool_id
}

output "cognito_client_id" {
  description = "Cognito App Client ID"
  value       = module.cognito.client_id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.frontend.cloudfront_domain_name
}

output "audio_bucket_name" {
  description = "S3 audio storage bucket name"
  value       = module.s3.bucket_name
}

output "frontend_bucket_name" {
  description = "S3 frontend bucket name"
  value       = module.frontend.frontend_bucket_name
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN"
  value       = module.step_functions.state_machine_arn
}

output "cloudwatch_dashboard" {
  description = "CloudWatch dashboard name"
  value       = module.cloudwatch.dashboard_name
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}
