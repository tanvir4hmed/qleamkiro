# =============================================================================
# Module: Lambda
# Deploys all Qleam Lambda functions as container images from ECR
# =============================================================================

locals {
  common_env_vars = {
    ENVIRONMENT                   = var.environment
    S3_BUCKET_NAME                = var.s3_bucket_name
    CHILD_PROFILE_TABLE           = var.child_profile_table
    SESSION_TABLE                 = var.session_table
    SOUND_CLUSTER_TABLE           = var.sound_cluster_table
    SEMANTIC_BRIDGE_TABLE         = var.semantic_bridge_table
    FEEDBACK_TABLE                = var.feedback_table
    ALPHA_VALUE                   = tostring(var.alpha_value)
    CLUSTER_SIMILARITY_THRESHOLD  = tostring(var.cluster_similarity_threshold)
    STEP_FUNCTION_ARN             = var.step_function_arn
    STEP_FUNCTION_ARN_PARAM_NAME  = var.step_function_arn_param_name
    LOG_LEVEL                     = var.environment == "prod" ? "WARNING" : "DEBUG"
  }
}

# -----------------------------------------------------------------------------
# Feature Extraction Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_function" "feature_extraction" {
  function_name = "${var.project}-${var.environment}-feature-extraction"
  description   = "Extracts acoustic features from uploaded audio"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["feature_extraction"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 60
  memory_size   = 1024

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
  function_name = "${var.project}-${var.environment}-cluster-engine"
  description   = "Manages sound cluster formation and evolution"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["cluster_engine"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 60
  memory_size   = 512

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
  function_name = "${var.project}-${var.environment}-reinforcement-engine"
  description   = "Updates reinforcement weights and semantic bridges"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["reinforcement_engine"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 30
  memory_size   = 512

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
  function_name = "${var.project}-${var.environment}-insight-generator"
  description   = "Generates structured insights from session data"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["insight_generator"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 60
  memory_size   = 512

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
  function_name = "${var.project}-${var.environment}-feedback-processor"
  description   = "Processes parent feedback and triggers reinforcement"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["feedback_processor"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 30
  memory_size   = 512

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
  function_name = "${var.project}-${var.environment}-api-handler"
  description   = "Handles API Gateway requests and routes to appropriate services"

  package_type  = "Image"
  image_uri     = "${var.ecr_repository_urls["api_handler"]}:${var.image_tag}"

  role          = var.lambda_execution_role_arn
  timeout       = 30
  memory_size   = 512

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

  tags = {
    Name      = "${var.project}-${var.environment}-api-handler"
    Component = "api-handler"
  }
}

resource "aws_cloudwatch_log_group" "api_handler" {
  name              = "/aws/lambda/${aws_lambda_function.api_handler.function_name}"
  retention_in_days = var.log_retention_days
}

