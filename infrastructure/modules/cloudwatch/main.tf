# =============================================================================
# Module: CloudWatch
# Alarms, dashboards, and SNS alerts for Qleam observability
# =============================================================================

# -----------------------------------------------------------------------------
# SNS Topic for Alerts
# -----------------------------------------------------------------------------
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-${var.environment}-alerts"

  tags = {
    Name = "${var.project}-${var.environment}-alerts"
  }
}

resource "aws_sns_topic_subscription" "email_alert" {
  count     = var.alert_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# -----------------------------------------------------------------------------
# Lambda Error Alarms
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project}-${var.environment}-${each.value}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = var.lambda_error_threshold
  alarm_description   = "Lambda function ${each.value} error rate exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# Lambda Duration Alarms
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project}-${var.environment}-${each.value}-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "p95"
  threshold           = var.lambda_duration_threshold_ms
  alarm_description   = "Lambda function ${each.value} p95 duration exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# Lambda Throttle Alarms
resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = toset(var.lambda_function_names)

  alarm_name          = "${var.project}-${var.environment}-${each.value}-throttles"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Throttles"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "Lambda function ${each.value} is being throttled"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# -----------------------------------------------------------------------------
# API Gateway Alarms
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "api_5xx_errors" {
  alarm_name          = "${var.project}-${var.environment}-api-5xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "5XXError"
  namespace           = "AWS/ApiGateway"
  period              = 60
  statistic           = "Sum"
  threshold           = var.api_error_threshold
  alarm_description   = "API Gateway 5XX error rate exceeded threshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = "${var.project}-${var.environment}-api"
    Stage   = var.environment
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_4xx_errors" {
  alarm_name          = "${var.project}-${var.environment}-api-4xx-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "4XXError"
  namespace           = "AWS/ApiGateway"
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "API Gateway 4XX error rate is high"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = "${var.project}-${var.environment}-api"
    Stage   = var.environment
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "api_latency" {
  alarm_name          = "${var.project}-${var.environment}-api-latency"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "Latency"
  namespace           = "AWS/ApiGateway"
  period              = 60
  extended_statistic  = "p95"
  threshold           = 10000
  alarm_description   = "API Gateway p95 latency exceeded 10 seconds"
  treat_missing_data  = "notBreaching"

  dimensions = {
    ApiName = "${var.project}-${var.environment}-api"
    Stage   = var.environment
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# -----------------------------------------------------------------------------
# Step Functions Alarms
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_metric_alarm" "sfn_failed" {
  alarm_name          = "${var.project}-${var.environment}-sfn-executions-failed"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 60
  statistic           = "Sum"
  threshold           = var.sfn_failure_threshold
  alarm_description   = "Step Function executions are failing"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "sfn_timed_out" {
  alarm_name          = "${var.project}-${var.environment}-sfn-executions-timed-out"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsTimedOut"
  namespace           = "AWS/States"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Step Function executions are timing out"
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = var.state_machine_arn
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

# -----------------------------------------------------------------------------
# CloudWatch Dashboard
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = "${var.project}-${var.environment}-dashboard"

  dashboard_body = jsonencode({
    widgets = [
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Errors"
          period = 60
          stat   = "Sum"
          metrics = [
            for fn in var.lambda_function_names : ["AWS/Lambda", "Errors", "FunctionName", fn]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Lambda Duration (p95)"
          period = 60
          stat   = "p95"
          metrics = [
            for fn in var.lambda_function_names : ["AWS/Lambda", "Duration", "FunctionName", fn]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "API Gateway Requests"
          period = 60
          stat   = "Sum"
          metrics = [
            ["AWS/ApiGateway", "Count", "ApiName", "${var.project}-${var.environment}-api", "Stage", var.environment],
            ["AWS/ApiGateway", "5XXError", "ApiName", "${var.project}-${var.environment}-api", "Stage", var.environment],
            ["AWS/ApiGateway", "4XXError", "ApiName", "${var.project}-${var.environment}-api", "Stage", var.environment]
          ]
          view = "timeSeries"
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Step Function Executions"
          period = 60
          stat   = "Sum"
          metrics = [
            ["AWS/States", "ExecutionsStarted", "StateMachineArn", var.state_machine_arn],
            ["AWS/States", "ExecutionsSucceeded", "StateMachineArn", var.state_machine_arn],
            ["AWS/States", "ExecutionsFailed", "StateMachineArn", var.state_machine_arn]
          ]
          view = "timeSeries"
        }
      }
    ]
  })
}
