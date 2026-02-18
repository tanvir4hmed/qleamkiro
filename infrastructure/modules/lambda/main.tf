# =============================================================================
# Module: Lambda
# Deploys all Qleam Lambda functions with layers, env vars, VPC config
# =============================================================================

locals {
  common_env_vars = {
    ENVIRONMENT              = var.environment
    S3_BUCKET_NAME           = var.s3_bucket_name
    CHILD_PROFILE_TABLE      = var.child_profile_table
    SESSION_TABLE            = var.session_table
    SOUND_CLUSTER_TABLE      = var.sound_cluster_table
    SEMANTIC_BRIDGE_TABLE    = var.semantic_bridge_table
    FEEDBACK_TABLE           = var.feedback_table
    ALPHA_VALUE              = tostring(var.alpha_value)
    CLUSTER_SIMILARITY_THRESHOLD = tostring(var.cluster_similarity_threshold)
    STEP_FUNCTION_ARN        = var.step_function_arn
    LOG_LEVEL                = var.environment == "prod" ? "WARNING" : "DEBUG"
  }
}

# -----------------------------------------------------------------------------
# Lambda Layer — Audio Processing (librosa, numpy, scipy)
# -----------------------------------------------------------------------------
resource "aws_lambda_layer_version" "audio_processing" {
  layer_name          = "${var.project}-${var.environment}-audio-processing"
  description         = "librosa, numpy, scipy for audio feature extraction"
  filename            = var.audio_layer_zip_path
  source_code_hash    = filebase64sha256(var.audio_layer_zip_path)
  compatible_runtimes = ["python3.11"]
  compatible_architectures = ["x86_64"]
}

# -----------------------------------------------------------------------------
# Lambda Layer — Shared Utilities
# -----------------------------------------------------------------------------
resource "aws_lambda_layer_version" "shared_utils" {
  layer_name          = "${var.project}-${var.environment}-shared-utils"
  description         = "Qleam shared utilities (similarity, normalization, constants)"
  filename            = var.shared_utils_zip_path
  source_code_hash    = filebase64sha256(var.shared_utils_zip_path)
  compatible_runtimes = ["python3.11"]
  compatible_architectures = ["x86_64"]
}

# -----------------------------------------------------------------------------
# Feature Extraction Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "feature_extraction" {
  function_name    = "${var.project}-${var.environment}-feature-extraction"
  description      = "Extracts acoustic features from uploaded audio"
  filename         = var.feature_extraction_zip_path
  source_code_hash = filebase64sha256(var.feature_extraction_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 30
  memory_size      = 512

  layers = [
    aws_lambda_layer_version.audio_processing.arn,
    aws_lambda_layer_version.shared_utils.arn
  ]

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
# Cluster Engine Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "cluster_engine" {
  function_name    = "${var.project}-${var.environment}-cluster-engine"
  description      = "Manages sound cluster formation and evolution"
  filename         = var.cluster_engine_zip_path
  source_code_hash = filebase64sha256(var.cluster_engine_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 30
  memory_size      = 256

  layers = [
    aws_lambda_layer_version.shared_utils.arn
  ]

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

  tags = {
    Name      = "${var.project}-${var.environment}-cluster-engine"
    Component = "cluster-engine"
  }
}

resource "aws_cloudwatch_log_group" "cluster_engine" {
  name              = "/aws/lambda/${aws_lambda_function.cluster_engine.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Reinforcement Engine Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "reinforcement_engine" {
  function_name    = "${var.project}-${var.environment}-reinforcement-engine"
  description      = "Updates reinforcement weights and semantic bridges"
  filename         = var.reinforcement_engine_zip_path
  source_code_hash = filebase64sha256(var.reinforcement_engine_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 15
  memory_size      = 256

  layers = [
    aws_lambda_layer_version.shared_utils.arn
  ]

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

  tags = {
    Name      = "${var.project}-${var.environment}-reinforcement-engine"
    Component = "reinforcement-engine"
  }
}

resource "aws_cloudwatch_log_group" "reinforcement_engine" {
  name              = "/aws/lambda/${aws_lambda_function.reinforcement_engine.function_name}"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# Insight Generator Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "insight_generator" {
  function_name    = "${var.project}-${var.environment}-insight-generator"
  description      = "Generates structured insights from session data"
  filename         = var.insight_generator_zip_path
  source_code_hash = filebase64sha256(var.insight_generator_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 30
  memory_size      = 256

  layers = [
    aws_lambda_layer_version.shared_utils.arn
  ]

  environment {
    variables = merge(local.common_env_vars, {
      BEDROCK_MODEL_ID = var.bedrock_model_id
      USE_BEDROCK      = tostring(var.use_bedrock)
    })
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [var.lambda_security_group_id]
  }

  tracing_config {
    mode = "Active"
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
  function_name    = "${var.project}-${var.environment}-feedback-processor"
  description      = "Processes parent feedback and triggers reinforcement"
  filename         = var.feedback_processor_zip_path
  source_code_hash = filebase64sha256(var.feedback_processor_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 15
  memory_size      = 256

  layers = [
    aws_lambda_layer_version.shared_utils.arn
  ]

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
  function_name    = "${var.project}-${var.environment}-api-handler"
  description      = "Handles API Gateway requests and routes to appropriate services"
  filename         = var.api_handler_zip_path
  source_code_hash = filebase64sha256(var.api_handler_zip_path)
  handler          = "handler.lambda_handler"
  runtime          = "python3.11"
  role             = var.lambda_execution_role_arn
  timeout          = 30
  memory_size      = 256

  layers = [
    aws_lambda_layer_version.shared_utils.arn
  ]

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

  tags = {
    Name      = "${var.project}-${var.environment}-api-handler"
    Component = "api-handler"
  }
}

resource "aws_cloudwatch_log_group" "api_handler" {
  name              = "/aws/lambda/${aws_lambda_function.api_handler.function_name}"
  retention_in_days = var.log_retention_days
}
