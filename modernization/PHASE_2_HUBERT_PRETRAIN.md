# Phase 2: HuBERT Feature Extraction + Pre-Training (EARS + BRAIN Bootstrap)

## Goal
Deploy HuBERT on SageMaker Serverless as the feature extractor (EARS). Pre-train a classifier (BRAIN) on public baby cry datasets so we launch with a real model on day 1 — not empty research priors.

## Why HuBERT (Not wav2vec 2.0, Not YAMNet)

### Sep 2025 Research Finding
Paper: "Speech transformer models for extracting information from baby cries" (arXiv:2509.02259)
> "Wav2Vec2 did not achieve the best result on any task when compared to UniSpeech and HuBERT."

HuBERT outperformed wav2vec 2.0 specifically for baby cry classification.

### Comparison

| Model | Baby Cry Performance | Size | Embeddings | Best For |
|---|---|---|---|---|
| YAMNet | Knows "baby cry" as class, can't distinguish emotions | 3MB | 1024-dim (general audio) | Sound classification gate only |
| wav2vec 2.0 | Good audio representation | 360MB | 768-dim (speech) | General speech tasks |
| **HuBERT** | **Best for baby cry** (proven 2025) | 360MB | 768-dim (speech+audio) | Fine-grained audio emotion |

HuBERT uses the same architecture as wav2vec 2.0 (self-supervised transformer, 768-dim embeddings, ~360MB) but learns better representations through masked prediction with offline clustering. Same cost, same infrastructure, better accuracy for our use case.

### Why Not YAMNet as Middle Layer?
YAMNet tells you "this is a baby cry" (classification). But HuBERT embeddings + our classifier can do the same thing AND distinguish emotions. Adding YAMNet as a separate layer = two model inferences instead of one, extra complexity for no gain. The GATE layer handles quick rejection with cheap acoustic checks (F0, RMS). No model needed for that.

## Architecture

```
Audio (16kHz mono)
      |
  [GATE: Lambda]              <- acoustic checks, <2s
  Reject silence/adult/noise
      |
  [EARS: SageMaker Serverless] <- HuBERT (~360MB)
  Input: raw waveform
  Output: 768-dim embeddings per ~20ms frame
      |
  [BRAIN: Lambda]              <- classifier (~2MB TFLite)
  Input: HuBERT embeddings + age_days
  Output: sound_type + emotion_probabilities
      |
  [INSIGHT: Lambda]
  Format for parent
```

Only baby sounds (those that pass GATE) hit SageMaker. That's ~40% of uploads. The rest are rejected in <2s on Lambda.

## Pre-Training on Public Datasets (BRAIN Bootstrap)

### Available Datasets

| Dataset | Samples | Labels | Access |
|---|---|---|---|
| **Dunstan Baby Language** | 1,128 | 9 labels (hungry, burping, stomachache, discomfort, tired, lonely, cold/hot, scared, unknown) | GitHub (donateacry corpus) |
| **DonateACry** | 457 (cleaned) | 5 labels (hunger, burping, belly pain, discomfort, tired) | GitHub open source |
| **Baby Chillanto** | 2,268 | 5 labels (asphyxia, deaf, hunger, normal, pain) | Request from CONACYT Mexico |
| **ICSD** | Varies | Cry detection (binary) | GitHub open source |
| **AudioSet baby cry** | Thousands | Baby cry class (no emotion) | Google |

### Pre-Training Pipeline (Before Launch)

```
Step 1: Download public datasets
  - Dunstan: 1,128 recordings (9 emotion labels, 0-2yr age range)
  - DonateACry: 457 clips (5 emotion labels)
  - Baby Chillanto: 2,268 samples (medical grade, 5 labels)
  - Total: ~3,500-4,000 labeled samples

Step 2: Unify labels across datasets
  Map to our 7 emotion classes:
    hungry     <- Dunstan:hungry, DonateACry:hunger, Chillanto:hunger
    tired      <- Dunstan:tired, DonateACry:tired
    discomfort <- Dunstan:discomfort, DonateACry:discomfort
    gas        <- Dunstan:stomachache, DonateACry:belly_pain
    pain       <- Dunstan:scared, Chillanto:pain
    burp       <- Dunstan:burping, DonateACry:burping
    content    <- Chillanto:normal
  Discard: Dunstan:unknown, Dunstan:lonely, Dunstan:cold/hot (too few samples)
           Chillanto:asphyxia, Chillanto:deaf (pathological, different domain)

Step 3: Process through HuBERT
  - Run each audio clip through HuBERT
  - Extract 768-dim embeddings (mean-pooled across frames)
  - Store: embedding + label + source_dataset

Step 4: Train classifier
  - Input: 768-dim HuBERT embeddings (no age_days yet — public datasets don't have it)
  - Output: 7-class emotion probabilities
  - Architecture: Dense(256) -> Dense(128) -> Dense(7, softmax)
  - Split: 80% train, 20% validation
  - Augment underrepresented classes (time stretch, pitch shift, noise)

Step 5: Validate
  - Track per-emotion accuracy, precision, recall
  - Expected baseline: 60-75% accuracy on 7 classes (limited data)
  - This is our day-1 model — it gets better with parent-confirmed data

Step 6: Export & deploy
  - Export classifier to TFLite (~2MB)
  - Deploy as Lambda layer or load from S3
```

### What This Gives Us on Day 1
- A REAL classifier that learned from ~3,500 baby cry samples
- Not research priors or hand-tuned rules
- Not empty and waiting for parents to teach it
- Accuracy will be moderate (60-75%) but genuine ML, not heuristic guesses
- Parent-confirmed data in Phase 3 makes it progressively better

## Tasks

### 2.1 Deploy HuBERT on SageMaker Serverless
- Create SageMaker Serverless endpoint with HuBERT model
- Input: raw audio waveform (16kHz, mono)
- Output: 768-dim embeddings (mean-pooled per clip)
- Terraform: SageMaker endpoint, IAM roles, S3 model artifact
- Test cold start latency (target: <5s cold, <1s warm)

### 2.2 Build Inference Lambda
- Lambda calls SageMaker endpoint with audio
- Receives 768-dim embeddings
- Passes to classifier
- Returns emotion probabilities + sound type
- Handle SageMaker cold start gracefully (retry once)

### 2.3 Download & Prepare Public Datasets
- Script to download Dunstan/DonateACry from GitHub
- Request access to Baby Chillanto
- Unify labels to our 7-class taxonomy
- Audio preprocessing: resample to 16kHz mono, trim/pad to uniform length
- Store prepared dataset in S3

### 2.4 Pre-Train Classifier on Public Data
- Run all public dataset audio through HuBERT endpoint
- Extract and store embeddings
- Train Dense classifier on embeddings -> 7 emotion classes
- Augment underrepresented classes
- Validate on held-out split
- Export to TFLite

### 2.5 Integrate Into Pipeline
- feature_extraction Lambda: after GATE passes, call SageMaker for HuBERT embeddings
- New classifier Lambda (or integrated): run TFLite model on embeddings
- insight_generator receives: emotion_probabilities, sound_type, confidence
- Replace old cry_analyzer scoring with classifier output
- Keep cry_analyzer Dunstan mapping for 0-3m display text only

### 2.6 Store Embeddings for Training (Phase 3 prep)
- For every session processed, store:
  - HuBERT embeddings (768-dim, ~6KB)
  - Mel spectrogram (compressed, ~50KB)
  - age_days (continuous)
  - Model's predicted emotion + confidence
- Store in S3 under `training-features/{feature_id}/`
- DynamoDB training_features table: metadata + S3 path
- NOT linked to child_id (anonymization happens at feedback time in Phase 3)

## Infrastructure (Terraform)

```hcl
# SageMaker Serverless Endpoint for HuBERT
resource "aws_sagemaker_model" "hubert" {
  name               = "qleam-hubert"
  execution_role_arn = aws_iam_role.sagemaker_role.arn

  primary_container {
    image          = "763104351884.dkr.ecr.us-east-1.amazonaws.com/huggingface-pytorch-inference:2.0-transformers4.28-cpu-py310-ubuntu20.04"
    model_data_url = "s3://${aws_s3_bucket.models.id}/hubert/model.tar.gz"
    environment = {
      HF_MODEL_ID = "facebook/hubert-base-ls960"
      HF_TASK     = "feature-extraction"
    }
  }
}

resource "aws_sagemaker_endpoint_configuration" "hubert" {
  name = "qleam-hubert-config"

  production_variants {
    variant_name = "default"
    model_name   = aws_sagemaker_model.hubert.name

    serverless_config {
      memory_size_in_mb       = 4096
      max_concurrency         = 5
      provisioned_concurrency = 0  # Scale to zero
    }
  }
}

resource "aws_sagemaker_endpoint" "hubert" {
  name                 = "qleam-hubert-endpoint"
  endpoint_config_name = aws_sagemaker_endpoint_configuration.hubert.name
}

# DynamoDB table for training feature metadata
resource "aws_dynamodb_table" "training_features" {
  name         = "qleam-training-features"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "feature_id"

  attribute {
    name = "feature_id"
    type = "S"
  }

  global_secondary_index {
    name            = "sound_type-age_days-index"
    hash_key        = "sound_type"
    range_key       = "age_days"
    projection_type = "ALL"
  }

  attribute {
    name = "sound_type"
    type = "S"
  }

  attribute {
    name = "age_days"
    type = "N"
  }
}

# IAM role for SageMaker
resource "aws_iam_role" "sagemaker_role" {
  name = "qleam-sagemaker-hubert-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "sagemaker.amazonaws.com" }
    }]
  })
}

# Lambda permission to invoke SageMaker endpoint
resource "aws_iam_role_policy" "lambda_sagemaker_invoke" {
  name = "qleam-lambda-sagemaker-invoke"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sagemaker:InvokeEndpoint"
      Resource = aws_sagemaker_endpoint.hubert.arn
    }]
  })
}
```

## Cost Analysis

| Component | Cost | When |
|---|---|---|
| SageMaker Serverless (HuBERT) | ~$0.0001-0.0003 per inference | Only for baby sounds (~40% of uploads) |
| SageMaker Serverless idle | $0 | Scales to zero |
| Lambda (GATE + classifier) | ~$0.00001 per invocation | Every upload |
| S3 (embeddings storage) | ~$0.023/GB/month | Minimal |
| DynamoDB | Pay per request | Minimal |

For 1000 sessions/month: ~$0.30-1.00 for SageMaker. Negligible.

## Files Changed
- CREATE: shared/hubert_client.py (SageMaker client), shared/emotion_classifier.py (TFLite inference), scripts/pretrain_classifier.py, scripts/prepare_datasets.py
- MODIFY: feature_extraction/handler.py (call SageMaker after gate), insight_generator/handler.py (use classifier output)
- KEEP (simplified): shared/cry_analyzer.py (Dunstan mapping for 0-3m display only)
- TERRAFORM: SageMaker endpoint, DynamoDB table, IAM roles

## Success Criteria
- HuBERT endpoint returns 768-dim embeddings for any audio clip
- SageMaker cold start <5s, warm inference <1s
- Pre-trained classifier achieves 60-75% accuracy on 7 emotion classes
- End-to-end pipeline: upload -> emotion result in 4-8 seconds
- Embeddings stored for every baby sound session (Phase 3 ready)
- Old hand-tuned cry_analyzer scoring no longer used for classification

## Deploy
- Workflows: `1-infra-deploy` (SageMaker endpoint, DynamoDB table, IAM) then `2-lambda-deploy`
