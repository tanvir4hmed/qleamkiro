output "endpoint_name" {
  description = "SageMaker HuBERT endpoint name (empty if disabled)"
  value       = var.enabled ? aws_sagemaker_endpoint.hubert[0].name : ""
}

output "endpoint_arn" {
  description = "SageMaker HuBERT endpoint ARN (empty if disabled)"
  value       = var.enabled ? aws_sagemaker_endpoint.hubert[0].arn : ""
}

output "models_bucket_name" {
  description = "S3 bucket name for model artifacts"
  value       = local.models_bucket_name
}

output "models_bucket_arn" {
  description = "S3 bucket ARN for model artifacts"
  value       = local.models_bucket_arn
}
