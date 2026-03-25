# =============================================================================
# Module: S3
# Encrypted audio storage bucket with lifecycle rules
# =============================================================================

resource "aws_s3_bucket" "audio" {
  bucket = var.bucket_name

  tags = {
    Name    = var.bucket_name
    Purpose = "audio-storage"
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "audio" {
  bucket                  = aws_s3_bucket.audio.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Server-side encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Versioning
resource "aws_s3_bucket_versioning" "audio" {
  bucket = aws_s3_bucket.audio.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Lifecycle rules — Glacier archive + auto-delete (GDPR/COPPA belt-and-suspenders)
resource "aws_s3_bucket_lifecycle_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  rule {
    id     = "archive-and-delete-audio"
    status = "Enabled"

    filter {
      prefix = ""
    }

    # Move to Glacier after retention period (default 90 days)
    transition {
      days          = var.audio_retention_days
      storage_class = "GLACIER"
    }

    # Permanent deletion after max retention (default 365 days)
    expiration {
      days = var.audio_max_retention_days
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

# CORS configuration for frontend uploads
resource "aws_s3_bucket_cors_configuration" "audio" {
  bucket = aws_s3_bucket.audio.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

# Bucket policy — enforce TLS only
resource "aws_s3_bucket_policy" "audio" {
  bucket = aws_s3_bucket.audio.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyNonTLS"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource = [
          "${aws_s3_bucket.audio.arn}",
          "${aws_s3_bucket.audio.arn}/*"
        ]
        Condition = {
          Bool = {
            "aws:SecureTransport" = "false"
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.audio]
}

# S3 notification to trigger Step Functions via EventBridge
resource "aws_s3_bucket_notification" "audio_upload" {
  bucket      = aws_s3_bucket.audio.id
  eventbridge = true
}
