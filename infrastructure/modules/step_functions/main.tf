# =============================================================================
# Module: Step Functions
# Orchestrates the full audio processing pipeline
# =============================================================================

resource "aws_sfn_state_machine" "processing_pipeline" {
  name     = "${var.project}-${var.environment}-processing-pipeline"
  role_arn = var.step_functions_role_arn

  definition = jsonencode({
    Comment = "Qleam audio processing pipeline — classify first, then route"
    StartAt = "AudioClassifier"

    States = {
      # Step 1: Classify audio (sound type + adult/baby + features)
      AudioClassifier = {
        Type     = "Task"
        Resource = var.feature_extraction_lambda_arn
        Comment  = "Classify audio: sound type, adult/baby, extract features"
        Parameters = {
          "child_id.$"        = "$.child_id"
          "session_id.$"      = "$.session_id"
          "s3_audio_path.$"   = "$.s3_audio_path"
          "session_context.$" = "$.session_context"
        }
        ResultPath = "$.classifier_result"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ProcessingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ShouldFastReject"
      }

      # Step 2: Fast reject for critical quality failures
      ShouldFastReject = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.classifier_result.fast_reject"
            BooleanEquals = true
            Next          = "InsightGeneratorFastReject"
          }
        ]
        Default = "InsightGenerator"
      }

      InsightGeneratorFastReject = {
        Type     = "Task"
        Resource = var.insight_generator_lambda_arn
        Comment  = "Generate fast-reject insight (silence/quality failure)"
        InputPath = "$.classifier_result"
        ResultPath = "$.insight_result"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ProcessingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ProcessingComplete"
      }

      # Step 3: Generate insight (transcription, cry analysis, word detection, etc.)
      InsightGenerator = {
        Type     = "Task"
        Resource = var.insight_generator_lambda_arn
        Comment  = "Route by sound type: transcribe words, analyze cry, detect laugh"
        InputPath = "$.classifier_result"
        ResultPath = "$.insight_result"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 2
            MaxAttempts     = 3
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ProcessingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ClusterEngine"
      }

      # Step 4: Cluster acoustic patterns (optional, non-fatal)
      ClusterEngine = {
        Type     = "Task"
        Resource = var.cluster_engine_lambda_arn
        Comment  = "Cluster embedding for pattern history"
        Parameters = {
          "child_id.$"         = "$.child_id"
          "session_id.$"       = "$.session_id"
          "embedding_vector.$" = "$.classifier_result.embedding_vector"
        }
        ResultPath = "$.cluster_result"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ProcessingComplete"
            ResultPath  = "$.cluster_error"
          }
        ]
        Next = "ProcessingComplete"
      }

      ProcessingComplete = {
        Type    = "Succeed"
        Comment = "Pipeline completed successfully"
      }

      ProcessingFailed = {
        Type  = "Fail"
        Error = "ProcessingError"
        Cause = "Audio processing pipeline failed"
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.sfn.arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }

  tracing_configuration {
    enabled = true
  }

  tags = {
    Name      = "${var.project}-${var.environment}-processing-pipeline"
    Component = "step-functions"
  }
}

resource "aws_cloudwatch_log_group" "sfn" {
  name              = "/aws/states/${var.project}-${var.environment}-processing-pipeline"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# EventBridge Rule — Trigger Step Function on S3 Upload
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "s3_upload" {
  count       = var.enable_s3_event_trigger ? 1 : 0
  name        = "${var.project}-${var.environment}-s3-audio-upload"
  description = "Trigger processing pipeline when audio is uploaded to S3"

  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = {
        name = [var.audio_bucket_name]
      }
      object = {
        key = [{
          prefix = ""
        }]
      }
    }
  })
}

resource "aws_cloudwatch_event_target" "sfn_trigger" {
  count     = var.enable_s3_event_trigger ? 1 : 0
  rule      = aws_cloudwatch_event_rule.s3_upload[0].name
  target_id = "TriggerProcessingPipeline"
  arn       = aws_sfn_state_machine.processing_pipeline.id
  role_arn  = aws_iam_role.eventbridge[0].arn

  input_transformer {
    input_paths = {
      bucket = "$.detail.bucket.name"
      key    = "$.detail.object.key"
    }
    input_template = <<EOF
{
  "s3_audio_path": "<key>",
  "child_id": "<key>",
  "session_id": "<key>"
}
EOF
  }
}

# EventBridge IAM Role
resource "aws_iam_role" "eventbridge" {
  count = var.enable_s3_event_trigger ? 1 : 0
  name  = "${var.project}-${var.environment}-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "events.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "eventbridge_sfn" {
  count = var.enable_s3_event_trigger ? 1 : 0
  name  = "${var.project}-${var.environment}-eventbridge-sfn-policy"
  role  = aws_iam_role.eventbridge[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = aws_sfn_state_machine.processing_pipeline.arn
      }
    ]
  })
}
