# =============================================================================
# Module: Lambda
# Deploys all Qleam Lambda functions as container images from ECR
# =============================================================================

locals {
  common_env_vars = {
    ENVIRONMENT                  = var.environment
    S3_BUCKET_NAME               = var.s3_bucket_name
    CHILD_PROFILE_TABLE          = var.child_profile_table
    SESSION_TABLE                = var.session_table
    SOUND_CLUSTER_TABLE          = var.sound_cluster_table
    SEMANTIC_BRIDGE_TABLE        = var.semantic_bridge_table
    FEEDBACK_TABLE               = var.feedback_table
    CONCEPT_GRAPH_TABLE          = var.concept_graph_table
    MILESTONES_TABLE             = var.milestones_table
    POPULATION_MODEL_TABLE       = var.population_model_table
    TRAINING_CANDIDATE_TABLE     = var.training_candidate_table
    MODEL_REGISTRY_TABLE         = var.model_registry_table
    TRAINING_FEATURES_TABLE      = var.training_features_table
    SAGEMAKER_HUBERT_ENDPOINT    = var.sagemaker_hubert_endpoint_name
    MODEL_VERSIONS_TABLE         = var.model_versions_table
    TRAINING_STEP_FUNCTION_ARN   = var.training_step_function_arn
    STEP_FUNCTION_ARN            = var.step_function_arn
    STEP_FUNCTION_ARN_PARAM_NAME = var.step_function_arn_param_name
    LOG_LEVEL                    = var.environment == "prod" ? "WARNING" : "DEBUG"
  }
}

# -----------------------------------------------------------------------------
# Feature Extraction Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "feature_extraction" {
  function_name = "${var.project}-${var.environment}-feature-extraction"
  description   = "Extracts acoustic features from uploaded audio"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["feature_extraction"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 60
  memory_size = 1024

  environment {
    variables = local.common_env_vars
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  # image_uri is managed by 2-lambda-deploy (ECR push + update-function-code).
  # Terraform must not revert it on infra deploys or it would load placeholder images.
  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-feature-extraction"
    Component = "feature-extraction"
  }
}

resource "aws_cloudwatch_log_group" "feature_extraction" {
  name              = "/aws/lambda/${aws_lambda_function.feature_extraction.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Insight Generator Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "insight_generator" {
  function_name = "${var.project}-${var.environment}-insight-generator"
  description   = "Generates structured insights from session data"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["insight_generator"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 60
  memory_size = 512

  environment {
    variables = merge(local.common_env_vars, {
      BEDROCK_MODEL_ID               = var.bedrock_model_id
      USE_BEDROCK                    = tostring(var.use_bedrock)
      USE_SAGEMAKER_INTENT_ENDPOINT  = tostring(var.use_sagemaker_intent_endpoint)
      SAGEMAKER_INTENT_ENDPOINT_NAME = var.sagemaker_intent_endpoint_name
      USE_TRANSCRIBE_FOR_LINGUISTIC  = tostring(var.use_transcribe_for_linguistic)
      TRANSCRIBE_TIMEOUT_SECONDS     = tostring(var.transcribe_timeout_seconds)
    })
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-insight-generator"
    Component = "insight-generator"
  }
}

resource "aws_cloudwatch_log_group" "insight_generator" {
  name              = "/aws/lambda/${aws_lambda_function.insight_generator.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Feedback Processor Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "feedback_processor" {
  function_name = "${var.project}-${var.environment}-feedback-processor"
  description   = "Processes parent feedback and triggers reinforcement"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["feedback_processor"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 30
  memory_size = 512

  environment {
    variables = local.common_env_vars
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-feedback-processor"
    Component = "feedback-processor"
  }
}

resource "aws_cloudwatch_log_group" "feedback_processor" {
  name              = "/aws/lambda/${aws_lambda_function.feedback_processor.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# API Handler Lambda (routes API Gateway requests)
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "api_handler" {
  function_name = "${var.project}-${var.environment}-api-handler"
  description   = "Handles API Gateway requests and routes to appropriate services"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["api_handler"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 30
  memory_size = 512

  environment {
    variables = merge(local.common_env_vars, {
      ALLOWED_ORIGINS = join(",", var.allowed_origins)
    })
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-api-handler"
    Component = "api-handler"
  }
}

resource "aws_cloudwatch_log_group" "api_handler" {
  name              = "/aws/lambda/${aws_lambda_function.api_handler.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Training Check Lambda (Phase 3 — daily check if retraining is needed)
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "training_check" {
  function_name = "${var.project}-${var.environment}-training-check"
  description   = "Checks if model retraining conditions are met and triggers training pipeline"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["training_check"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 30
  memory_size = 256

  environment {
    variables = local.common_env_vars
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-training-check"
    Component = "training-check"
  }
}

resource "aws_cloudwatch_log_group" "training_check" {
  name              = "/aws/lambda/${aws_lambda_function.training_check.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Model Trainer Lambda (Phase 3/4 — trains age-conditioned classifier)
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "model_trainer" {
  function_name = "${var.project}-${var.environment}-model-trainer"
  description   = "Trains two-branch age-conditioned emotion classifier from confirmed data"

  package_type = "Image"
  image_uri    = "${var.ecr_repository_urls["model_trainer"]}:${var.image_tag}"

  role        = var.lambda_execution_role_arn
  timeout     = 300
  memory_size = 1024

  environment {
    variables = local.common_env_vars
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
  }

  lifecycle {
    ignore_changes = [image_uri]
  }

  tags = {
    Name      = "${var.project}-${var.environment}-model-trainer"
    Component = "model-trainer"
  }
}

resource "aws_cloudwatch_log_group" "model_trainer" {
  name              = "/aws/lambda/${aws_lambda_function.model_trainer.function_name}"
  retention_in_days = var.log_retention_days
}
