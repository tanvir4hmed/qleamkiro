# =============================================================================
# Module: API Gateway
# REST API with Cognito authorizer for all Qleam endpoints
# =============================================================================

# -----------------------------------------------------------------------------
# REST API
# -----------------------------------------------------------------------------
resource "aws_api_gateway_rest_api" "main" {
  name        = "${var.project}-${var.environment}-api"
  description = "Qleam MVP REST API"

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = {
    Name = "${var.project}-${var.environment}-api"
  }
}

# -----------------------------------------------------------------------------
# Cognito Authorizer
# -----------------------------------------------------------------------------
resource "aws_api_gateway_authorizer" "cognito" {
  name                   = "${var.project}-${var.environment}-cognito-authorizer"
  rest_api_id            = aws_api_gateway_rest_api.main.id
  type                   = "COGNITO_USER_POOLS"
  identity_source        = "method.request.header.Authorization"
  provider_arns          = [var.cognito_user_pool_arn]
  authorizer_result_ttl_in_seconds = 300
}

# -----------------------------------------------------------------------------
# Lambda Permission — allow API Gateway to invoke Lambda
# -----------------------------------------------------------------------------
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = var.api_handler_function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.main.execution_arn}/*/*"
}

# -----------------------------------------------------------------------------
# Resources and Methods
# -----------------------------------------------------------------------------

# /child
resource "aws_api_gateway_resource" "child" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "child"
}

# POST /child
resource "aws_api_gateway_method" "post_child" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.child.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "post_child" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.child.id
  http_method             = aws_api_gateway_method.post_child.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# /child/{child_id}
resource "aws_api_gateway_resource" "child_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.child.id
  path_part   = "{child_id}"
}

# DELETE /child/{child_id}
resource "aws_api_gateway_method" "delete_child" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.child_id.id
  http_method   = "DELETE"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "delete_child" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.child_id.id
  http_method             = aws_api_gateway_method.delete_child.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# /session
resource "aws_api_gateway_resource" "session" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_rest_api.main.root_resource_id
  path_part   = "session"
}

# /session/upload
resource "aws_api_gateway_resource" "session_upload" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.session.id
  path_part   = "upload"
}

# POST /session/upload
resource "aws_api_gateway_method" "post_session_upload" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.session_upload.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "post_session_upload" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.session_upload.id
  http_method             = aws_api_gateway_method.post_session_upload.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# /session/{session_id}
resource "aws_api_gateway_resource" "session_id" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.session.id
  path_part   = "{session_id}"
}

# /session/{session_id}/insight
resource "aws_api_gateway_resource" "session_insight" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.session_id.id
  path_part   = "insight"
}

# GET /session/{session_id}/insight
resource "aws_api_gateway_method" "get_session_insight" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.session_insight.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "get_session_insight" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.session_insight.id
  http_method             = aws_api_gateway_method.get_session_insight.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# /session/{session_id}/feedback
resource "aws_api_gateway_resource" "session_feedback" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.session_id.id
  path_part   = "feedback"
}

# POST /session/{session_id}/feedback
resource "aws_api_gateway_method" "post_session_feedback" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.session_feedback.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "post_session_feedback" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.session_feedback.id
  http_method             = aws_api_gateway_method.post_session_feedback.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# /child/{child_id}/sessions
resource "aws_api_gateway_resource" "child_sessions" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  parent_id   = aws_api_gateway_resource.child_id.id
  path_part   = "sessions"
}

# GET /child/{child_id}/sessions
resource "aws_api_gateway_method" "get_child_sessions" {
  rest_api_id   = aws_api_gateway_rest_api.main.id
  resource_id   = aws_api_gateway_resource.child_sessions.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "get_child_sessions" {
  rest_api_id             = aws_api_gateway_rest_api.main.id
  resource_id             = aws_api_gateway_resource.child_sessions.id
  http_method             = aws_api_gateway_method.get_child_sessions.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = var.api_handler_invoke_arn
}

# -----------------------------------------------------------------------------
# Deployment and Stage
# -----------------------------------------------------------------------------
resource "aws_api_gateway_deployment" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.child.id,
      aws_api_gateway_method.post_child.id,
      aws_api_gateway_integration.post_child.id,
      aws_api_gateway_resource.session_upload.id,
      aws_api_gateway_method.post_session_upload.id,
      aws_api_gateway_resource.session_insight.id,
      aws_api_gateway_method.get_session_insight.id,
      aws_api_gateway_resource.session_feedback.id,
      aws_api_gateway_method.post_session_feedback.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.post_child,
    aws_api_gateway_integration.delete_child,
    aws_api_gateway_integration.post_session_upload,
    aws_api_gateway_integration.get_session_insight,
    aws_api_gateway_integration.post_session_feedback,
    aws_api_gateway_integration.get_child_sessions,
  ]
}

resource "aws_api_gateway_stage" "main" {
  deployment_id = aws_api_gateway_deployment.main.id
  rest_api_id   = aws_api_gateway_rest_api.main.id
  stage_name    = var.environment

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      caller         = "$context.identity.caller"
      user           = "$context.identity.user"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      resourcePath   = "$context.resourcePath"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
    })
  }

  xray_tracing_enabled = true

  tags = {
    Name = "${var.project}-${var.environment}-api-stage"
  }
}

resource "aws_api_gateway_method_settings" "main" {
  rest_api_id = aws_api_gateway_rest_api.main.id
  stage_name  = aws_api_gateway_stage.main.stage_name
  method_path = "*/*"

  settings {
    metrics_enabled        = true
    logging_level          = "INFO"
    data_trace_enabled     = false
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${var.project}-${var.environment}"
  retention_in_days = var.log_retention_days
}
