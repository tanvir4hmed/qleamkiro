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

# =============================================================================
# Training Pipeline Step Function (Phase 3)
# Orchestrates: training_check → model_trainer (load → train → validate → promote)
# =============================================================================

resource "aws_sfn_state_machine" "training_pipeline" {
  count    = var.enable_training_pipeline ? 1 : 0
  name     = "${var.project}-${var.environment}-training-pipeline"
  role_arn = var.step_functions_role_arn

  definition = jsonencode({
    Comment = "Qleam model retraining pipeline — check threshold, then train/validate/promote"
    StartAt = "TrainingCheck"

    States = {
      # Step 1: Check if retraining conditions are met
      TrainingCheck = {
        Type     = "Task"
        Resource = var.training_check_lambda_arn
        Comment  = "Check sample count thresholds for retraining"
        ResultPath = "$.check_result"
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 5
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TrainingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ShouldTrain"
      }

      # Step 2: Decision — did training_check say to trigger?
      ShouldTrain = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.check_result.triggered"
            BooleanEquals = true
            Next          = "LoadData"
          }
        ]
        Default = "TrainingSkipped"
      }

      # Step 3: Load confirmed training data from DynamoDB + S3
      LoadData = {
        Type     = "Task"
        Resource = var.model_trainer_lambda_arn
        Comment  = "Load confirmed embeddings and age data"
        Parameters = {
          "step"            = "load"
          "trigger_reason.$" = "$.check_result.reason"
        }
        ResultPath = "$.load_result"
        TimeoutSeconds = 120
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 5
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TrainingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ShouldSkipTraining"
      }

      # Step 3b: Check if load step says to skip (too few samples)
      ShouldSkipTraining = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.load_result.skip"
            BooleanEquals = true
            Next          = "TrainingSkipped"
          }
        ]
        Default = "TrainModel"
      }

      # Step 4: Train two-branch age-conditioned classifier
      TrainModel = {
        Type     = "Task"
        Resource = var.model_trainer_lambda_arn
        Comment  = "Train classifier on loaded data"
        InputPath = "$.load_result"
        ResultPath = "$.train_result"
        TimeoutSeconds = 300
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 10
            MaxAttempts     = 1
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TrainingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ValidateModel"
      }

      # Step 5: Validate — compare to active model
      ValidateModel = {
        Type     = "Task"
        Resource = var.model_trainer_lambda_arn
        Comment  = "Compare new model accuracy to current active model"
        InputPath = "$.train_result"
        ResultPath = "$.validate_result"
        TimeoutSeconds = 60
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 5
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TrainingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "ShouldPromote"
      }

      # Step 6: Decision — did accuracy improve enough?
      ShouldPromote = {
        Type = "Choice"
        Choices = [
          {
            Variable      = "$.validate_result.accuracy_improved"
            BooleanEquals = true
            Next          = "PromoteModel"
          }
        ]
        Default = "TrainingNoImprovement"
      }

      # Step 7: Promote model — copy to permanent S3, update ModelVersions
      PromoteModel = {
        Type     = "Task"
        Resource = var.model_trainer_lambda_arn
        Comment  = "Promote new model to production"
        InputPath = "$.validate_result"
        ResultPath = "$.promote_result"
        TimeoutSeconds = 60
        Retry = [
          {
            ErrorEquals     = ["Lambda.ServiceException", "Lambda.AWSLambdaException", "Lambda.SdkClientException"]
            IntervalSeconds = 5
            MaxAttempts     = 2
            BackoffRate     = 2
          }
        ]
        Catch = [
          {
            ErrorEquals = ["States.ALL"]
            Next        = "TrainingFailed"
            ResultPath  = "$.error"
          }
        ]
        Next = "TrainingComplete"
      }

      TrainingComplete = {
        Type    = "Succeed"
        Comment = "Model training and promotion completed successfully"
      }

      TrainingSkipped = {
        Type    = "Succeed"
        Comment = "Training skipped — conditions not met"
      }

      TrainingNoImprovement = {
        Type    = "Succeed"
        Comment = "Training completed but new model did not improve enough to promote"
      }

      TrainingFailed = {
        Type  = "Fail"
        Error = "TrainingError"
        Cause = "Model training pipeline failed"
      }
    }
  })

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.training_sfn[0].arn}:*"
    include_execution_data = false
    level                  = "ERROR"
  }

  tracing_configuration {
    enabled = true
  }

  tags = {
    Name      = "${var.project}-${var.environment}-training-pipeline"
    Component = "step-functions"
  }
}

resource "aws_cloudwatch_log_group" "training_sfn" {
  count             = var.enable_training_pipeline ? 1 : 0
  name              = "/aws/states/${var.project}-${var.environment}-training-pipeline"
  retention_in_days = var.log_retention_days
}

# -----------------------------------------------------------------------------
# EventBridge Rule — Daily Training Check (6 AM UTC)
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_event_rule" "daily_training_check" {
  count               = var.enable_training_pipeline ? 1 : 0
  name                = "${var.project}-${var.environment}-daily-training-check"
  description         = "Trigger training pipeline daily to check if retraining is needed"
  schedule_expression = "cron(0 6 * * ? *)"

  tags = {
    Name      = "${var.project}-${var.environment}-daily-training-check"
    Component = "training"
  }
}

resource "aws_cloudwatch_event_target" "training_sfn_trigger" {
  count     = var.enable_training_pipeline ? 1 : 0
  rule      = aws_cloudwatch_event_rule.daily_training_check[0].name
  target_id = "TriggerTrainingPipeline"
  arn       = aws_sfn_state_machine.training_pipeline[0].arn
  role_arn  = aws_iam_role.training_eventbridge[0].arn

  input = jsonencode({
    source = "scheduled"
    time   = "daily"
  })
}

# EventBridge IAM Role for Training Pipeline
resource "aws_iam_role" "training_eventbridge" {
  count = var.enable_training_pipeline ? 1 : 0
  name  = "${var.project}-${var.environment}-training-eventbridge-role"

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

resource "aws_iam_role_policy" "training_eventbridge_sfn" {
  count = var.enable_training_pipeline ? 1 : 0
  name  = "${var.project}-${var.environment}-training-eventbridge-sfn-policy"
  role  = aws_iam_role.training_eventbridge[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["states:StartExecution"]
        Resource = aws_sfn_state_machine.training_pipeline[0].arn
      }
    ]
  })
}
