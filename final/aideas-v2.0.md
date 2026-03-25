# AIdeas: QLEAM AI - From Cry to Clarity with a Self-Learning Pipeline

Team Name: Qlitch  
Category: Daily Life Enhancement  
Cover Image: **Image: Cover - QLEAM AI architecture + live insight screen**  
Tags: `#aideas-2025` `#daily-life-enhancement` `#APJC`

## App category
Daily Life Enhancement

QLEAM AI belongs to Daily Life Enhancement because it helps parents handle one of the hardest daily moments: understanding cry signals in real time and responding with confidence.

## My vision
I build QLEAM AI as a practical interpreter for early childhood communication (ages 0-2). The app translates short audio sessions into structured, explainable insights and improves over time from validated parent feedback.

The product vision is not only detection. The vision is a learning system that becomes more personalized and more reliable as real-world family data quality improves.

## Why this matters
Early cry communication is high-frequency, high-stress, and often ambiguous. In real life, this creates repeated guesswork loops for caregivers.

QLEAM AI matters because it provides:
- immediate signal interpretation from each session,
- consistent logic instead of random trial-and-error,
- a self-learning pipeline that upgrades model behavior from confirmed outcomes.

This turns a daily emotional challenge into a measurable feedback cycle.

## How I built this

### 1) Architecture Overview
QLEAM AI runs on a serverless AWS architecture built for low-latency audio inference and continuous model improvement.

The React frontend records short audio samples (typically 5-30 seconds) and uploads them to Amazon S3 through pre-signed URLs. API Gateway + Lambda handle authentication, session lifecycle, and ownership checks.

AWS Step Functions orchestrates two core stages:
- `feature_extraction`: decoding, quality gating, diarization, acoustic computation, and optional embedding inference
- `insight_generator`: cry/speech/laugh routing, emotion synthesis, and final parent-facing insight payload

Learning services run as separate control loops:
- `feedback_processor`: validates caregiver confirmations/corrections
- `training_check`: evaluates retraining readiness from confirmed sample growth
- `model_trainer`: load -> train -> validate -> promote model versions

Core infrastructure:
- Amazon Cognito
- Amazon API Gateway
- AWS Lambda
- AWS Step Functions
- Amazon S3
- Amazon DynamoDB
- Amazon SageMaker (HuBERT embedding inference)

### 2) Session-Time Inference Pipeline
Each recording passes through a structured inference graph.

1. **Quality gating first**
Audio is decoded and tested for duration, silence ratio, clipping, voiced activity, and SNR. If quality is poor, QLEAM AI returns a rejection insight instead of a potentially misleading interpretation.

2. **Acoustic preprocessing**
Energy-based diarization isolates likely baby segments. Lightweight denoising and pre-emphasis improve signal quality before feature extraction.

3. **Acoustic intelligence path (deterministic)**
The system computes interpretable features such as:
- `f0_mean`, pitch instability, voiced fraction
- RMS/energy variability
- spectral centroid/flatness/rolloff
- rhythmic signals (syllable rate, burst behavior)

These features drive sound-type routing (`cry`, `speech`, `laugh`, `silence`, `noise`, `mixed`) and rule-based cry analysis.

4. **Advanced embedding path (model-based)**
For cry-relevant audio, HuBERT on SageMaker produces frame embeddings and mean-pools them into a 768-dimensional representation. That vector feeds the emotion classifier.

If the advanced path is unavailable or fails, QLEAM AI automatically falls back to deterministic acoustic analysis.

### 3) Insight Generation
Insights combine probabilistic modeling with explainable acoustic evidence.

- If classifier output is valid, emotion is selected from model probabilities.
- If not, rule-based cry scoring compares acoustic features against emotion profiles and normalizes scores.

The insight payload includes:
- emotion distribution and confidence
- acoustic evidence profile (pitch, intensity, stability, brightness, variation)
- alternatives/ambiguity signals
- caregiver-facing guidance

For visualization, values are normalized into emotion radar and acoustic profile charts. This keeps output interpretable and auditable rather than black-box only.

### 4) Self-Learning Dataset and Daily Growth
QLEAM AI uses a feedback-verified learning pipeline instead of training directly on raw session predictions.

Each eligible cry session can create a training candidate containing:
- embedding vector reference
- acoustic feature summary
- predicted label + confidence
- quality metadata

Candidates become confirmed training data only after gate checks pass:
- valid caregiver feedback
- minimum audio quality
- correct sound-type scope
- confidence-policy checks for "was correct"
- deduplication protection

After acceptance, records are anonymized and promoted into the training pool.

Retraining is day-scheduled and threshold-based (minimum pool size + new confirmed sample growth), so model updates are controlled rather than noisy.

Operational note: because retraining uses day-based windows and thresholds, sparse-feedback periods can create timing edge cases where useful samples wait for the next qualifying window. We track this explicitly (including month-boundary lag patterns such as 59/61-day style gaps) to reduce perceived data loss and improve retrain cadence.

### 5) Legacy Research Datasets and Modernization
QLEAM AI starts from pre-2025 public cry research priors (baseline signal behavior), then modernizes performance with continuously confirmed real-world samples.

In production behavior, the model confidence layer is not static:
- legacy baseline stabilizes early-stage behavior
- confirmed daily samples progressively increase influence
- blending gradually shifts weight toward self-learned data as evidence accumulates

This avoids discarding prior science while preventing the model from staying frozen in controlled-lab assumptions.

Research/data governance note: when additional external datasets are licensed and approved, they can be integrated as calibrated baseline layers. The long-term objective is stronger alignment with QLEAM AI's own verified dataset, not replacement-by-claim.

### 6) Why This Architecture Works
This design balances reliability, explainability, and long-horizon improvement.

- Serverless orchestration scales with low operational overhead.
- Deterministic acoustic fallback guarantees graceful behavior under model outages.
- Advanced embedding inference increases representation power for complex cry signals.
- Feedback-verified dataset growth improves model relevance over time.
- Legacy research grounding + daily adaptation keeps the system both scientifically anchored and real-world responsive.

## Demo

- **Image: 1 - End-to-end architecture diagram (Frontend -> API -> Step Functions -> Insights + Learning loop)**
- **Image: 2 - Audio processing stages (quality gate, diarization, classification)**
- **Image: 3 - Insight output (emotion confidence + acoustic radar + guidance)**
- **Image: 4 - Feedback confirmation flow and quality gates**
- **Image: 5 - Learning dataset lifecycle (candidate -> confirmed -> retrain -> promote)**
- **Image: 6 - Model blending schedule visual**
- **Image: 7 - Mobile UI walkthrough (record -> insight -> feedback)**
- **Video: 0:00-4:30 - Technical walkthrough of one session from upload to insight**

## What I learned
1. Real-world AI quality depends as much on data gates as model choice.
2. Explainability is a product feature, not a documentation feature.
3. Parent-confirmed corrections are high-value training signals.
4. A robust fallback path is essential for production trust.
5. The strongest long-term advantage is a disciplined self-learning loop, not one-time model accuracy.

