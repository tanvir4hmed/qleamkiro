output "endpoint_name" {
  description = "SageMaker HuBERT endpoint name"
  value       = aws_sagemaker_endpoint.hubert.name
}

output "endpoint_arn" {
  description = "SageMaker HuBERT endpoint ARN"
  value       = aws_sagemaker_endpoint.hubert.arn
}

output "models_bucket_name" {
  description = "S3 bucket name for model artifacts"
  value       = aws_s3_bucket.models.id
}

output "models_bucket_arn" {
  description = "S3 bucket ARN for model artifacts"
  value       = aws_s3_bucket.models.arn
}
