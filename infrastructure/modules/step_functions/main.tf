# =============================================================================
# Module: Step Functions
# Orchestrates the full audio processing pipeline
# =============================================================================

resource "aws_sfn_state_machine" "processing_pipeline" {
  name     = "${var.project}-${var.environment}-processing-pipeline"
  role_arn = var.step_functions_role_arn

  definition = jsonencode({
    Comment = "Qleam audio processing pipeline with fast-reject short-circuit for critical-quality sessions"
    StartAt = "FeatureExtraction"

    States = {
      FeatureExtraction = {
        Type     = "Task"
        Resource = var.feature_extraction_lambda_arn
        Comment  = "Extract acoustic features from uploaded audio"
        Parameters = {
          "child_id.$"        = "$.child_id"
          "session_id.$"      = "$.session_id"
          "s3_audio_path.$"   = "$.s3_audio_path"
          "session_context.$" = "$.session_context"
        }
        ResultPath = "$.feature_result"
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

      ShouldFastReject = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.feature_result.fast_reject"
            BooleanEquals = true
            Next          = "InsightGeneratorFastReject"
          }
        ]
        Default = "ClusterEngine"
      }

      InsightGeneratorFastReject = {
        Type     = "Task"
        Resource = var.insight_generator_lambda_arn
        Comment  = "Generate immediate rejection insight and stop for critical-quality sessions"
        Parameters = {
          "child_id.$"   = "$.child_id"
          "session_id.$" = "$.session_id"
          "cluster_id"   = ""
        }
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

      ClusterEngine = {
        Type     = "Task"
        Resource = var.cluster_engine_lambda_arn
        Comment  = "Assign audio embedding to cluster or create new cluster"
        Parameters = {
          "child_id.$"         = "$.child_id"
          "session_id.$"       = "$.session_id"
          "embedding_vector.$" = "$.feature_result.embedding_vector"
        }
        ResultPath = "$.cluster_result"
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
        Next = "InsightGenerator"
      }

      InsightGenerator = {
        Type     = "Task"
        Resource = var.insight_generator_lambda_arn
        Comment  = "Generate structured insight from session state"
        Parameters = {
          "child_id.$"   = "$.child_id"
          "session_id.$" = "$.session_id"
          "cluster_id.$" = "$.cluster_result.cluster_id"
        }
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
        Next = "DevelopmentalTracker"
      }

      DevelopmentalTracker = {
        Type     = "Task"
        Resource = var.developmental_tracker_lambda_arn
        Comment  = "Track CBR trend, VTL growth, φ order parameter, and milestone logging"
        Parameters = {
          "child_id.$"   = "$.child_id"
          "session_id.$" = "$.session_id"
          "cluster_id.$" = "$.cluster_result.cluster_id"
        }
        ResultPath = "$.developmental_result"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ConceptDecoder"
            ResultPath  = "$.developmental_error"
          }
        ]
        Next = "ConceptDecoder"
      }

      ConceptDecoder = {
        Type     = "Task"
        Resource = var.concept_decoder_lambda_arn
        Comment  = "Decode concept graph for session and check proto-word crystallization"
        Parameters = {
          "child_id.$"   = "$.child_id"
          "session_id.$" = "$.session_id"
          "cluster_id.$" = "$.cluster_result.cluster_id"
        }
        ResultPath = "$.concept_decode_result"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "SpeechAnalyzer"
            ResultPath  = "$.concept_decode_error"
          }
        ]
        Next = "SpeechAnalyzer"
      }

      SpeechAnalyzer = {
        Type     = "Task"
        Resource = var.speech_analyzer_lambda_arn
        Comment  = "Language development analysis for LINGUISTIC-mode sessions (non-fatal)"
        Parameters = {
          "child_id.$"   = "$.child_id"
          "session_id.$" = "$.session_id"
          "cluster_id.$" = "$.cluster_result.cluster_id"
        }
        ResultPath = "$.speech_analysis_result"
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "ProcessingComplete"
            ResultPath  = "$.speech_analysis_error"
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
