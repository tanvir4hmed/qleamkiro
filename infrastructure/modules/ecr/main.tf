# =============================================================================
# Module: ECR
# Elastic Container Registry for Lambda container images
# =============================================================================

resource "aws_ecr_repository" "lambda" {
  for_each = var.lambda_functions

  name                 = "${var.project}-${var.environment}-${each.key}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name      = "${var.project}-${var.environment}-${each.key}"
    Project   = var.project
    Component = "ecr"
  }
}

# Lifecycle policy to keep only last 10 images
resource "aws_ecr_lifecycle_policy" "lambda" {
  for_each = aws_ecr_repository.lambda

  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Keep only last 10 images"
        selection = {
          tagStatus     = "any"
          countType     = "imageCountMoreThan"
          countNumber   = 10
        }
        action = {
          type = "expire"
        }
      }
    ]
  })
}