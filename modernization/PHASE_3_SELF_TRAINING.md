# Phase 3: Self-Training Pipeline & Anonymized Storage (LEARNING)

## Goal
Parent-confirmed feedback flows into an anonymized training dataset. Quality gates ensure only validated data enters training. The system improves with every confirmed session. Model weight shifts from public-dataset priors to our own data as it grows.

## Training Data Flow

```
Parent records audio
        |
  [GATE -> EARS -> BRAIN -> INSIGHT]
        |
  Parent sees insight, gives feedback:
    - "Yes, was hungry" (confirms)
    - "No, was tired" (corrects)
    - "Not sure" (discarded)
        |
  [Quality Gate]
    - Audio quality passed?
    - Confidence check passed?
    - Not a duplicate?
        |
  [Anonymize & Store]
    - Extract: HuBERT embeddings + mel_spectrogram + age_days + confirmed_emotion
    - Strip: child_id, parent_id, session_id, S3_audio_path
    - Generate: anonymous feature_id (UUID)
    - Store in DynamoDB training_features + S3
        |
  [Retrain Trigger]
    - When sample threshold reached -> retrain BRAIN
    - If accuracy improves -> promote new model
```

## What Gets Stored Per Training Sample

```python
# Anonymized training record — NO PII
{
    "feature_id": "uuid-v4",                    # New random ID
    "hubert_embeddings_s3": "s3://bucket/training-features/uuid_emb.npz",
    "mel_spectrogram_s3": "s3://bucket/training-features/uuid_mel.npz",
    "confirmed_emotion": "hungry",              # Parent-confirmed label
    "age_days": 47,                             # EXACT age, continuous
    "sound_type": "cry",                        # From classifier
    "model_confidence_at_time": 0.72,           # What model predicted when parent saw it
    "audio_quality_snr": 18.5,                  # Quality metric
    "duration_s": 7.2,                          # Duration
    "confirmation_source": "parent_correct",    # parent_confirm | parent_correct
    "device_type": "iphone_14",                 # Helps normalize recordings
    "environment": "home_quiet",                # If available
    "created_at": "2026-03-07T10:30:00Z",      # Timestamp only
    # NO child_id, NO parent_id, NO session_id, NO audio S3 path
}
```

Key differences from Phase 2 storage:
- Phase 2 stores embeddings for ALL sessions (linked to session, temporary)
- Phase 3 stores ONLY parent-confirmed data, fully anonymized (permanent training data)

## Quality Gates for Training Acceptance

### Gate 1: Feedback Quality
- Parent must explicitly confirm or correct (not "skip" or "not sure")
- If parent corrects: use parent's label, not model's prediction (corrections = highest value training data)
- If parent confirms: use model's prediction as label

### Gate 2: Audio Quality
- SNR >= 10dB (clear enough to learn from)
- Duration >= 3s (enough signal)
- Baby sound confirmed by GATE + classifier
- No adult-only recording

### Gate 3: Confidence Check
- If parent CONFIRMS model prediction: model confidence must be >= 0.4 (avoid reinforcing lucky guesses on low-confidence predictions)
- If parent CORRECTS model prediction: always accept (correction = the model was wrong, learn from it)

### Gate 4: Deduplication
- Same child + same emotion + within 5 minutes = skip (don't overcount one crying episode)
- Embedding cosine similarity > 0.95 against recent samples = skip (re-upload detection)

## Model Weight Blending

As our own confirmed data grows, shift weight from public-dataset model to retrained model:

| Our Confirmed Samples | Public Dataset Weight | Our Data Weight |
|---|---|---|
| 0-29 | 100% | 0% (public-dataset model only) |
| 30-99 | 70% | 30% |
| 100-299 | 40% | 60% |
| 300+ | 15% | 85% |

This means the public dataset model (from Phase 2 pre-training) serves us immediately but gracefully fades as our own data proves more accurate.

## Training Trigger & Pipeline

### When to Retrain
- Every 50 new confirmed samples (batch trigger)
- Or weekly if >= 10 new samples since last train
- EventBridge rule checks daily + DynamoDB counter trigger

### Training Process (Step Function)
```
Step 1: Query training_features table for all confirmed samples
Step 2: Load HuBERT embeddings from S3
Step 3: If total samples < 30 -> skip (not enough data)
Step 4: Group by confirmed_emotion, check class balance
Step 5: Augment underrepresented classes
Step 6: Train classifier:
  - Input: HuBERT embeddings + age_days (NOW we have age!)
  - Output: 7-class emotion probabilities
  - This is now BETTER than Phase 2 model because:
    a) Our data has age_days (public datasets didn't)
    b) Our data is from real parents confirming real cries
    c) Audio is from real devices in real environments
Step 7: Validate on held-out 20% split
Step 8: Compare accuracy vs current active model
Step 9: If accuracy >= current model -> promote new model
Step 10: Store model artifact in S3, update model version in DynamoDB
```

### What Makes Our Data Better Than Public Datasets
- **age_days**: Public datasets don't have exact baby age. Ours does. This enables the age-conditioned classifier in Phase 4.
- **device diversity**: Real phones in real homes, not lab recordings
- **parent ground truth**: Parent knows their baby better than any label
- **longitudinal**: Same babies over time — developmental transitions captured
- **growing**: Gets bigger every day, automatically

## Tasks

### 3.1 Update Feedback Processor Lambda
- Receive parent feedback (confirm/correct/skip)
- Apply quality gates (all 4)
- If accepted: call anonymization module, store training record
- If rejected: log rejection reason to CloudWatch (no PII)
- Track acceptance rate as CloudWatch metric

### 3.2 Create Anonymization Module
- `shared/training_anonymizer.py`:
  - `anonymize_and_store(session_data, feedback, hubert_embeddings, mel_spectrogram)` -> feature_id or None
  - Strips ALL PII before storage
  - Generates anonymous feature_id (UUID)
  - Stores embeddings + mel to S3 training prefix
  - Writes metadata to DynamoDB training_features table
  - Returns None if quality gates reject

### 3.3 Create Training Trigger
- EventBridge rule: daily check for new sample count
- DynamoDB atomic counter: increment on each accepted sample
- When threshold reached: trigger Step Function
- Step Function orchestrates: Query -> Load -> Train -> Validate -> Promote/Discard

### 3.4 Create Model Trainer Lambda
- Loads training data from S3 + DynamoDB
- Trains classifier on HuBERT embeddings
- Phase 3: embeddings only (no age_days input yet — that's Phase 4)
- Phase 4 upgrade: adds age_days as continuous input
- Validates against held-out split
- Exports to TFLite, stores in S3
- Updates model_versions table if promoted

### 3.5 Model Version Management
- DynamoDB model_versions table tracks:
  - model_type (emotion_classifier)
  - version number
  - S3 path to model artifact
  - accuracy metrics
  - training sample count
  - active flag (which version is currently serving)
- Classifier Lambda loads active model version at cold start

## Infrastructure (Terraform)

```hcl
# EventBridge rule to check training readiness daily
resource "aws_cloudwatch_event_rule" "training_check" {
  name                = "qleam-training-check"
  schedule_expression = "rate(1 day)"
}

resource "aws_cloudwatch_event_target" "training_check_target" {
  rule      = aws_cloudwatch_event_rule.training_check.name
  target_id = "training-check-lambda"
  arn       = aws_lambda_function.training_check.arn
}

# Lambda to check if retraining needed
resource "aws_lambda_function" "training_check" {
  function_name = "qleam-training-check"
  memory_size   = 256
  timeout       = 30
}

# Step Function for training pipeline
resource "aws_sfn_state_machine" "training_pipeline" {
  name     = "qleam-training-pipeline"
  role_arn = aws_iam_role.step_function_role.arn
  definition = jsonencode({
    Comment = "Qleam model retraining pipeline"
    StartAt = "LoadTrainingData"
    States = {
      LoadTrainingData = {
        Type     = "Task"
        Resource = "aws_lambda_function.model_trainer.arn"
        Parameters = { step = "load" }
        Next     = "TrainModel"
      }
      TrainModel = {
        Type     = "Task"
        Resource = "aws_lambda_function.model_trainer.arn"
        Parameters = { step = "train" }
        Next     = "ValidateModel"
      }
      ValidateModel = {
        Type     = "Task"
        Resource = "aws_lambda_function.model_trainer.arn"
        Parameters = { step = "validate" }
        Next     = "PromoteOrDiscard"
      }
      PromoteOrDiscard = {
        Type = "Choice"
        Choices = [{
          Variable         = "$.accuracy_improved"
          BooleanEquals    = true
          Next             = "PromoteModel"
        }]
        Default = "DiscardModel"
      }
      PromoteModel = {
        Type     = "Task"
        Resource = "aws_lambda_function.model_trainer.arn"
        Parameters = { step = "promote" }
        End      = true
      }
      DiscardModel = {
        Type = "Pass"
        End  = true
      }
    }
  })
}

# Lambda for model training execution
resource "aws_lambda_function" "model_trainer" {
  function_name = "qleam-model-trainer"
  memory_size   = 3008
  timeout       = 900  # 15 min max
}

# DynamoDB table for model versions
resource "aws_dynamodb_table" "model_versions" {
  name         = "qleam-model-versions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "model_type"
  range_key    = "version"

  attribute {
    name = "model_type"
    type = "S"
  }
  attribute {
    name = "version"
    type = "N"
  }
}
```

## Files Changed
- CREATE: shared/training_anonymizer.py, lambdas/training_check/handler.py, lambdas/model_trainer/handler.py
- MODIFY: lambdas/feedback_processor/handler.py (quality gates + anonymization)
- TERRAFORM: EventBridge rule, Step Function, training_check Lambda, model_trainer Lambda, model_versions table

## Success Criteria
- Parent confirms -> anonymized record stored (zero PII in training table)
- Quality gates reject: low SNR, duplicates, skips, low-confidence confirms
- Retraining triggers automatically when threshold reached
- New model only promoted if accuracy >= current model
- Model weight blending works: public dataset model fades as our data grows
- Acceptance rate tracked in CloudWatch

## Deploy
- Workflows: `1-infra-deploy` (EventBridge, Step Function, new Lambdas, model_versions table) then `2-lambda-deploy`
