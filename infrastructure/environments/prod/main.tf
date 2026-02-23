# =============================================================================
# Qleam — PROD Environment Root
# Composes all modules for the production environment
# =============================================================================

terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
    }
  }

  backend "s3" {
    bucket         = "qleam-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "qleam-terraform-state-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  audio_bucket_name    = "${var.project}-${var.environment}-audio-storage"
  frontend_bucket_name = "${var.project}-${var.environment}-frontend"
  
  # Build allowed origins list
  allowed_origins = concat(
    ["https://${module.frontend.cloudfront_domain_name}"],
    var.additional_allowed_origins
  )
  
  # Build callback URLs for Cognito
  callback_urls = concat(
    ["https://${module.frontend.cloudfront_domain_name}/callback"],
    var.additional_callback_urls
  )
  
  # Build logout URLs for Cognito
  logout_urls = concat(
    ["https://${module.frontend.cloudfront_domain_name}/logout"],
    var.additional_logout_urls
  )
}

# -----------------------------------------------------------------------------
# VPC
# -----------------------------------------------------------------------------
module "vpc" {
  source = "../../modules/vpc"

  project            = var.project
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = var.enable_nat_gateway
}

# -----------------------------------------------------------------------------
# IAM
# -----------------------------------------------------------------------------
module "iam" {
  source = "../../modules/iam"

  project           = var.project
  environment       = var.environment
  audio_bucket_name = local.audio_bucket_name
}

# -----------------------------------------------------------------------------
# ECR (Elastic Container Registry for Lambda images)
# -----------------------------------------------------------------------------
module "ecr" {
  source = "../../modules/ecr"

  project     = var.project
  environment = var.environment
}

# -----------------------------------------------------------------------------
# S3 (Audio Storage)
# -----------------------------------------------------------------------------
module "s3" {
  source = "../../modules/s3"

  project              = var.project
  environment          = var.environment
  bucket_name          = local.audio_bucket_name
  audio_retention_days = var.audio_retention_days
  allowed_origins      = local.allowed_origins
}

# -----------------------------------------------------------------------------
# DynamoDB
# -----------------------------------------------------------------------------
module "dynamodb" {
  source = "../../modules/dynamodb"

  project     = var.project
  environment = var.environment
  enable_pitr = var.enable_pitr
}

# -----------------------------------------------------------------------------
# Frontend (S3 + CloudFront) - Created early for CloudFront domain
# -----------------------------------------------------------------------------
module "frontend" {
  source = "../../modules/frontend"

  project              = var.project
  environment          = var.environment
  frontend_bucket_name = local.frontend_bucket_name
}

# -----------------------------------------------------------------------------
# Cognito
# -----------------------------------------------------------------------------
module "cognito" {
  source = "../../modules/cognito"

  project               = var.project
  environment           = var.environment
  enable_mfa            = var.enable_mfa
  callback_urls         = local.callback_urls
  logout_urls           = local.logout_urls
  cognito_auth_role_arn = module.iam.lambda_execution_role_arn
}

# -----------------------------------------------------------------------------
# Step Functions (created before Lambda so we have the ARN)
# Note: Lambda ARNs are passed as strings with known naming pattern
# -----------------------------------------------------------------------------
module "step_functions" {
  source = "../../modules/step_functions"

  project                       = var.project
  environment                   = var.environment
  step_functions_role_arn       = module.iam.step_functions_role_arn
  feature_extraction_lambda_arn = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project}-${var.environment}-feature-extraction"
  cluster_engine_lambda_arn     = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project}-${var.environment}-cluster-engine"
  insight_generator_lambda_arn  = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project}-${var.environment}-insight-generator"
  audio_bucket_name             = local.audio_bucket_name
  log_retention_days            = var.log_retention_days

  depends_on = [module.iam]
}

# -----------------------------------------------------------------------------
# Lambda Functions (Container Images from ECR)
# -----------------------------------------------------------------------------
module "lambda" {
  source = "../../modules/lambda"

  project                   = var.project
  environment               = var.environment
  lambda_execution_role_arn = module.iam.lambda_execution_role_arn
  private_subnet_ids        = module.vpc.private_subnet_ids
  lambda_security_group_id  = module.vpc.lambda_security_group_id

  s3_bucket_name        = local.audio_bucket_name
  child_profile_table   = module.dynamodb.child_profile_table_name
  session_table         = module.dynamodb.session_table_name
  sound_cluster_table   = module.dynamodb.sound_cluster_table_name
  semantic_bridge_table = module.dynamodb.semantic_bridge_table_name
  feedback_table        = module.dynamodb.feedback_table_name

  alpha_value                  = var.alpha_value
  cluster_similarity_threshold = var.cluster_similarity_threshold
  step_function_arn            = module.step_functions.state_machine_arn
  step_function_arn_param_name = ""
  use_bedrock                  = var.use_bedrock
  bedrock_model_id             = var.bedrock_model_id
  log_retention_days           = var.log_retention_days

  # ECR configuration
  ecr_repository_urls = module.ecr.repository_urls
  image_tag           = var.lambda_image_tag
  allowed_origins     = local.allowed_origins

  depends_on = [module.vpc, module.iam, module.dynamodb, module.s3, module.ecr, module.step_functions]
}

# -----------------------------------------------------------------------------
# SSM Parameter for Step Function ARN (kept for reference, not used by Lambda)
# -----------------------------------------------------------------------------
resource "aws_ssm_parameter" "step_function_arn" {
  name        = "/${var.project}/${var.environment}/step-function-arn"
  description = "ARN of the audio processing Step Function state machine"
  type        = "String"
  value       = module.step_functions.state_machine_arn

  tags = {
    Name = "${var.project}-${var.environment}-step-function-arn-param"
  }

  depends_on = [module.step_functions]
}

# -----------------------------------------------------------------------------
# API Gateway
# -----------------------------------------------------------------------------
module "api_gateway" {
  source = "../../modules/api_gateway"

  project                   = var.project
  environment               = var.environment
  cognito_user_pool_arn     = module.cognito.user_pool_arn
  api_handler_function_name = module.lambda.api_handler_function_name
  api_handler_invoke_arn    = module.lambda.api_handler_invoke_arn
  log_retention_days        = var.log_retention_days

  depends_on = [module.lambda, module.cognito]
}

# -----------------------------------------------------------------------------
# CloudWatch Monitoring
# -----------------------------------------------------------------------------
module "cloudwatch" {
  source = "../../modules/cloudwatch"

  project     = var.project
  environment = var.environment
  alert_email = var.alert_email

  lambda_function_names = [
    module.lambda.feature_extraction_function_name,
    module.lambda.cluster_engine_function_name,
    module.lambda.reinforcement_engine_function_name,
    module.lambda.insight_generator_function_name,
    module.lambda.feedback_processor_function_name,
    module.lambda.api_handler_function_name,
  ]

  state_machine_arn            = module.step_functions.state_machine_arn
  lambda_error_threshold       = var.lambda_error_threshold
  lambda_duration_threshold_ms = var.lambda_duration_threshold_ms
  api_error_threshold          = var.api_error_threshold
  sfn_failure_threshold        = var.sfn_failure_threshold

  depends_on = [module.lambda, module.step_functions, module.api_gateway]
}