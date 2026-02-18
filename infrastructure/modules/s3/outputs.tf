output "bucket_name" {
  description = "Name of the audio S3 bucket"
  value       = aws_s3_bucket.audio.bucket
}

output "bucket_arn" {
  description = "ARN of the audio S3 bucket"
  value       = aws_s3_bucket.audio.arn
}

output "bucket_regional_domain_name" {
  description = "Regional domain name of the audio S3 bucket"
  value       = aws_s3_bucket.audio.bucket_regional_domain_name
}
