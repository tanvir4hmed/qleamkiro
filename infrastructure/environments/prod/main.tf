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

locals {
  audio_bucket_name    = "${var.project}-${var.environment}-audio-storage"
  frontend_bucket_name = "${var.project}-${var.environment}-frontend"
}

module "vpc" {
  source = "../../modules/vpc"

  project            = var.project
  environment        = var.environment
  aws_region         = var.aws_region
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  enable_nat_gateway = var.enable_nat_gateway
}

module "iam" {
  source = "../../modules/iam"

  project           = var.project
  environment       = var.environment
  audio_bucket_name = local.audio_bucket_name
}

module "s3" {
  source = "../../modules/s3"

  project              = var.project
  environment          = var.environment
  bucket_name          = local.audio_bucket_name
  audio_retention_days = var.audio_retention_days
  allowed_origins      = ["https://${module.frontend.cloudfront_domain_name}"]
}

module "dynamodb" {
  source = "../../modules/dynamodb"

  project     = var.project
  environment = var.environment
  enable_pitr = var.enable_pitr
}

module "cognito" {
  source = "../../modules/cognito"

  project               = var.project
  environment           = var.environment
  enable_mfa            = var.enable_mfa
  callback_urls         = ["https://${module.frontend.cloudfront_domain_name}/callback"]
  logout_urls           = ["https://${module.frontend.cloudfront_domain_name}/logout"]
  cognito_auth_role_arn = module.iam.lambda_execution_role_arn
}

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
  step_function_arn            = ""
  use_bedrock                  = var.use_bedrock
  bedrock_model_id             = var.bedrock_model_id
  log_retention_days           = var.log_retention_days

  audio_layer_zip_path          = var.audio_layer_zip_path
  shared_utils_zip_path         = var.shared_utils_zip_path
  feature_extraction_zip_path   = var.feature_extraction_zip_path
  cluster_engine_zip_path       = var.cluster_engine_zip_path
  reinforcement_engine_zip_path = var.reinforcement_engine_zip_path
  insight_generator_zip_path    = var.insight_generator_zip_path
  feedback_processor_zip_path   = var.feedback_processor_zip_path
  api_handler_zip_path          = var.api_handler_zip_path

  depends_on = [module.vpc, module.iam, module.dynamodb, module.s3]
}

module "step_functions" {
  source = "../../modules/step_functions"

  project                       = var.project
  environment                   = var.environment
  step_functions_role_arn       = module.iam.step_functions_role_arn
  feature_extraction_lambda_arn = module.lambda.feature_extraction_function_arn
  cluster_engine_lambda_arn     = module.lambda.cluster_engine_function_arn
  insight_generator_lambda_arn  = module.lambda.insight_generator_function_arn
  audio_bucket_name             = local.audio_bucket_name
  log_retention_days            = var.log_retention_days

  depends_on = [module.lambda]
}

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

module "frontend" {
  source = "../../modules/frontend"

  project              = var.project
  environment          = var.environment
  frontend_bucket_name = local.frontend_bucket_name
}

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
