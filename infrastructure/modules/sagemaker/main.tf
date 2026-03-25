# =============================================================================
# Module: SageMaker
# HuBERT feature extraction endpoint (Serverless Inference)
# Set enabled = false to skip all SageMaker resources (saves cost)
# =============================================================================

# -----------------------------------------------------------------------------
# S3 bucket for model artifacts is created MANUALLY (outside Terraform)
# so it survives `terraform destroy`. Bucket: ${var.project}-${var.environment}-models
# -----------------------------------------------------------------------------
locals {
  models_bucket_name = "${var.project}-${var.environment}-models"
  models_bucket_arn  = "arn:aws:s3:::${var.project}-${var.environment}-models"
}

# -----------------------------------------------------------------------------
# IAM Role for SageMaker
# -----------------------------------------------------------------------------
resource "aws_iam_role" "sagemaker" {
  count = var.enabled ? 1 : 0
  name  = "${var.project}-${var.environment}-sagemaker-hubert-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "sagemaker.amazonaws.com"
      }
    }]
  })

  tags = {
    Name = "${var.project}-${var.environment}-sagemaker-hubert-role"
  }
}

resource "aws_iam_role_policy" "sagemaker_s3" {
  count = var.enabled ? 1 : 0
  name  = "${var.project}-${var.environment}-sagemaker-s3-policy"
  role  = aws_iam_role.sagemaker[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          local.models_bucket_arn,
          "${local.models_bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "sagemaker_ecr" {
  count = var.enabled ? 1 : 0
  name  = "${var.project}-${var.environment}-sagemaker-ecr-policy"
  role  = aws_iam_role.sagemaker[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:GetAuthorizationToken"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy" "sagemaker_cloudwatch" {
  count = var.enabled ? 1 : 0
  name  = "${var.project}-${var.environment}-sagemaker-cw-policy"
  role  = aws_iam_role.sagemaker[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData",
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams"
        ]
        Resource = "*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# SageMaker Model — HuBERT Base (HuggingFace container)
# -----------------------------------------------------------------------------
resource "aws_sagemaker_model" "hubert" {
  count              = var.enabled ? 1 : 0
  name               = "${var.project}-${var.environment}-hubert"
  execution_role_arn = aws_iam_role.sagemaker[0].arn

  primary_container {
    # HuggingFace PyTorch Inference container (CPU)
    image          = var.huggingface_inference_image
    model_data_url = "s3://${local.models_bucket_name}/hubert/model.tar.gz"
    environment = {
      HF_MODEL_ID                    = "facebook/hubert-base-ls960"
      HF_TASK                        = "feature-extraction"
      SAGEMAKER_CONTAINER_LOG_LEVEL  = "20"
    }
  }

  tags = {
    Name      = "${var.project}-${var.environment}-hubert"
    Component = "sagemaker"
  }
}

# -----------------------------------------------------------------------------
# SageMaker Endpoint Configuration (Serverless — scales to zero)
# -----------------------------------------------------------------------------
resource "aws_sagemaker_endpoint_configuration" "hubert" {
  count = var.enabled ? 1 : 0
  name  = "${var.project}-${var.environment}-hubert-config"

  production_variants {
    variant_name           = "default"
    model_name             = aws_sagemaker_model.hubert[0].name
    initial_variant_weight = 1.0

    serverless_config {
      memory_size_in_mb = var.sagemaker_memory_mb
      max_concurrency   = var.sagemaker_max_concurrency
    }
  }

  tags = {
    Name      = "${var.project}-${var.environment}-hubert-config"
    Component = "sagemaker"
  }
}

# -----------------------------------------------------------------------------
# SageMaker Endpoint
# -----------------------------------------------------------------------------
resource "aws_sagemaker_endpoint" "hubert" {
  count                = var.enabled ? 1 : 0
  name                 = "${var.project}-${var.environment}-hubert-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.hubert[0].name

  tags = {
    Name      = "${var.project}-${var.environment}-hubert-endpoint"
    Component = "sagemaker"
  }
}
