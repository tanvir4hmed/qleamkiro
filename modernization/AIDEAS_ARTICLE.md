# AIdeas: Qleam - AI Baby Sound Analysis That Learns From Every Parent

> **[COVER IMAGE NOTE: Add a hero image showing the Qleam app interface on a phone with a soft gradient background featuring sound waveforms transforming into baby emotion icons (happy, hungry, tired). Use warm, parent-friendly colors - teal/coral palette.]**

**Tags:** #aideas-2025 #daily-life-enhancement #APJC

---

## App Category

**Daily Life Enhancement**

Qleam is a daily companion for parents of babies aged 0-24 months. It turns the universal parenting question — "What does my baby need right now?" — into an AI-powered analysis that listens, learns, and gets smarter with every interaction.

---

## My Vision

Every new parent knows the feeling: your baby is crying, and you've checked everything — fed, changed, held, rocked — but the crying continues. What if your phone could listen to that cry and tell you "This sounds like a hunger cry" or "This pattern is consistent with discomfort from teething"?

That's Qleam. A parent records 5-30 seconds of their baby's sounds. Within seconds, our AI pipeline:

1. **Validates** the audio (rejects silence, background noise, adult voices)
2. **Extracts** deep acoustic features using HuBERT transformer embeddings
3. **Classifies** the emotion considering the baby's exact age in days
4. **Generates** a personalized insight with actionable suggestions
5. **Learns** from parent feedback to improve over time

What I built is not just a classifier — it's a **self-improving system**. When a parent confirms "Yes, she was hungry" or corrects "Actually, he was overtired," that feedback flows through quality gates, gets anonymized, and eventually retrains the model. The system gets smarter for every family, while never compromising any child's privacy.

### The Before and After

The original Qleam was a rule-based system: 65 hand-tuned acoustic features, hardcoded Bayesian priors from research papers, and static template responses. It took 13-25 seconds per analysis and gave the same generic advice to every parent.

The modernized Qleam uses deep learning with HuBERT embeddings, processes in 4-8 seconds, adapts to developmental stages continuously (not in arbitrary 3-month buckets), and generates dynamic conversational insights unique to each recording.

---

## Why This Matters

### The Scale of the Problem

There are approximately **140 million babies born each year** worldwide. For the first 12-18 months, before language develops, crying is a baby's primary communication channel. Research shows that babies have distinct cry patterns for hunger, pain, discomfort, tiredness, and overstimulation — but most parents can't reliably distinguish them, especially with their first child.

### The Parental Stress Factor

Studies show that **inability to interpret infant cries** is a leading contributor to parental stress, postpartum anxiety, and in extreme cases, caregiver frustration. New parents often feel helpless, cycling through every possible remedy.

### Why AI Makes Sense Here

This is a problem uniquely suited to AI:

- **Pattern recognition at scale**: Subtle acoustic differences between cry types are measurable but hard for human ears to distinguish
- **Personalization**: Every baby is different — a system that learns from each parent's feedback becomes specifically tuned to their child
- **Developmental awareness**: A 2-week-old's hunger cry sounds different from a 6-month-old's. Age-continuous modeling captures these gradual transitions
- **Privacy-first**: Baby audio is sensitive data. Our pipeline anonymizes training data so the model improves without retaining any child's recordings

### Daily Life Enhancement

Qleam fits into the daily rhythm of parenting:

- Baby starts crying at 3 AM → parent opens Qleam, records 10 seconds
- Within 5 seconds: "This sounds like a hunger pattern. Last session showed similar timing between feeds."
- Parent feeds the baby, confirms the insight
- That confirmation makes the system slightly smarter for the next time

Over weeks and months, Qleam builds a picture of each baby's patterns, giving parents increasing confidence in understanding their child.

---

## How I Built This

### Architecture Overview

Qleam is a fully serverless application on AWS, designed for zero idle cost and automatic scaling.

```
┌──────────────────────────────────────────────────────────────┐
│                     QLEAM ARCHITECTURE                        │
│                                                                │
│  ┌─────────┐    ┌──────────┐    ┌──────────────┐             │
│  │ React   │───▶│ API      │───▶│ Step         │             │
│  │ Frontend│◀───│ Gateway  │    │ Functions    │             │
│  │ (S3+CF) │    │ +Cognito │    │ Orchestrator │             │
│  └─────────┘    └──────────┘    └──────┬───────┘             │
│                                         │                      │
│  ┌──────────────────────────────────────┼──────────────────┐  │
│  │              Processing Pipeline      │                  │  │
│  │                                       ▼                  │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────┐             │  │
│  │  │ GATE    │─▶│ EARS     │─▶│ BRAIN      │             │  │
│  │  │ Lambda  │  │ SageMaker│  │ Lambda     │             │  │
│  │  │ <2s     │  │ HuBERT   │  │ Classifier │             │  │
│  │  └─────────┘  └──────────┘  └─────┬──────┘             │  │
│  │                                     │                    │  │
│  │                                     ▼                    │  │
│  │  ┌─────────────┐           ┌────────────┐               │  │
│  │  │ LEARNING    │◀──────────│ INSIGHT    │               │  │
│  │  │ Self-Train  │  feedback │ Generator  │               │  │
│  │  │ Step Func.  │           └────────────┘               │  │
│  │  └─────────────┘                                        │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Storage: DynamoDB (7 tables) │ S3 (audio) │ ECR (8 imgs)│  │
│  └──────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

### The 6-Phase Modernization

I rebuilt the entire system across 6 phases, each adding a critical capability:

#### Phase 1: Pipeline Cleanup & Early Rejection Gate

**Problem**: The old system processed every recording identically, even silence or adult voices.

**Solution**: A 3-layer rejection gate runs before any expensive processing:

1. **Audio Quality Gate** — checks SNR (>6 dB), vocal activity (>5%), clipping, silence ratio
2. **Critical Issues Check** — detects adult voices via F0/VTL biometric validation
3. **Post-Classification Reject** — catches noise/chaotic patterns after initial classification

Recordings that fail any gate get a friendly rejection message within 2 seconds, saving compute costs and avoiding misleading results.

**Key decision**: I relaxed the noise thresholds (SNR from 10 dB to 6 dB, vocal activity from 8% to 5%) after real-world testing showed the original values were too aggressive for typical home environments with TV, siblings, or outdoor recordings.

#### Phase 2: HuBERT Feature Extraction

**Problem**: Hand-crafted features (MFCCs, spectral centroid, zero-crossing rate) capture surface-level acoustics but miss the contextual patterns that distinguish cry types.

**Solution**: HuBERT (Hidden-Unit BERT), a self-supervised speech representation model, running on SageMaker Serverless Inference:

- Converts raw audio waveform into **768-dimensional contextual embeddings**
- Captures temporal patterns, harmonic structure, and vocal characteristics
- SageMaker Serverless scales to zero when idle ($0 cost) and spins up in ~0.3s
- **Dual-mode**: When SageMaker is off, the system falls back to librosa-based feature extraction (still functional, just less accurate)

#### Phase 3: Self-Training Pipeline

**Problem**: A static model trained on public datasets doesn't adapt to the diversity of real-world baby sounds.

**Solution**: A complete self-training loop:

```
Parent Feedback                     Quality Gates                 Training
     │                                   │                           │
     ▼                                   ▼                           ▼
 "She was     ──▶  Confidence check  ──▶  Anonymize   ──▶  Daily check:
  hungry"         SNR > 6dB?             Strip PII        50 new samples?
                  Duration > 3s?         Blend weights     ──▶ Retrain
                  Sound = cry?           Age-encode            Validate
                  Confidence > 30%?                            Promote
```

The infrastructure includes:
- **EventBridge rule**: Triggers training check daily at 6 AM UTC
- **Step Function**: 7-state training pipeline (Check → Load → Train → Validate → Promote)
- **Numpy-only neural network**: No TensorFlow/PyTorch dependency — pure numpy forward/backward pass runs in Lambda
- **Model versioning**: Each trained model gets a version number; promotion only happens if validation accuracy improves

**Key design decision**: I chose numpy-only backpropagation to keep the training Lambda at 1 GB memory (vs. 3-10 GB for PyTorch). The network is small enough (~50K parameters) that numpy is fast and the code is fully transparent.

#### Phase 4: Age-Continuous Emotion Classifier

**Problem**: Traditional approaches bin babies into age groups (0-3m, 3-6m, etc.), creating artificial boundaries. A baby doesn't suddenly change at exactly 91 days.

**Solution**: A two-branch neural network that treats age as a continuous input:

```
Branch 1: Embedding Path          Branch 2: Age Path
768-dim HuBERT embedding          4-dim age encoding
     │                                 │
   Dense(256) + ReLU               Dense(16) + ReLU
   Dense(128) + ReLU               Dense(8) + ReLU
     │                                 │
     └──────────── Concat ─────────────┘
                    │
              Dense(64) + ReLU
              Dense(7) + Softmax
                    │
              7 emotions: hunger, pain, discomfort,
              tiredness, overstimulation, boredom, gas
```

The age encoding uses 4 dimensions:
- `age_days / 730` — normalized linear age
- `sin(age * pi/90)` — captures ~3-month developmental cycles
- `sin(age * pi/180)` — captures ~6-month developmental cycles
- `1.0 if age < 90 else 0.0` — newborn flag (Dunstan reflex period)

This lets the model smoothly learn that a 89-day-old and 91-day-old are nearly identical, while a 30-day-old and 300-day-old are very different.

#### Phase 5: Dynamic Conversational UI

**Problem**: Static template responses ("Your baby might be hungry. Try feeding.") feel robotic and don't match the emotional moment of a worried parent.

**Solution**: Dynamic insight generation that creates unique, conversational narratives:

- **Emotion radar chart**: Visual display of top emotion probabilities
- **Acoustic feature radar**: Shows rhythm, repetition, emotional intensity, expressive flow
- **Dunstan Sound Reference**: Maps detected sounds to the Dunstan Baby Language system (Neh = hungry, Owh = tired, etc.)
- **Contextual suggestions**: Different advice based on emotion + age combination
- **Speaker detection badge**: Shows whether the recording captured baby sounds or adult voice

> **[SCREENSHOT NOTE: Add screenshot of the Insight page showing the radar charts, emotion classification, Dunstan sound mapping, and conversational narrative. Show both a "cry detected" result and an "adult voice detected" result side by side.]**

#### Phase 6: Privacy & GDPR/COPPA Compliance

Baby audio is among the most sensitive data imaginable. The privacy system includes:

- **Cascade deletion**: Removing a child profile deletes ALL related data (sessions, clusters, bridges, feedback, S3 audio) across 6 DynamoDB tables and S3
- **Account deletion**: One-click removal of everything tied to a parent
- **Training data anonymization**: Confirmed feedback is stripped of all PII before entering the training pool. The anonymized embeddings contain no identifying information.
- **S3 lifecycle**: Audio files transition to Glacier after 30 days and auto-delete after 90 days
- **Separation**: Training features survive child deletion (they're anonymized), but raw audio and session records are permanently removed

### Infrastructure as Code

Everything is managed through Terraform:

- **8 Lambda functions** in Docker containers (ECR), each with specific memory/timeout tuning
- **7 DynamoDB tables** with GSIs for efficient querying
- **2 Step Functions** (processing pipeline + training pipeline)
- **API Gateway** with Cognito authentication (11 routes)
- **SageMaker Serverless endpoint** for HuBERT inference
- **CloudFront + S3** for frontend hosting
- **EventBridge** for daily training schedule

CI/CD runs through 3 GitHub Actions workflows:
1. `1-infra-deploy` — Terraform apply
2. `2-lambda-deploy` — Build Docker images, push to ECR, update Lambda functions
3. `3-frontend-deploy` — Build React app, sync to S3, invalidate CloudFront

### Key Development Milestones

| Milestone | What Changed |
|-----------|-------------|
| Pipeline Cleanup | Removed ~3,000 lines of dead code (evidence_model, federated_learning, concept_graph) |
| Early Rejection Gate | 3-layer quality check rejects bad recordings in <2s |
| HuBERT Integration | 768-dim embeddings via SageMaker Serverless ($0 idle) |
| Self-Training Loop | 7-state Step Function with EventBridge trigger |
| Numpy Neural Network | Two-branch age-conditioned classifier, no heavy ML framework |
| Age-Continuous Model | 4-dim sinusoidal age encoding replaces arbitrary age bins |
| Dynamic UI | Conversational insights with radar charts and Dunstan reference |
| Privacy Compliance | Cascade deletion across all tables + S3 lifecycle |
| Noise Threshold Tuning | SNR 10→6 dB, vocal activity 8%→5% for real-world conditions |
| SageMaker Status Badge | Parents see "Basic" vs "Advanced" AI mode in dashboard |
| Training Contribution Counter | Parents see how their feedback helps improve the AI |
| Dead Code Removal | Stripped unused session context feature (collected but never analyzed) |

---

## Demo

### Dashboard — Child Selection & Recording

> **[SCREENSHOT NOTE: Add screenshot of the Dashboard page showing:
> - Child selector buttons at top with settings gear icon
> - AI Mode badge ("AI Mode: Basic" or "AI Mode: Advanced")
> - "Record a Session" section with the record button
> - Training contribution counter ("Your baby contributed X samples to our AI")
> - Latest Insight panel showing a recent analysis summary
> - Session History grid with color-coded session cards]**

### Recording Flow

> **[SCREENSHOT NOTE: Add screenshot sequence (3 images side by side):
> 1. Idle state — showing the "Start Recording" button
> 2. Recording state — showing the pulsing dot, timer "Recording... 8s / 30s", and stop button
> 3. Uploading state — showing "Uploading and processing..." spinner]**

### Insight Page — Cry Analysis Result

> **[SCREENSHOT NOTE: Add screenshot of a cry analysis result showing:
> - Speaker badge ("Baby detected")
> - Headline with emotion icon (e.g., "Sounds like hunger")
> - Emotion radar chart showing probability distribution
> - Acoustic feature radar (rhythm, repetition, intensity, flow)
> - Dunstan sound section (e.g., "Neh — I'm hungry")
> - Conversational narrative with suggestions
> - Feedback buttons for parent confirmation]**

### Insight Page — Non-Cry Results

> **[SCREENSHOT NOTE: Add screenshot showing:
> - Adult voice detection with orange badge and friendly message
> - OR a noise rejection with explanation
> - OR a babbling/laughing detection with different visualization]**

### Settings Panel

> **[SCREENSHOT NOTE: Add screenshot of the Settings panel showing:
> - Add a child form (name, date of birth, gender)
> - Remove a child flow with safety confirmation (type name to confirm)]**

### Session Detail with Feedback

> **[SCREENSHOT NOTE: Add screenshot of a session detail page showing:
> - Full insight narrative
> - Feedback form with emotion options
> - "Was this correct?" confirmation
> - Notes field for parent context]**

---

## What I Learned

### 1. Real-World Audio Is Messy

The biggest lesson was that lab-quality thresholds don't work in living rooms. My initial noise detection (SNR > 10 dB, vocal activity > 8%) rejected a huge percentage of real recordings. Babies cry in cars, in kitchens with the dishwasher running, with siblings playing. I had to progressively relax thresholds to find the sweet spot between rejecting garbage and accepting imperfect-but-usable audio. The final values (SNR > 6 dB, vocal activity > 5%) were discovered through iterative testing.

### 2. Dead Code Accumulates Faster Than You Think

The original codebase had a "session context" feature where parents could tag recordings with feeding time, health state, and environment. It had sophisticated age-adaptive UI (different options for newborns vs. 6-month-olds), thorough backend validation with alias mapping, and data storage throughout the pipeline. The problem? The insight generator — the only system that would actually use this data — never read it. It was a complete dead data path: collected, validated, stored, forwarded through 3 Lambda functions, and never consumed. This taught me to always trace data flow end-to-end before building features.

### 3. You Don't Need PyTorch for Everything

The decision to implement backpropagation in pure numpy was controversial (even in my own head). But the practical benefits were enormous:

- Lambda memory: 1 GB instead of 3-10 GB
- Cold start: ~2s instead of ~15s
- Docker image: ~200 MB instead of ~2 GB
- Cost: ~$0.002/training run instead of ~$0.02

For a small network (~50K parameters), numpy is perfectly adequate. The code is also more transparent — every gradient computation is visible, not hidden behind autograd.

### 4. Age Is Continuous, Not Categorical

One of the most impactful architectural decisions was encoding age as a continuous 4-dimensional vector instead of categorical bins. Traditional systems say "0-3 months" and "3-6 months" — but a baby at 89 days is nearly identical to one at 91 days. The sinusoidal encoding captures developmental cycles naturally, and the newborn flag captures the Dunstan reflex period (0-90 days) where certain cry sounds have well-documented physiological causes.

### 5. Privacy-First Architecture Requires Upfront Design

Adding GDPR/COPPA compliance retroactively would have been a nightmare. Because I designed the anonymization pipeline from the start, training data is cleanly separated from personal data. When a parent deletes their child's profile, the cascade deletion removes everything personal, but the anonymized training contributions (which contain only acoustic embeddings and age encodings — no audio, no names, no identifiers) survive. This means the AI keeps learning even as individual data is deleted.

### 6. Serverless Can Do ML — With Creative Constraints

Running ML inference and training on serverless infrastructure required creative engineering:

- **SageMaker Serverless** for HuBERT: scales to zero ($0 idle), provisions on demand
- **Lambda** for classification: numpy-only inference runs in <50ms
- **Lambda** for training: numpy backpropagation with 1 GB memory, 5-minute timeout
- **Step Functions** for orchestration: handles the complexity of multi-step pipelines with error handling and retries

The constraint of serverless forced better architecture. No always-on GPU means the system naturally optimizes for efficiency.

### 7. Dual-Mode Architecture Enables Gradual Rollout

The SageMaker toggle (`use_sagemaker_intent_endpoint`) enables a "Basic" mode (librosa features, no training data collection) and "Advanced" mode (HuBERT embeddings, self-training active). This means:

- The system works from day one without any ML infrastructure
- SageMaker can be enabled when there's budget or user demand
- Parents see which mode they're in via the AI Mode badge
- Rollback is instant if SageMaker has issues

### 8. Let Parents See Their Impact

Adding the training contribution counter ("Your baby contributed 12 samples to our AI — 847 total across all families") was a small feature with outsized impact. It transforms parents from passive users into active participants in improving the technology. When parents see their feedback counts, they're more motivated to confirm or correct predictions, creating a virtuous cycle of data quality and model improvement.

---

## Technical Summary

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | React + AWS Amplify | Parent-facing UI |
| Auth | Cognito User Pools | Authentication + JWT |
| API | API Gateway + Lambda | RESTful endpoints (11 routes) |
| Processing | Step Functions + Lambda | Audio analysis pipeline |
| ML Inference | SageMaker Serverless | HuBERT feature extraction |
| ML Training | Lambda (numpy) | Self-training neural network |
| Storage | DynamoDB (7 tables) + S3 | Structured data + audio files |
| Infrastructure | Terraform | All resources as code |
| CI/CD | GitHub Actions (3 workflows) | Automated deploy pipeline |
| Monitoring | CloudWatch + X-Ray | Logs, metrics, tracing |

**Total Lambda functions**: 8 (api_handler, feature_extraction, insight_generator, feedback_processor, training_check, model_trainer + 2 supporting)

**Total infrastructure cost at idle**: ~$0/month (serverless scales to zero)

**Total infrastructure cost at moderate use** (~100 recordings/day): ~$15-25/month

---

*Built with serverless AI on AWS. Every baby deserves to be understood.*
