# Qleam: AI-Powered Baby Sound Analysis — Technical Deep Dive

## From Rule-Based Heuristics to Self-Learning ML Pipeline

**Version**: 1.0 — March 2026
**Architecture**: Serverless AWS (Lambda, Step Functions, SageMaker, DynamoDB, S3)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Problem with Rule-Based Baby Cry Analysis](#2-the-problem-with-rule-based-baby-cry-analysis)
3. [The 6-Layer Architecture](#3-the-6-layer-architecture)
4. [Phase 1: Pipeline Cleanup & Early Rejection Gate](#4-phase-1-pipeline-cleanup--early-rejection-gate)
5. [Phase 2: HuBERT Feature Extraction](#5-phase-2-hubert-feature-extraction)
6. [Phase 3: Self-Training Pipeline](#6-phase-3-self-training-pipeline)
7. [Phase 4: Age-Continuous Emotion Classifier](#7-phase-4-age-continuous-emotion-classifier)
8. [Phase 5: Dynamic Conversational UI](#8-phase-5-dynamic-conversational-ui)
9. [Phase 6: Privacy & GDPR/COPPA Compliance](#9-phase-6-privacy--gdpaccoppa-compliance)
10. [Infrastructure & Deployment](#10-infrastructure--deployment)
11. [Cost Analysis](#11-cost-analysis)
12. [Dataset Strategy & Licensing](#12-dataset-strategy--licensing)
13. [File Reference](#13-file-reference)

---

## 1. Executive Summary

Qleam is a mobile application that analyzes baby sounds (crying, babbling, laughing) and provides parents with real-time insights about what their baby might need. The modernization transformed it from a fragile, hand-tuned rule system into a self-improving ML pipeline.

### Before Modernization
- 65-feature extraction on every recording (slow, ~13-25 seconds)
- Hand-tuned Bayesian evidence model with arbitrary profiles and priors
- ~3,000 lines of dead code across unused modules
- Static template-based UI (same advice every time)
- No real machine learning (nearest-centroid classifier never activated)
- No data validation (accepted all recordings indiscriminately)

### After Modernization
- Early rejection gate rejects silence/noise/adult in <2 seconds
- HuBERT transformer extracts 768-dimensional contextual embeddings
- Self-training pipeline learns from parent feedback automatically
- Age-continuous classifier (no arbitrary developmental boundaries)
- Dynamic conversational UI with radar charts and Dunstan reference
- Full GDPR/COPPA compliance with cascade deletion

### Key Technical Decisions
- **HuBERT over YAMNet/wav2vec2**: Sep 2025 research showed HuBERT outperforms alternatives for infant cry classification
- **SageMaker Serverless**: Scales to zero ($0 idle), ~$0.01/call when active
- **Numpy-only training**: No TensorFlow/PyTorch dependency in Lambda — pure numpy backpropagation
- **Age as continuous input**: No arbitrary age slots (0-3m, 3-6m) — model learns smooth developmental transitions from data
- **Dual-mode extraction**: Librosa (free, in-Lambda) when SageMaker is off; HuBERT when on

---

## 2. The Problem with Rule-Based Baby Cry Analysis

The original system computed F0 (fundamental frequency) 5 times and RMS (volume) 4 times across different modules. It used:

- **Compound rules**: "IF F0 > 400Hz AND duration > 5s AND spectral_centroid < 2000 THEN gas_pain_probability += 0.3"
- **Age profiles**: Hand-tuned scoring tables for each developmental stage
- **Bayesian priors**: Hard-coded probability distributions from research papers
- **Conflict resolution**: When rules contradicted each other, another layer of rules resolved them

This approach had fundamental problems:
1. **Fragile**: Change one threshold and the entire scoring chain breaks
2. **Non-learning**: Every baby is different, but the system treats them all the same
3. **Research-dependent**: When new papers contradicted old ones, manual updates were needed
4. **Slow**: Full 65-feature extraction for every recording, even silence

---

## 3. The 6-Layer Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    COMPLETE SYSTEM                        │
│                                                           │
│  1. GATE (Early Rejection)                               │
│     Lightweight acoustic checks: silence? adult? noise?  │
│     Rejects non-baby sounds in <2 seconds                │
│     Runs on: Lambda (pennies)                            │
│                                                           │
│  2. EARS (Feature Extraction — HuBERT)                   │
│     Input: raw audio waveform                            │
│     Output: 768-dimensional contextual embeddings        │
│     Runs on: SageMaker Serverless (scales to zero)       │
│                                                           │
│  3. BRAIN (Classification)                               │
│     Small neural network: embeddings + age → emotion     │
│     Pre-trained on public datasets (3,500+ samples)      │
│     Runs on: Lambda (<1s inference)                      │
│                                                           │
│  4. LEARNING (Self-Training)                             │
│     Parent confirms/corrects → quality gates → anonymize │
│     Auto-retrain when sample threshold reached           │
│     Runs on: Step Functions + Lambda                     │
│                                                           │
│  5. INSIGHT (Parent-Facing)                              │
│     Dynamic conversational narrative                     │
│     Radar charts (emotion match + acoustic features)     │
│     Context-aware suggestions                            │
│     Runs on: Lambda + React frontend                     │
│                                                           │
│  6. PRIVACY (Data Protection)                            │
│     Cascade deletion on child removal                    │
│     Anonymized training data survives deletion           │
│     S3 lifecycle: Glacier → auto-delete                  │
└─────────────────────────────────────────────────────────┘
```

### Execution Flow

```
Audio Upload → S3                              ~1-3s
  → Lambda: GATE                               ~1-2s
     (quality check, silence/adult rejection)
     │
  → SageMaker Serverless: EARS                 ~0.3-0.8s
     (HuBERT 768-dim embeddings)
     │
  → Lambda: BRAIN                              ~0.05s
     (classifier: embeddings + age_days)
     │
  → Lambda: INSIGHT                            ~1-2s
     (format for parent)
     │
  → Frontend polling                           ~1-2s
                                           ─────────
  TOTAL                                        ~4-8 seconds
```

---

## 4. Phase 1: Pipeline Cleanup & Early Rejection Gate

### What Was Removed
- `evidence_model.py` — Bayesian evidence scoring (hand-tuned priors)
- `federated_learning.py` — Unused federated aggregation module
- `concept_graph.py` — Dead conceptual mapping system
- Redundant F0/RMS computations across modules
- FeatureChart component (displayed scores from unused evidence_model)

### Early Rejection Gate

The gate runs before any expensive processing. It checks:

```python
def _check_early_rejection(audio, sr):
    """Reject non-baby sounds in <2 seconds."""

    # 1. Silence detection (RMS < threshold)
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < SILENCE_THRESHOLD:
        return {"fast_reject": True, "reason": "silence"}

    # 2. Duration check (too short = noise burst)
    duration = len(audio) / sr
    if duration < MIN_DURATION:
        return {"fast_reject": True, "reason": "too_short"}

    # 3. Adult voice detection (F0 range check)
    f0 = estimate_fundamental_frequency(audio, sr)
    if f0 < BABY_F0_MIN:  # Below baby vocal range
        return {"fast_reject": True, "reason": "adult_voice"}

    return {"fast_reject": False}
```

When fast_reject is True, the Step Function routes directly to InsightGenerator with a "sorry, couldn't analyze" message. No HuBERT, no classification, no training data stored.

### Core Features Consolidation

The `shared/core_features.py` module provides a single unified feature extraction pipeline, replacing 5 scattered implementations.

**Key files:**
- `lambdas/feature_extraction/handler.py` — Main Lambda handler
- `shared/core_features.py` — Consolidated feature extraction
- `shared/sound_classifier.py` — Sound type classification (cry/speech/laugh/noise)

---

## 5. Phase 2: HuBERT Feature Extraction

### Why HuBERT?

HuBERT (Hidden-Unit BERT) is a self-supervised speech representation model developed by Meta AI. September 2025 research specifically demonstrated its superiority for infant cry classification:

- **768-dimensional contextual embeddings** capture temporal dynamics of crying
- **Pre-trained on 960 hours of speech** — understands acoustic structure without baby-specific training
- **Outperforms YAMNet** (Google's audio event classifier) which produces generic 1024-dim embeddings
- **Outperforms wav2vec2** on infant cry tasks specifically

### SageMaker Serverless Deployment

```hcl
# infrastructure/modules/sagemaker/main.tf

resource "aws_sagemaker_endpoint_configuration" "hubert" {
  production_variants {
    variant_name = "default"
    model_name   = aws_sagemaker_model.hubert[0].name

    serverless_config {
      memory_size_in_mb = 3072    # Account quota limit
      max_concurrency   = 5       # Max parallel invocations
    }
  }
}
```

**Serverless means:**
- $0 when idle (no provisioned instances)
- Cold start ~10-15 seconds on first call after idle
- ~0.3-0.8 seconds per inference after warm
- Scales automatically up to max_concurrency
- ~$0.01 per invocation (compute time × memory)

### HuBERT Client

```python
# shared/hubert_client.py

def extract_hubert_embeddings(audio, sr, endpoint_name):
    """Extract 768-dim HuBERT embeddings via SageMaker."""
    # Resample to 16kHz (HuBERT requirement)
    if sr != 16000:
        audio = resample(audio, sr, 16000)

    # Invoke SageMaker endpoint
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=json.dumps({"inputs": audio.tolist()})
    )

    # Parse 768-dim embedding (mean-pooled across time)
    hidden_states = json.loads(response["Body"].read())
    embedding = np.mean(hidden_states[0], axis=0)  # [T, 768] → [768]

    return {"embeddings": embedding, "dim": 768}
```

### Dual-Mode Feature Extraction

The system works with or without SageMaker:

| SageMaker | Feature Extraction | Training Data | Quality |
|---|---|---|---|
| OFF (`false`) | Librosa: MFCC, F0, spectral | Not collected | Good (rule-based) |
| ON (`true`) | HuBERT 768-dim + librosa | Stored in S3 + DynamoDB | Better (ML-based) |

Toggle: `use_sagemaker_intent_endpoint = true/false` in `terraform.tfvars`

### Emotion Classifier

```python
# shared/emotion_classifier.py

EMOTION_CLASSES = ["hungry", "tired", "discomfort", "gas", "pain", "burp", "content"]

def predict_emotion(embeddings, age_days, model_versions_table=None):
    """
    Predict cry emotion from HuBERT embeddings + age.

    Blends Phase 2 (public dataset) and Phase 3 (our trained) models
    based on how much confirmed training data we have.
    """
    # Try Phase 3/4 numpy model first (from ModelVersions table)
    numpy_model = load_numpy_model(model_versions_table)

    if numpy_model:
        # Two-branch inference: embeddings + age encoding
        age_enc = encode_age(age_days)
        scores = numpy_forward(numpy_model, embeddings, age_enc)
        return {emotion: float(score) for emotion, score in zip(EMOTION_CLASSES, scores)}

    # Fallback to Phase 2 TFLite model (pre-trained on public data)
    tflite_model = load_model()
    if tflite_model:
        scores = tflite_inference(tflite_model, embeddings)
        return {emotion: float(score) for emotion, score in zip(EMOTION_CLASSES, scores)}

    # No model available — return uniform distribution
    return {emotion: 1.0 / len(EMOTION_CLASSES) for emotion in EMOTION_CLASSES}
```

---

## 6. Phase 3: Self-Training Pipeline

This is the heart of Qleam's intelligence — the system learns from every parent interaction.

### Data Flow

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Parent uses   │────>│ feature_extraction│────>│ TrainingFeatures │
│ the app       │     │ Lambda           │     │ DynamoDB table   │
│               │     │                  │     │ (embeddings in S3)│
└──────────────┘     └──────────────────┘     └──────────────────┘
                                                       │
┌──────────────┐     ┌──────────────────┐              │
│ Parent gives  │────>│ feedback_processor│──────────────┘
│ feedback      │     │ Lambda           │   (confirms/corrects
│ "Yes hungry"  │     │                  │    + anonymizes)
└──────────────┘     └──────────────────┘
                                                       │
┌──────────────┐     ┌──────────────────┐              │
│ Daily 6AM UTC│────>│ training_check   │──────────────┘
│ EventBridge   │     │ Lambda           │   (checks if
│ schedule      │     │                  │    ≥50 new samples)
└──────────────┘     └──────────────────┘
                            │ triggers
                            ▼
              ┌──────────────────────────┐
              │ Training Step Function   │
              │                          │
              │  1. Load confirmed data  │
              │  2. Train classifier     │
              │  3. Validate accuracy    │
              │  4. Promote if better    │
              └──────────────────────────┘
                            │
                            ▼
              ┌──────────────────────────┐
              │ ModelVersions table      │
              │ v1: accuracy=0.62        │
              │ v2: accuracy=0.68 ← active│
              │ v3: ...                  │
              └──────────────────────────┘
```

### Quality Gates

Not all feedback enters training data. Four gates filter quality:

```python
# shared/training_anonymizer.py

def apply_quality_gates(session, confirmed_emotion, was_correct, table):
    # Gate 0: Must have HuBERT embeddings (SageMaker was active)
    # Gate 1: Feedback quality — explicit confirm/correct only (no "skip")
    # Gate 2: Audio quality — SNR ≥ 10dB, duration ≥ 3s, sound_type = cry/mixed
    # Gate 3: Confidence check — low-confidence confirms rejected (corrections always accepted)
    # Gate 4: Deduplication — same session can't be confirmed twice
```

**Why corrections are always accepted**: If the model predicted "hungry" with 20% confidence and the parent corrected it to "tired", that's extremely valuable training data — the model was wrong and the parent knows better. Low confidence + parent correction = highest-value sample.

### Anonymization

When a sample passes quality gates:

```python
def anonymize_and_confirm(feature_id, confirmed_emotion, was_correct, session, table):
    # UPDATE TrainingFeatures record:
    #   SET confirmed_emotion, confirmation_source, confirmed_at
    #   REMOVE session_id  ← PII stripped
    #
    # The HuBERT embedding in S3 is already anonymous (stored by feature_id, not session_id)
```

After anonymization, the training record has:
- ✅ HuBERT embeddings (S3 path)
- ✅ Confirmed emotion label
- ✅ Age at time of recording
- ✅ Audio quality metrics
- ❌ No session_id
- ❌ No child_id
- ❌ No parent_id

### Training Pipeline (Step Functions)

```
EventBridge (daily 6AM UTC)
    │
    ▼
TrainingCheck Lambda
    │ Checks: total_confirmed ≥ 30 AND
    │         (new_samples ≥ 50 OR (new_samples ≥ 10 AND days_since_last ≥ 7))
    │
    ├─ No  → TrainingSkipped (Succeed)
    │
    └─ Yes → LoadData (model_trainer step=load)
                │ Query all confirmed TrainingFeatures
                │ Load embeddings from S3
                │ Encode age_days → 4-dim vectors
                │
                ▼
             TrainModel (model_trainer step=train)
                │ Two-branch neural network (numpy-only)
                │ Embedding branch: 768 → 256 → 128
                │ Age branch: 4 → 16 → 8
                │ Concat: 136 → 64 → 7 (softmax)
                │ 50 epochs, batch_size=32, Adam-like updates
                │
                ▼
             ValidateModel (model_trainer step=validate)
                │ Compare to active model accuracy
                │ Requires ≥2% improvement margin
                │ (Or first model: just needs ≥30% accuracy)
                │
                ├─ No improvement → TrainingNoImprovement (Succeed)
                │
                └─ Better → PromoteModel (model_trainer step=promote)
                               │ Copy weights to permanent S3 path
                               │ Create ModelVersions record
                               │ Deactivate previous version
                               │ Mark training features as "included_in_training"
                               │
                               ▼
                            TrainingComplete (Succeed)
```

### Model Weight Blending

As our training data grows, the model transitions from public-dataset-trained to our-data-trained:

```python
BLEND_THRESHOLDS = [
    (0,   29,   1.0,  0.0),    # 0-29 confirmed:  100% public model, 0% ours
    (30,  99,   0.7,  0.3),    # 30-99:           70% public, 30% ours
    (100, 299,  0.4,  0.6),    # 100-299:         40% public, 60% ours
    (300, None, 0.15, 0.85),   # 300+:            15% public, 85% ours
]
```

This prevents catastrophic forgetting — the public dataset model provides a safety net until our data proves reliable.

---

## 7. Phase 4: Age-Continuous Emotion Classifier

### The Problem with Age Slots

Traditional approach: "0-3 months = newborn sounds, 3-6 months = early vocal, 6-12 months = babbling"

Problems:
- Arbitrary boundaries (why does everything change at exactly 90 days?)
- Babies develop at different rates
- Slot-averaged research hides granular patterns
- Manual updates when research changes

### Age Encoding

Instead of slots, we encode age as a 4-dimensional continuous vector:

```python
# shared/age_encoder.py

def encode_age(age_days):
    age = clamp(age_days, 0, 730)  # 0-24 months
    return np.array([
        age / 730.0,                          # Normalized 0-1
        sin(age * π / 90),                    # ~3-month developmental cycles
        sin(age * π / 180),                   # ~6-month developmental cycles
        1.0 if age < 90 else 0.0,             # Newborn hint (Dunstan reflex period)
    ])
```

**Why sinusoidal encoding?** Developmental transitions aren't linear — they're cyclical. The ~3-month cycle captures when Dunstan reflexes fade, when babbling begins, etc. The ~6-month cycle captures larger developmental shifts. The model learns the exact timing from data rather than from hard-coded boundaries.

### Two-Branch Neural Network

```
┌─────────────┐     ┌────────────┐
│ HuBERT      │     │ Age        │
│ Embedding   │     │ Encoding   │
│ (768-dim)   │     │ (4-dim)    │
└──────┬──────┘     └─────┬──────┘
       │                   │
  ┌────▼────┐         ┌───▼───┐
  │Dense 256│         │Dense 16│
  │ + ReLU  │         │+ ReLU  │
  └────┬────┘         └───┬───┘
       │                   │
  ┌────▼────┐         ┌───▼───┐
  │Dense 128│         │Dense 8 │
  │ + ReLU  │         │+ ReLU  │
  └────┬────┘         └───┬───┘
       │                   │
       └───────┬───────────┘
               │ concatenate (136-dim)
          ┌────▼────┐
          │Dense 64 │
          │ + ReLU  │
          └────┬────┘
               │
          ┌────▼────┐
          │Dense 7  │
          │+ Softmax│
          └────┬────┘
               │
    ┌──────────▼──────────┐
    │ hungry  tired  gas  │
    │ discomfort  pain    │
    │ burp  content       │
    └─────────────────────┘
```

**Why two branches?** The embedding branch processes the 768-dimensional audio representation. The age branch processes developmental context. They're concatenated so the final layers can learn interactions like "this acoustic pattern + this age = this emotion."

**Why numpy-only?** Lambda functions have a 250MB deployment limit. TensorFlow is ~500MB. PyTorch is ~800MB. Our numpy implementation is <1MB and trains a 30-sample dataset in ~10 seconds. For a small classifier with <100K parameters, numpy is sufficient.

---

## 8. Phase 5: Dynamic Conversational UI

### Before: Static Templates

```
"Your baby seems hungry. Try feeding."
"Your baby seems tired. Try putting to sleep."
```

Same text every time. No data backing. No context awareness.

### After: Dynamic Insights

The insight_generator Lambda produces a rich data structure:

```json
{
  "emotion_label": "hungry",
  "confidence": 0.82,
  "narrative": {
    "what_hearing": "Strong rhythmic 'neh' pattern with rising pitch — this is a classic hunger cry.",
    "what_means": "At 6 weeks, hunger cries peak around feeding times. The 'neh' reflex (tongue pushing to roof of mouth) is your baby's built-in signal.",
    "what_try": "Try offering a feed. If the last feed was less than an hour ago, try a comfort nurse — sometimes babies cluster feed during growth spurts."
  },
  "emotion_scores": {
    "hungry": 0.82, "tired": 0.08, "gas": 0.04,
    "discomfort": 0.03, "pain": 0.02, "burp": 0.01, "content": 0.00
  },
  "acoustic_features": {
    "pitch": 0.75, "energy": 0.82, "stability": 0.45,
    "voicing": 0.90, "brightness": 0.60, "variation": 0.35
  },
  "dunstan_sound": {
    "sound": "neh",
    "description": "Tongue pushes to roof of mouth — hunger reflex",
    "audio_url": "/dunstan/neh.mp3"
  },
  "session_context": {
    "session_count": 47,
    "child_age_days": 42,
    "time_of_day": "morning"
  }
}
```

### Frontend Components

1. **EmotionRadar** (`EmotionRadar.js`): 7-axis radar chart showing model softmax probabilities
2. **AcousticRadar** (`AcousticRadar.js`): 6-axis radar chart showing real acoustic measurements
3. **DunstanSection** (`DunstanSection.js`): Reference audio + description for Dunstan Baby Language sounds (0-6 months only)
4. **InsightPanel** (`InsightPanel.js`): Main insight display with progressive reveal animation
5. **FeedbackForm** (`FeedbackForm.js`): Parent confirm/correct/skip interface
6. **SessionCard** (`SessionCard.js`): Session history with emotion badges

---

## 9. Phase 6: Privacy & GDPR/COPPA Compliance

### Cascade Deletion

When a parent deletes a child from the app:

```
DELETE /child/{child_id}
    │
    ├── Verify parent owns this child (parent_id check)
    │
    ├── Delete Sessions (by child_id GSI)
    │   └── Delete linked Feedback records (by session_id)
    │
    ├── Delete S3 audio files (by child_id prefix)
    │
    ├── Delete Training Candidates (PII-linked)
    │
    ├── Delete Sound Clusters
    │
    ├── Delete Semantic Bridges
    │
    ├── Delete Concept Graphs
    │
    ├── Delete Milestones
    │
    └── Delete Child Profile (last)

    ✅ KEPT: TrainingFeatures (anonymized — no PII, no session_id)
    ✅ KEPT: ModelVersions (model weights — no PII)
```

### What's Kept vs Deleted

| Data | Contains PII? | On Child Delete | On Account Delete |
|---|---|---|---|
| Child profile | Yes (name, DOB) | DELETED | DELETED |
| Sessions | Yes (child_id) | DELETED | DELETED |
| Raw audio (S3) | Yes (child's voice) | DELETED | DELETED |
| Feedback | Yes (session_id) | DELETED | DELETED |
| Training candidates | Yes (session_id) | DELETED | DELETED |
| Sound clusters | Yes (child_id) | DELETED | DELETED |
| TrainingFeatures | **No** (anonymized) | KEPT | KEPT |
| ModelVersions | **No** (model weights) | KEPT | KEPT |

### S3 Lifecycle (Belt & Suspenders)

Even if cascade deletion misses something:

```hcl
# infrastructure/modules/s3/main.tf

lifecycle_rule {
  # Transition to Glacier after 90 days (configurable)
  transition {
    days          = var.audio_retention_days  # default: 90
    storage_class = "GLACIER"
  }

  # Permanent deletion after 365 days
  expiration {
    days = 365
  }

  # Clean up old versions
  noncurrent_version_expiration {
    noncurrent_days = 7
  }
}
```

### Audit Logging

All deletions are logged without PII:

```python
logger.info(
    f"AUDIT_CHILD_DELETE child_id_hash={hash(child_id)} "
    f"sessions_deleted={session_count} "
    f"feedback_deleted={feedback_count} "
    f"s3_objects_deleted={s3_count}"
)
```

---

## 10. Infrastructure & Deployment

### AWS Services Used

| Service | Purpose | Cost Model |
|---|---|---|
| Lambda (×6) | All compute | Per-invocation (~$0.20/M requests) |
| Step Functions (×2) | Pipeline orchestration | $0.025/1K transitions |
| SageMaker Serverless | HuBERT inference | $0 idle, ~$0.01/call |
| DynamoDB (×11 tables) | All persistent data | On-demand (pay per read/write) |
| S3 | Audio storage + models | $0.023/GB/month |
| EventBridge | Daily training trigger | Free for scheduled rules |
| CloudFront | Frontend CDN | $0.085/GB transfer |
| Cognito | Authentication | Free tier (50K MAU) |
| API Gateway | REST API | $3.50/M requests |

### GitHub Actions Workflows

Three workflows, in order:

1. **`1-infra-deploy`** — Terraform creates all AWS resources
   - Triggers on: `infrastructure/**` changes (push to develop)
   - Phases: Bootstrap → ECR repos → Placeholder images → SageMaker model artifact → Full apply
   - Manual approval gate before apply

2. **`2-lambda-deploy`** — Builds Docker images, pushes to ECR, updates Lambda functions
   - Triggers on: `lambdas/**`, `shared/**`, `docker/**` changes
   - Builds 6 Lambda images: feature_extraction, insight_generator, feedback_processor, api_handler, training_check, model_trainer
   - Runs tests first (pytest)

3. **`3-frontend-deploy`** — Builds React app, deploys to S3, invalidates CloudFront
   - Triggers on: `frontend/**` changes

### Lambda Functions

| Function | Memory | Timeout | Docker Base | Purpose |
|---|---|---|---|---|
| feature-extraction | 1024MB | 60s | python:3.11 + librosa | Audio analysis + HuBERT |
| insight-generator | 512MB | 60s | python:3.11 + boto3 | Narrative + Bedrock |
| feedback-processor | 512MB | 30s | python:3.11 + numpy | Feedback + anonymization |
| api-handler | 512MB | 30s | python:3.11 + boto3 | REST API routing |
| training-check | 256MB | 30s | python:3.11 + boto3 | Daily retrain check |
| model-trainer | 1024MB | 300s | python:3.11 + numpy | Neural network training |

### Terraform Module Structure

```
infrastructure/
├── environments/
│   ├── dev/
│   │   ├── main.tf          # Composes all modules
│   │   ├── variables.tf     # Environment-specific vars
│   │   └── terraform.tfvars # Dev configuration
│   └── prod/                # (Same structure)
└── modules/
    ├── vpc/                 # VPC, subnets, NAT gateway
    ├── iam/                 # Roles + policies
    ├── ecr/                 # Container registries (8 repos)
    ├── s3/                  # Audio bucket + lifecycle
    ├── dynamodb/            # 11 tables
    ├── cognito/             # User pool + app client
    ├── lambda/              # 6 Lambda functions
    ├── step_functions/      # 2 state machines + EventBridge
    ├── api_gateway/         # REST API
    ├── sagemaker/           # HuBERT endpoint (toggleable)
    ├── frontend/            # S3 + CloudFront
    └── cloudwatch/          # Alarms + dashboards
```

---

## 11. Cost Analysis

### Monthly Cost Estimate (Dev Environment)

| Component | Cost | Notes |
|---|---|---|
| Lambda (all 6) | ~$1-5 | Low traffic in dev |
| DynamoDB | ~$0-2 | On-demand, minimal reads/writes |
| S3 | ~$0.50 | Small audio files |
| SageMaker | $0 (idle) | Serverless scales to zero |
| NAT Gateway | ~$32 | Fixed cost (required for VPC) |
| CloudFront | ~$0.50 | Minimal traffic |
| API Gateway | ~$0.50 | Low request count |
| **Total** | **~$35/month** | Mostly NAT Gateway |

### Per-Recording Cost (When Active)

| Step | Cost |
|---|---|
| Lambda feature_extraction | ~$0.0001 |
| SageMaker HuBERT (if ON) | ~$0.01 |
| Lambda insight_generator | ~$0.0001 |
| Bedrock (Claude Haiku) | ~$0.001 |
| DynamoDB writes | ~$0.00001 |
| S3 storage | ~$0.00001 |
| **Total per recording** | **~$0.01** |

### Training Cost (Per Retrain Cycle)

| Step | Cost |
|---|---|
| training_check Lambda | ~$0.0001 |
| model_trainer Lambda (load) | ~$0.001 |
| model_trainer Lambda (train) | ~$0.01 |
| model_trainer Lambda (validate) | ~$0.001 |
| model_trainer Lambda (promote) | ~$0.001 |
| Step Functions | ~$0.00005 |
| **Total per retrain** | **~$0.015** |

---

## 12. Dataset Strategy & Licensing

### Available Public Datasets

| Dataset | Samples | Labels | License | Status |
|---|---|---|---|---|
| **DonateACry** | ~457 | 5 emotions | Creative Commons | Free — download script ready |
| **Dunstan Baby Language** | ~1,128 | 5 Dunstan sounds | Proprietary | Requires purchase/license |
| **Baby Chillanto** | ~2,268 | Multiple | Academic | Requires data sharing agreement |

### How to Use DonateACry (Free)

```bash
# 1. Download dataset
python scripts/download_donateacry.py

# 2. Extract HuBERT embeddings
#    Option A: Local (needs pip install transformers torch soundfile)
python scripts/pretrain_classifier.py extract-embeddings \
  --manifest data/donateacry/manifest.json --local --output data/embeddings/

#    Option B: SageMaker endpoint (needs endpoint running)
python scripts/pretrain_classifier.py extract-embeddings \
  --manifest data/donateacry/manifest.json \
  --endpoint qleam-dev-hubert-endpoint --output data/embeddings/

# 3. Train initial model
python scripts/pretrain_classifier.py train \
  --embeddings data/embeddings/ --output models/emotion_classifier.tflite

# 4. Evaluate
python scripts/pretrain_classifier.py evaluate \
  --embeddings data/embeddings/ --model models/emotion_classifier.tflite
```

### Without Any Dataset

The system works fine with zero pre-training:
1. SageMaker extracts HuBERT embeddings on each recording
2. Emotion classifier returns uniform distribution (no trained model)
3. Insight generator uses acoustic features + Bedrock for insights
4. Parents confirm/correct predictions → training data accumulates
5. After 30+ confirmed samples, self-training activates
6. Model improves progressively with each retrain cycle

---

## 13. File Reference

### Lambda Handlers
| File | Purpose |
|---|---|
| `lambdas/feature_extraction/handler.py` | Audio classification, HuBERT embedding extraction |
| `lambdas/insight_generator/handler.py` | Narrative generation, cry analysis, speech transcription |
| `lambdas/feedback_processor/handler.py` | Parent feedback processing, training data anonymization |
| `lambdas/api_handler/handler.py` | REST API routing, auth, cascade deletion |
| `lambdas/training_check/handler.py` | Daily check for retraining conditions |
| `lambdas/model_trainer/handler.py` | Neural network training, validation, promotion |

### Shared Modules
| File | Purpose |
|---|---|
| `shared/constants.py` | Environment variables and configuration |
| `shared/core_features.py` | Consolidated audio feature extraction |
| `shared/sound_classifier.py` | Sound type classification (cry/speech/laugh) |
| `shared/hubert_client.py` | SageMaker HuBERT endpoint client |
| `shared/emotion_classifier.py` | Emotion prediction (TFLite + numpy models) |
| `shared/age_encoder.py` | Continuous age encoding (4-dim) |
| `shared/cry_analyzer.py` | Cry emotion → display text mapping |
| `shared/training_anonymizer.py` | Quality gates + PII anonymization |
| `shared/audio_utils.py` | Audio loading, resampling utilities |
| `shared/speech_transcriber.py` | Amazon Transcribe integration |

### Infrastructure
| File | Purpose |
|---|---|
| `infrastructure/environments/dev/main.tf` | Dev environment composition |
| `infrastructure/environments/dev/terraform.tfvars` | Dev configuration values |
| `infrastructure/modules/lambda/main.tf` | 6 Lambda function definitions |
| `infrastructure/modules/step_functions/main.tf` | Processing + Training pipelines |
| `infrastructure/modules/sagemaker/main.tf` | HuBERT endpoint (toggleable) |
| `infrastructure/modules/dynamodb/main.tf` | 11 DynamoDB tables |
| `infrastructure/modules/ecr/main.tf` | 8 ECR repositories |
| `infrastructure/modules/s3/main.tf` | Audio bucket + lifecycle |

### Docker
| File | Purpose |
|---|---|
| `docker/feature_extraction/Dockerfile` | Librosa + numpy + scipy |
| `docker/insight_generator/Dockerfile` | Boto3 (Bedrock + Transcribe) |
| `docker/feedback_processor/Dockerfile` | Numpy + boto3 |
| `docker/api_handler/Dockerfile` | Boto3 |
| `docker/training_check/Dockerfile` | Boto3 (lightweight) |
| `docker/model_trainer/Dockerfile` | Numpy + boto3 |

### Scripts
| File | Purpose |
|---|---|
| `scripts/pretrain_classifier.py` | Extract embeddings, train, evaluate |
| `scripts/download_donateacry.py` | Download DonateACry dataset |

### Frontend
| File | Purpose |
|---|---|
| `frontend/src/components/EmotionRadar.js` | 7-emotion radar chart |
| `frontend/src/components/AcousticRadar.js` | 6-feature acoustic radar |
| `frontend/src/components/DunstanSection.js` | Dunstan Baby Language reference |
| `frontend/src/components/InsightPanel.js` | Main insight display |
| `frontend/src/components/FeedbackForm.js` | Parent feedback form |

### Tests
| File | Tests |
|---|---|
| `tests/test_age_encoder.py` | Age encoding (shapes, bounds, sinusoidal) |
| `tests/test_training_anonymizer.py` | Quality gates, blend weights |
| `tests/test_training_check.py` | Sample counting, thresholds |
| `tests/test_model_trainer.py` | Neural network (forward, backward, convergence) |

---

*This document covers the complete Qleam modernization as of March 2026. All 6 phases are fully implemented and deployed.*
