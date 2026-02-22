output "frontend_bucket_name" {
  description = "Frontend S3 bucket name"
  value       = aws_s3_bucket.frontend.bucket
}

output "frontend_bucket_arn" {
  description = "Frontend S3 bucket ARN"
  value       = aws_s3_bucket.frontend.arn
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution ID"
  value       = aws_cloudfront_distribution.frontend.id
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_url" {
  description = "Frontend URL (CloudFront)"
  value       = "https://${aws_cloudfront_distribution.frontend.domain_name}"
}

output "custom_domain_url" {
  description = "Frontend URL using custom domain (if configured)"
  value       = var.custom_domain != "" ? "https://${var.custom_domain}" : ""
}

output "primary_domain" {
  description = "Primary domain name for the frontend (custom domain if configured, otherwise CloudFront domain)"
  value       = var.custom_domain != "" ? var.custom_domain : aws_cloudfront_distribution.frontend.domain_name
}
