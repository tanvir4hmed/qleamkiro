# =============================================================================
# Module: ECR - Outputs
# =============================================================================

output "repository_urls" {
  description = "Map of Lambda function names to ECR repository URLs"
  value       = { for k, v in aws_ecr_repository.lambda : k => v.repository_url }
}

output "repository_arns" {
  description = "Map of Lambda function names to ECR repository ARNs"
  value       = { for k, v in aws_ecr_repository.lambda : k => v.arn }
}