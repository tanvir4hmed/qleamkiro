# =============================================================================
# Module: IAM
# Least-privilege roles for Lambda, Step Functions, Cognito
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# -----------------------------------------------------------------------------
# Lambda Execution Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "lambda_execution" {
  name = "${var.project}-${var.environment}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project}-${var.environment}-lambda-execution-role"
  }
}

# Lambda basic execution (CloudWatch Logs)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Lambda VPC access
resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Lambda S3 access (specific bucket only)
resource "aws_iam_policy" "lambda_s3" {
  name        = "${var.project}-${var.environment}-lambda-s3-policy"
  description = "Allow Lambda to read/write audio S3 bucket"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:HeadObject"
        ]
        Resource = "arn:aws:s3:::${var.audio_bucket_name}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket"
        ]
        Resource = "arn:aws:s3:::${var.audio_bucket_name}"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_s3" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_s3.arn
}

# Lambda DynamoDB access (specific tables only)
resource "aws_iam_policy" "lambda_dynamodb" {
  name        = "${var.project}-${var.environment}-lambda-dynamodb-policy"
  description = "Allow Lambda to read/write DynamoDB tables"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.project}-${var.environment}-*",
          "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.project}-${var.environment}-*/index/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_dynamodb" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_dynamodb.arn
}

# Lambda Step Functions (to start executions from API trigger)
resource "aws_iam_policy" "lambda_stepfunctions" {
  name        = "${var.project}-${var.environment}-lambda-sfn-policy"
  description = "Allow Lambda to start Step Function executions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "states:StartExecution"
        ]
        Resource = "arn:aws:states:${local.region}:${local.account_id}:stateMachine:${var.project}-${var.environment}-*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_stepfunctions" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_stepfunctions.arn
}

# Lambda Bedrock access (for insight generation)
resource "aws_iam_policy" "lambda_bedrock" {
  name        = "${var.project}-${var.environment}-lambda-bedrock-policy"
  description = "Allow Lambda to invoke Bedrock models"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "arn:aws:bedrock:${local.region}::foundation-model/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_bedrock.arn
}

# Lambda SSM Parameter Store access (for Step Function ARN lookup)
resource "aws_iam_policy" "lambda_ssm" {
  name        = "${var.project}-${var.environment}-lambda-ssm-policy"
  description = "Allow Lambda to read SSM parameters"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters",
          "ssm:GetParametersByPath"
        ]
        Resource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter/${var.project}/${var.environment}/*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_ssm" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.lambda_ssm.arn
}

# -----------------------------------------------------------------------------
# Step Functions Execution Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "step_functions" {
  name = "${var.project}-${var.environment}-stepfunctions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project}-${var.environment}-stepfunctions-role"
  }
}

resource "aws_iam_policy" "step_functions_lambda" {
  name        = "${var.project}-${var.environment}-sfn-lambda-policy"
  description = "Allow Step Functions to invoke Lambda functions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:${local.region}:${local.account_id}:function:${var.project}-${var.environment}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "step_functions_lambda" {
  role       = aws_iam_role.step_functions.name
  policy_arn = aws_iam_policy.step_functions_lambda.arn
}

# -----------------------------------------------------------------------------
# API Gateway CloudWatch Logging Role
# -----------------------------------------------------------------------------
resource "aws_iam_role" "api_gateway_cloudwatch" {
  name = "${var.project}-${var.environment}-apigw-cloudwatch-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "apigateway.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "api_gateway_cloudwatch" {
  role       = aws_iam_role.api_gateway_cloudwatch.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonAPIGatewayPushToCloudWatchLogs"
}

resource "aws_api_gateway_account" "main" {
  cloudwatch_role_arn = aws_iam_role.api_gateway_cloudwatch.arn
}
