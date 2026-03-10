# Qleam — Technical Documentation

> Generated from source code only. No external references or speculation.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [AI Basic Mode — Recording to Insight](#2-ai-basic-mode--recording-to-insight)
3. [AI Advanced Mode — Recording to Insight](#3-ai-advanced-mode--recording-to-insight)
4. [Self-Learning Model](#4-self-learning-model)
5. [Frontend UI — How Each Value is Generated](#5-frontend-ui--how-each-value-is-generated)
6. [Data Security and Privacy](#6-data-security-and-privacy)

---

## 1. System Overview

Qleam is a baby sound analysis application for parents of children aged **0–24 months**. A parent records their baby's sounds on a phone browser; the system analyzes the audio, classifies the emotion or sound type, and presents a human-readable insight.

### Infrastructure Stack

| Layer | Technology |
|---|---|
| Authentication | AWS Cognito (email + password) |
| Frontend | React (AWS Amplify UI) |
| API | AWS API Gateway + Lambda |
| Orchestration | AWS Step Functions |
| Audio Storage | Amazon S3 |
| Database | Amazon DynamoDB |
| ML Inference | AWS SageMaker Serverless Endpoint (HuBERT) |
| Speech Transcription | Amazon Transcribe |
| Infrastructure-as-Code | Terraform |

### DynamoDB Tables

| Table | Purpose |
|---|---|
| `ChildProfile` | Parent–child relationship, birth date, baseline features |
| `Session` | Every recording session with all analysis results |
| `Feedback` | Parent feedback records |
| `TrainingFeatures` | Anonymized HuBERT embeddings for model training |
| `ModelVersions` | History of trained model versions |
| `SoundCluster` | Per-child sound clusters (private language) |
| `SemanticBridge` | Cluster→emotion mappings |
| `ConceptGraph` | Child-specific concept graph |
| `Milestones` | Developmental milestone events |
| `TrainingCandidate` | Pre-anonymization candidate records |

---

## 2. AI Basic Mode — Recording to Insight

Basic mode runs when the SageMaker HuBERT endpoint is **not configured** (`USE_SAGEMAKER_INTENT_ENDPOINT = false`). Emotion scoring uses hand-crafted acoustic rules instead of a neural network.

### 2.1 Stage 1 — Audio Capture (Frontend)

**Component:** `RecordButton.js`
**Technology:** Browser MediaRecorder API (`audio/webm`)

- Parent taps "Start Recording"
- Browser requests microphone permission via `navigator.mediaDevices.getUserMedia`
- Audio chunks are collected every 100ms
- Minimum recording: **5 seconds** (enforced client-side; stops auto at **30 seconds**)
- Parent taps "Stop"; audio blob is assembled from chunks

### 2.2 Stage 2 — Upload to S3 (Frontend → API)

**Component:** `RecordButton.js` → `POST /session/upload` → `PUT S3`

1. Frontend calls `POST /session/upload` with `child_id`
2. API Handler Lambda validates: child exists, belongs to this parent, child age is 0–24 months
3. API generates a **presigned S3 URL** (expires in 5 minutes) and creates a pending `Session` record in DynamoDB
4. Frontend uploads the WebM blob directly to S3 via `PUT` using the presigned URL (no Lambda in the upload path)
5. Frontend calls `POST /session/{id}/start` to trigger the processing pipeline

### 2.3 Stage 3 — Audio Classification Lambda

**Lambda:** `feature_extraction/handler.py`
**Trigger:** AWS Step Function (first state)
**Libraries:** `librosa`, `numpy`, `scipy`

The pipeline runs in this exact order:

#### Step 1: Download + Decode
- Downloads `audio/webm` file from S3
- Decodes to mono float32 numpy array at **22050 Hz** sample rate
- Applies Voice Activity Detection (VAD) to trim silence from edges
- Records `duration_seconds`

#### Step 2: Quality Gate
Checks the audio for disqualifying problems:

| Issue | Threshold | Rejection Message |
|---|---|---|
| No signal / too short | < 3 seconds | "Audio Quality Issue" |
| Too long | > 600 seconds | "Audio Quality Issue" |
| Clipping | > 0.5% of frames | "Audio Quality Issue" |
| Low SNR | < 10 dB | "Noisy Environment" |
| Too silent | RMS too low | "Noisy Environment" |
| No vocal activity | voiced_fraction too low | "Noisy Environment" |

If critical issues are found → **fast reject**: session saved with `fast_reject=True` and a user-facing message.

#### Step 3: Feature Extraction (Embedding for Clustering)
- Extracts a feature embedding vector from the full audio
- Computes `feature_scores`: spectral and temporal acoustic measurements

#### Step 4: Diarization
- Segments audio by speaker using `diarize()` from `diarization.py`
- Extracts the "baby segment" from multi-speaker audio
- Applies a lightweight denoise pass (`_enhance_baby_signal`): DC removal, peak normalization, soft noise gating, pre-emphasis filter (α=0.95)

#### Step 5: Core Features (computed once, reused)
`compute_core_features()` calculates:

| Feature | Description |
|---|---|
| `f0_mean` | Mean fundamental frequency (Hz) |
| `rms_mean` | Mean RMS energy |
| `voiced_fraction` | Fraction of frames with voiced activity |
| `f0_instability` | Variance in pitch |
| `spectral_centroid` | Spectral brightness |
| `energy_variability` | Variation in energy over time |
| `zcr` | Zero-crossing rate |
| `syllable_rate` | Estimated syllables per second |

#### Step 6: Early Rejection Gate
Before classification, checks core features directly:
- **Silence**: RMS mean < 0.005 AND 80%+ frames below threshold → "No Sound Detected"
- **No voiced frames**: voiced_fraction < 3% AND RMS < 0.015 → "No Sound Detected"
- **Adult-only**: F0 median < 200 Hz with significant voiced activity → "Adult Voice Detected"

#### Step 7: Sound Classification
`classify_sound()` assigns one of: `cry`, `speech`, `laugh`, `silence`, `noise`, `mixed`

Per-segment classification is also run if diarization produced segments, then `aggregate_sound_types()` computes `type_ratios` (fractions of time per type).

**Scope normalization for 0–3 month babies:** If the baby is ≤ 90 days old and the audio is borderline speech/mixed but has cry evidence, it is normalized back to `cry` (because babies this age don't produce speech).

#### Step 8: Adult/Baby Detection
Two-stage check:

1. **Biological validation** (`biological_validation()`): Estimates vocal tract length (VTL) from formants. VTL > 13 cm → adult. Also detects mimicry (adult imitating baby cry).
2. **Age classifier** (`classify_probabilistic()`): Uses rich acoustic features including formants to produce a probability. `is_adult = True` if confidence ≥ 60%.

Final rule: adult if either classifier says adult with sufficient confidence, OR mimicry is suspected.

#### Step 9: Post-Classification Rejection
After knowing `sound_type` and `is_adult`:

| Condition | Message |
|---|---|
| Age unavailable or > 24 months | "Age Not Supported" |
| Adult voice detected | "Adult Voice Detected" |
| Speech + age ≤ 90 days | "Speech Not Supported" |
| Noisy/chaotic mixed audio | "Chaotic Environment" / "Noisy Environment" |

#### Step 10: Routing Decision
Determines which downstream analyses to run:

```
sound_type = cry        → run_cry_analysis = True
sound_type = speech     → run_transcription = True  (disabled if age ≤ 90 days)
sound_type = laugh      → run_laugh_detection = True
sound_type = mixed      → run whichever sub-types are present
```

#### Step 11: Basic Mode — Skip HuBERT
In Basic mode, the `USE_SAGEMAKER_INTENT_ENDPOINT` flag is `false`. The HuBERT call is skipped entirely. The session is saved with `classifier_result = None`.

### 2.4 Stage 4 — Insight Generator Lambda

**Lambda:** `insight_generator/handler.py`
**Trigger:** Step Function (second state, receives feature_extraction output)

Routes by `sound_type`:

#### Cry path (Basic mode)
Since `classifier_result` is `None`, `analyze_cry()` calls `analyze_cry_rules()`:

**Rule-based scoring** (`cry_rules.py`):
- Each emotion has an `EMOTION_PROFILES_0_3M` entry with acoustic rules
- Each rule specifies a feature name, `min`/`max` range, and `weight`
- `_soft_range_match()`: value inside range → score 1.0; outside → linearly decays over 20% tolerance band
- Raw score = prior + weighted sum of rule matches
- Scores are normalized to sum to 1.0 (probability distribution)
- Highest probability → `primary_emotion`

Emotion taxonomy (7 classes):

| Emotion | Dunstan Sound | Acoustic Profile |
|---|---|---|
| `hungry` | neh | F0 300–560 Hz, moderate energy, rhythmic |
| `tired` | owh | F0 210–430 Hz, low energy, low ZCR |
| `discomfort` | heh | Mid-high ZCR, intermittent energy |
| `gas` | eairh | High F0 400–660 Hz, high spectral centroid, straining |
| `burp` | eh | F0 280–520 Hz, high energy variability |
| `pain` | — | F0 560–1100 Hz, high RMS, sustained |
| `content` | — | Low F0, very low energy, stable |

**Insight output** for cry:
- `headline`: emotion icon + label (e.g. "🍼 Hungry")
- `emotion`: primary emotion key
- `emotion_confidence`: normalized probability score (0–1)
- `top_emotions`: top 3 with scores
- `emotion_scores`: all 7 scores
- `acoustic_features`: normalized 0–100 values for radar chart
- `narrative_data`: computed text slots (intensity, pitch_desc, pattern_desc, duration_desc)
- `insight_sections.what_i_hear`: acoustic description
- `insight_sections.what_it_means`: behavioral interpretation
- `insight_sections.what_to_try`: 3 actionable suggestions
- `dunstan_sound`: Dunstan sound name (for babies ≤ 6 months)

#### Other sound types
- **Silence** → "No sound detected"
- **Noise** → "Unrecognized sound"
- **Laugh** → "Your baby is laughing!" or adult-detected variant
- **Speech** → transcription result + word count (disabled for 0–3 month babies)
- **Mixed** → prioritizes: speech (if words) > cry (if score > 0.3) > laugh (if score > 0.3) > "Mixed sounds"

All insights include `disclaimer`: *"This is a behavioral pattern observation, not medical advice..."*

### 2.5 Technology Stack — Basic Mode

| Component | Technology |
|---|---|
| Audio capture | Browser MediaRecorder API |
| Audio decoding | `librosa`, `soundfile` |
| Feature extraction | `numpy`, `scipy` |
| Diarization | Custom `diarization.py` |
| Sound classification | Custom `sound_classifier.py` |
| Biological validation | Custom `audio_utils.py` |
| Age classification | Custom `age_classifier.py` |
| Emotion scoring | Rule engine `cry_rules.py` |
| Data storage | DynamoDB, S3 |
| Orchestration | AWS Step Functions |
| API | AWS Lambda (Python 3.x) |

---

## 3. AI Advanced Mode — Recording to Insight

Advanced mode activates when `USE_SAGEMAKER_INTENT_ENDPOINT = true` AND a SageMaker HuBERT endpoint is configured. Stages 1–3 (up through routing) are identical to Basic mode. Advanced mode adds a neural network layer.

### 3.1 Additional Step After Routing — HuBERT Embeddings (EARS)

**Technology:** Facebook HuBERT (Hidden-Unit BERT) via AWS SageMaker Serverless Endpoint
**Client:** `hubert_client.py`

Only runs when `sound_type` is `cry` or `mixed`.

1. Audio is resampled to **16,000 Hz** (HuBERT's expected sample rate)
2. Audio waveform is sent as a JSON payload to the SageMaker endpoint
3. SageMaker runs HuBERT feature extraction
4. Response is a time-series of frame embeddings (T × 768 dimensions)
5. Client **mean-pools** across time frames → single **768-dimensional embedding vector**
6. Cold-start handling: if the serverless endpoint is cold, waits 3 seconds and retries once

HuBERT is a self-supervised speech model trained on 960 hours of LibriSpeech. It learns rich acoustic representations without needing labeled data.

### 3.2 Emotion Classifier (BRAIN)

**Module:** `emotion_classifier.py`
**Function:** `predict_emotion(embeddings, age_days)`

Three model layers are attempted in priority order:

#### Layer 1: Phase 4 — Age-Conditioned Two-Branch Network (if trained)

Architecture:
```
Embedding branch:   768 → 256 (ReLU) → 128 (ReLU)
Age branch:           4 →  16 (ReLU) →   8 (ReLU)
Concatenate:        136 (128+8) → 64 (ReLU) → 7 (softmax)
```

The age input is encoded as a **4-dimensional age feature vector** (`age_encoder.py`):
```
[0] age_days / 730.0                    — normalized linear age
[1] sin(age_days × π / 90)             — 3-month developmental cycle
[2] sin(age_days × π / 180)            — 6-month developmental cycle
[3] 1.0 if age_days < 90 else 0.0      — newborn binary hint
```

This allows the model to distinguish that the same acoustic pattern may mean "hungry" for a 2-week-old but "tired" for a 5-month-old.

#### Layer 2: Phase 2 — TFLite Public Dataset Model (pre-trained)

Pre-trained on public datasets mapped to our 7-class taxonomy:
- **Dunstan Baby Language** dataset (neh/owh/heh/eairh/eh)
- **DonateACry** (hunger/belly_pain)
- **Baby Chillanto** (normal/pain)

Runs via TFLite Runtime or TensorFlow Lite.

#### Layer 3: Fallback
If no model loads → uniform distribution across 7 classes, `model_version = "fallback"`.

#### Model Blending (when both Phase 4 and Phase 2 are available)

```
probs = (our_weight × phase4_probs) + (public_weight × tflite_probs)
```

Blend weights based on confirmed training samples:

| Confirmed Samples | Public Model Weight | Our Model Weight |
|---|---|---|
| 0–29 | 100% | 0% |
| 30–99 | 70% | 30% |
| 100–299 | 40% | 60% |
| 300+ | 15% | 85% |

This ensures the system starts with a reliable public baseline and gradually trusts its own fine-tuned model as parent feedback accumulates.

### 3.3 Insight Generation (Advanced Mode)

Same as Basic mode except:
- `classifier_result` contains the neural network output
- `analyze_cry()` uses the ML probabilities instead of acoustic rules
- `model_version` is one of: `phase4-v{N}`, `blended-v{N}`, `phase2-pretrained`
- Higher confidence values are possible because the neural model has access to rich spectral representations that the rule engine cannot capture

### 3.4 Training Data Collection (Advanced Mode Only)

After a successful HuBERT + emotion classification:

`_store_training_features()` is called automatically:
1. HuBERT embeddings (768-dim float32 array) are saved to S3 at: `training-features/{feature_id}/embeddings.npy`
2. A metadata record is written to `TrainingFeatures` DynamoDB table with:
   - `feature_id` (UUID, no PII)
   - `session_id` (temporary — removed at anonymization time)
   - `s3_embeddings_path`
   - `predicted_emotion`, `predicted_confidence`, `model_version`
   - `age_days`, `duration_s`, `created_at`
   - `is_confirmed = False` (not yet parent-confirmed)

### 3.5 Technology Stack — Advanced Mode

| Component | Technology |
|---|---|
| Everything in Basic mode | (same) |
| HuBERT feature extraction | SageMaker Serverless Endpoint (HuggingFace HuBERT) |
| Emotion classification | TFLite Phase 2 + NumPy Phase 4 two-branch network |
| Age encoding | Custom sinusoidal age encoder |
| Model storage | S3 (`.npz` weights), DynamoDB (version registry) |
| Model blending | Weighted sum of public + trained probabilities |

---

## 4. Self-Learning Model

The self-learning loop converts parent feedback into improved model weights. It is entirely automated via AWS Step Functions and EventBridge.

### 4.1 Phase Flow Overview

```
Parent records → Classify → HuBERT embeddings stored (raw, unconfirmed)
     ↓
Parent gives feedback → Quality gates → Anonymize → Mark confirmed
     ↓
Training Check (EventBridge daily) → Enough new samples? → Start Step Function
     ↓
Model Trainer: Load → Train → Validate → Promote
     ↓
New model active → loaded at next Lambda cold start
```

### 4.2 Feedback Collection

**Lambda:** `feedback_processor/handler.py`
**Trigger:** `POST /session/{id}/feedback`

Parent submits:
```json
{
  "feedback_type": "cry_emotion",
  "confirmed_emotion": "hungry",
  "was_correct": true
}
```

Or corrects:
```json
{
  "feedback_type": "cry_emotion",
  "confirmed_emotion": "tired",
  "was_correct": false
}
```

The feedback processor then runs quality gates.

### 4.3 Quality Gates (training_anonymizer.py)

Five gates that must all pass before feedback enters training data:

| Gate | Check | Rejection Reason |
|---|---|---|
| 0 — Embeddings exist | HuBERT was run for this session (Advanced mode only) | `no_embeddings` |
| 1 — Valid feedback | `confirmed_emotion` not "skip" / "not_sure" / "unknown" | `feedback_skip` |
| 2 — Audio quality | SNR ≥ 10 dB AND duration ≥ 3 seconds AND sound_type is cry/mixed | `low_snr` / `short_duration` / `wrong_sound_type` |
| 3 — Confidence check | If `was_correct=True` (parent confirming), model confidence must be ≥ 0.4 | `low_confidence_confirm` |
| 4 — Deduplication | This session cannot be confirmed twice | `already_confirmed` |

**Important:** Corrections (`was_correct=False`) always pass gate 3. The logic: if the model was wrong, the parent's correction is especially valuable regardless of the model's original confidence.

### 4.4 Anonymization

When all gates pass, `anonymize_and_confirm()` runs:

1. Adds confirmed label to the `TrainingFeatures` record
2. **Removes `session_id`** from the record (the link back to PII is severed)
3. Sets `is_confirmed = True`
4. Records `confirmation_source`: `parent_confirm` or `parent_correct`
5. Records `model_confidence_at_time` and `audio_quality_snr`

After this, the record contains only:
- A random `feature_id` UUID
- The S3 path to the embedding file (also identified only by `feature_id`)
- `age_days`, `duration_s`, `confirmed_emotion`, `is_confirmed`
- No child name, no parent ID, no session timestamp

### 4.5 Training Trigger (training_check/handler.py)

**Trigger:** AWS EventBridge (runs daily)

Conditions to trigger retraining:

| Condition | Threshold |
|---|---|
| Batch trigger | ≥ 50 new confirmed samples since last training |
| Weekly trigger | ≥ 10 new samples AND ≥ 7 days since last training |
| Minimum threshold | Total confirmed samples ≥ 30 (required for either trigger) |

If conditions are met, starts the Training Step Function.

### 4.6 Model Training (model_trainer/handler.py)

**Trigger:** AWS Step Function (4 sequential states: load → train → validate → promote)

#### State 1: Load
- Scans `TrainingFeatures` for `is_confirmed = True`
- Downloads embeddings from S3 for each confirmed sample
- Encodes age_days → 4-dim age vector (via `age_encoder.py`)
- Checks: minimum 30 samples total, minimum 3 samples per class, minimum 2 valid classes
- Saves `embeddings.npy`, `labels.npy`, `age_encodings.npy` to a temp S3 prefix

#### State 2: Train
**Architecture:** Two-branch age-conditioned neural network (NumPy-only, no TensorFlow required)

```
Embedding branch: 768 → 256 → 128 (both ReLU)
Age branch:         4 →  16 →   8 (both ReLU)
Concatenated:     136 →  64 →   7 (ReLU → softmax)
```

Training parameters:
- Optimizer: Gradient descent with manual backpropagation
- Learning rate: 0.001
- L2 regularization: 1e-4
- Epochs: 50
- Batch size: 32
- Train/val split: 80/20

Loss: cross-entropy with L2 regularization. Gradients computed by hand for all 12 parameter tensors.

#### State 3: Validate
- Compares new model's validation accuracy vs. current active model's stored accuracy
- Promotion threshold: new accuracy must exceed current by **+2%** (`PROMOTION_MARGIN = 0.02`)
- Exception: if no active model exists and new accuracy ≥ 30%, promote anyway

#### State 4: Promote
- Copies model weights to permanent S3 path: `models/emotion_classifier/v{N}/model_weights.npz`
- Creates a new record in `ModelVersions` DynamoDB table
- Marks previous version as `active = False`
- Marks all trained feature records with `included_in_training = train_id`
- The new model is loaded by `emotion_classifier.py` on the next Lambda cold start

---

## 5. Frontend UI — How Each Value is Generated

### 5.1 App Shell (`App.js`)

- **Authentication**: AWS Amplify `Authenticator` component (Cognito). Parent logs in with email + password.
- **AI Mode badge** (header): Shown as "AI Mode: Basic" or "AI Mode: Advanced". Source: `GET /status` → `ai_mode` field. Value is `"Advanced"` if `USE_SAGEMAKER_INTENT_ENDPOINT=true` AND a HuBERT endpoint is configured; otherwise `"Basic"`.
- **Sign Out button**: Calls Amplify `signOut()`
- **User name** (header): From Cognito user object (`signInDetails.loginId`)

### 5.2 Settings Menu (`Dashboard.js` — `SettingsPanel` component)

Opened via the ⚙ icon in the top-right of the child selector bar.

**Add a Child:**
- Fields: Name (required), Date of Birth (required), Gender (optional)
- Date of birth is validated client-side to be within the last 730 days (0–24 months)
- Calls `POST /child` → creates a `ChildProfile` record in DynamoDB
- Child profile contains: `child_id`, `parent_id`, `name`, `birth_date`, `gender`, `session_count`

**Remove a Child:**
- Parent selects child from dropdown, then types the child's name to confirm
- Calls `DELETE /child/{child_id}`
- Deletes: all sessions, feedback records, S3 audio files, training candidates (PII-linked), sound clusters, semantic bridges, concept graph, milestones
- Does **not** delete de-identified `TrainingFeatures` records (embeddings are already anonymized)
- Audit log entry is written (UUIDs only, no names)

### 5.3 Latest Insight (`Dashboard.js`)

Shown in the "Latest Insight" section after the record button.

**Source:** The most recent session from `GET /child/{child_id}/sessions` that has an `insight_summary` object.

**`insight_summary` fields shown:**
- `headline_icon` + `headline` → shown via `InsightPanel`
- `emotion_confidence` → confidence bar percentage
- `is_adult` → adult warning badge

The summary is a trimmed version of the full insight — no embedding vectors, no full debug payload.

### 5.4 Session History (`Dashboard.js` — `SessionCard` component)

List of all sessions for the selected child. Calls `GET /child/{child_id}/sessions`.

Each `SessionCard` shows:

| UI Element | Data Source |
|---|---|
| Date | `session.timestamp` → `toLocaleDateString()` |
| Time | `session.timestamp` → `toLocaleTimeString()` |
| Color dot | `insight_summary.display_type` → type color map (cry=red, speech=teal, laugh=green, silence=gray, noise=dark gray, mixed=yellow) |
| Emotion icon | `insight_summary.headline_icon` |
| Headline text | `insight_summary.headline` (icon stripped if duplicated at start) |
| "Adult voice" badge | `insight_summary.is_adult` |
| Confidence % | `insight_summary.emotion_confidence` → multiplied by 100, rounded |
| "Processing..." text | `insight_summary === null` (session exists but not yet processed) |

### 5.5 Session Detail Page (`SessionDetail.js`)

Navigated to when a session card is clicked, or immediately after recording completes.

**Polling:** If insight is not ready, polls `GET /session/{id}/insight` every 2–5 seconds (up to 20 attempts).

**Values shown:**

| UI Element | Data Source |
|---|---|
| Child name in title | `session.child_name` (from API) or localStorage cache |
| Session timestamp | `session.timestamp` → `toLocaleString()` |

#### InsightPanel — Cry Type (CryInsight component)

| UI Element | Data Source |
|---|---|
| Headline icon + text | `insight.headline_icon`, `insight.headline` |
| Narrative paragraph | Generated by `pickNarrative()` using `insight.emotion` + `insight.narrative_data` + child name |
| Confidence bar | `insight.emotion_confidence` (0–1, displayed as percentage) |
| Confidence message | `buildConfidenceMessage()` using confidence value + session count |
| "Try this" suggestions | `pickSuggestions()` using emotion + age_days |
| "Also possible" text | `buildAlsoPossibleText()` using `insight.also_possible` |
| Emotion radar chart | `EmotionRadar` component using `insight.emotion_scores` (7 values) + `insight.top_emotions` |
| Acoustic radar chart | `AcousticRadar` component using `insight.acoustic_features` (normalized 0–100) |
| Dunstan section | `DunstanSection` using `insight.dunstan_sound` + `insight.dunstan_description` (only shown for babies ≤ 6 months) |

**Acoustic features on radar chart:**
| Feature Key | What it measures | How computed |
|---|---|---|
| `pitch_hz` | Raw F0 mean in Hz | `f0_mean` from sound features |
| `pitch_normalized` | Pitch 0–100 | Clamped: (f0 - 100) / 700 × 100 |
| `energy_normalized` | Loudness 0–100 | Clamped: rms / 0.2 × 100 |
| `stability_normalized` | Inverse of F0 instability | 100 - (instability / 0.5 × 100) |
| `voicing_pct` | % of voiced frames | `voiced_fraction × 100` |
| `brightness_normalized` | Spectral brightness | Clamped: (centroid - 500) / 3500 × 100 |
| `variation_normalized` | Energy variation | Clamped: energy_variability / 1.0 × 100 |

**Narrative data slots (for dynamic text):**
| Slot | Computation |
|---|---|
| `intensity` | RMS > 0.12 → "strong", > 0.05 → "moderate", else "gentle" |
| `pitch_desc` | F0 > 500 → "high-pitched", > 350 → "mid-range", else "low-pitched"; combined with stability |
| `pattern_desc` | syllable_rate > 4 → "rapid, repetitive", > 2 → "rhythmic", energy_var > 0.5 → "intermittent", else "continuous" |
| `duration_desc` | energy_var > 0.6 → "comes in waves", > 0.3 → "builds in waves", else "stays sustained" |
| `builds_or_steady` | energy_var > 0.4 → "builds in intensity", instability > 0.2 → "comes and goes", else "stays relatively steady" |

#### InsightPanel — Non-Cry Types (GenericInsight component)

| UI Element | Data Source |
|---|---|
| Description text | `insight.description` |
| Transcript (speech/mixed) | `insight.transcript.text`, `.word_count`, `.unique_words`, `.has_sentences`, `.confidence` |
| Speaker badge | `insight.word_age_match.speaker` ("adult" / "baby" / "uncertain") |
| Age mismatch warning | `insight.word_age_match.mismatch_warning` |

#### InsightPanel — Adult Detected

If `insight.adult_detected = true`, a warning banner is shown: "🔊 Adult voice detected in this recording". The cry analysis section is replaced with the generic layout.

### 5.6 Feedback Form (`FeedbackForm.js`)

Shown on the Session Detail page for cry and mixed sessions. Hidden for other sound types.

**Flow:**
1. Parent sees "Help Qleam learn" button
2. Clicks → modal opens
3. If emotion was detected: parent selects "✓ Yes, correct" or "✗ No, it was different"
4. If incorrect: parent selects the actual emotion from a 7-button grid (hungry / tired / uncomfortable / gas / burp / pain / content)
5. Optional notes field (500 char limit enforced server-side)
6. Submits → `POST /session/{id}/feedback`
7. On success: "✓ Thank you — your feedback helps Qleam learn!"

**What happens with feedback (server-side):**
1. `feedback_processor` applies quality gates
2. If accepted: the existing `TrainingFeatures` record is anonymized (session_id removed), `is_confirmed = True`, `confirmed_emotion` set
3. The HuBERT embeddings in S3 are now confirmed training data
4. After enough accumulate, the Training Check Lambda triggers retraining

### 5.7 Training Stats (`Dashboard.js`)

Shown only if `child_count > 0`. Source: `GET /child/{child_id}/training-stats`.

```
"Your baby contributed X samples to our AI (Y total across all families)"
```

`child_count`: count of `TrainingFeatures` records where `is_confirmed=True` AND `child_id` matches.
`total_count`: count of all `is_confirmed=True` records globally.

### 5.8 Disclaimer

Static text stored in `constants.py`:
> "This is a behavioral pattern observation, not medical advice. Qleam provides probabilistic interpretations to support parental awareness. Always consult a healthcare professional for medical concerns."

Attached to every insight in the `disclaimer` field and displayed at the bottom of the Session Detail page.

---

## 6. Data Security and Privacy

### 6.1 Authentication and Ownership

- Every API request carries a Cognito JWT token
- `get_user_id()` extracts the Cognito `sub` (a UUID) from JWT claims
- Every child record stores `parent_id = cognito_sub`
- Before any read/write/delete, the API verifies `profile.parent_id == user_id`
- A parent can never access another parent's children or sessions

### 6.2 Audio Data

- Audio is stored in S3 at path: `{child_id}/{session_id}/audio.webm`
- S3 access is via IAM roles on the Lambda functions — no public access
- Presigned upload URLs expire in **5 minutes**
- When a child is deleted, all S3 audio files at `{child_id}/{session_id}/*` are deleted

### 6.3 PII Handling During Training

**Before parent feedback:** Raw training candidates stored in `TrainingFeatures` still contain `session_id` (which links back to a session, which links to `child_id`). This is a temporary state.

**After parent feedback (anonymization):**
- `session_id` is **removed** from the `TrainingFeatures` record via a DynamoDB `REMOVE` expression
- The HuBERT embedding in S3 is identified only by `feature_id` (a random UUID with no link to any person)
- What remains: `feature_id`, `age_days`, `duration_s`, `confirmed_emotion`, `audio_quality_snr`, `model_confidence_at_time`
- No child name, no parent ID, no session timestamp, no audio file reference

**Data deleted on child removal:**
- Sessions + S3 audio files
- Feedback records
- Training candidates (`TrainingCandidate` table — PII-linked pre-anonymization records)
- Sound clusters, semantic bridges, concept graph, milestones

**Data NOT deleted on child removal:**
- Confirmed `TrainingFeatures` records — these are already anonymized and used to train the shared model. They contain no identifying information.

### 6.4 Self-Learning Model Purity

**How is the training data trustworthy?**

1. **Quality gates filter noise:** Only audio with SNR ≥ 10 dB, duration ≥ 3 seconds, sound_type = cry/mixed enters the training pool.

2. **Confidence gate on confirmations:** If a parent says "yes correct" but the model was low-confidence (< 40%), the sample is rejected. This prevents false confirmations of guesses.

3. **Corrections always accepted:** If the parent says "no, it was tired not hungry", this correction enters training regardless of model confidence. Corrections are the most valuable signal.

4. **Deduplication:** A session can only be confirmed once. A parent cannot flood the training set by submitting the same session repeatedly.

5. **Class balance check:** Training only proceeds if at least 2 emotion classes have ≥ 3 samples each. This prevents the model from collapsing to a single dominant class.

6. **Validation before promotion:** New model must beat the current active model by at least 2% on a held-out validation set. A worse or equal model is never deployed.

7. **Blend schedule:** Even after many confirmed samples, the system blends with the public dataset model (100% public → 85% ours at 300+ samples). This prevents catastrophic forgetting and keeps a population-level anchor.

**What if no feedback is given?**

Without feedback, `TrainingFeatures` records remain `is_confirmed = False`. They are never used for training. The model does not learn from unconfirmed predictions.

**Age_days in training — privacy note:**

`age_days` (not birth date) is stored. This is a derived value (number of days, not a specific date), making it significantly harder to de-anonymize compared to storing a birthdate.

### 6.5 CORS and API Security

- CORS origin validation: only pre-configured `ALLOWED_ORIGINS` are accepted
- `Access-Control-Allow-Credentials: true` with specific origin (not `*`)
- All API endpoints require a valid Cognito Bearer token

### 6.6 Data Deletion — Account Level

`DELETE /account` iterates all children for the authenticated parent and calls `_delete_child_direct_data()` for each. This deletes everything PII-linked. Audit log entries are written using UUIDs only (no names, no emails, no birthdates).

---

## Appendix — Processing Pipeline Diagram

```
Parent records audio (browser)
         │
         ▼
  POST /session/upload          ← Cognito JWT auth
  API creates Session record    ← DynamoDB
  Returns presigned S3 URL      ← S3
         │
         ▼
  Frontend PUTs audio to S3     ← Direct, no Lambda
         │
         ▼
  POST /session/{id}/start
  Step Function triggered       ← AWS Step Functions
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  State 1: feature_extraction Lambda                  │
│  ─────────────────────────────────────────────────── │
│  1. Download audio from S3                           │
│  2. Decode + VAD trim                                │
│  3. Quality gate (reject if broken/silent/noisy)     │
│  4. Feature extraction (embedding vector)            │
│  5. Diarization (isolate baby segment)               │
│  6. Core features (F0, RMS, ZCR, spectral)           │
│  7. Early rejection (silence / adult-only)           │
│  8. Sound classification (cry/speech/laugh/noise...) │
│  9. Adult/baby detection (VTL + age classifier)      │
│  10. Post-classification rejection                   │
│  11. [ADVANCED] HuBERT → 768-dim embedding           │
│  12. [ADVANCED] Emotion classifier → probability map │
│  13. [ADVANCED] Store training features in S3+DDB    │
│  14. Save session to DynamoDB                        │
└─────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  State 2: insight_generator Lambda                   │
│  ─────────────────────────────────────────────────── │
│  1. Read classification output from Step Function    │
│  2. [If speech and age > 90d] Run transcription      │
│  3. Route by sound_type:                             │
│     CRY: analyze_cry() → emotion display text        │
│     SPEECH: word analysis + age match                │
│     LAUGH: happy message                             │
│     SILENCE/NOISE: fallback message                  │
│  4. Build insight JSON (headline, scores, narrative) │
│  5. Save insight to Session record in DynamoDB       │
└─────────────────────────────────────────────────────┘
         │
         ▼
  Frontend polls GET /session/{id}/insight
  Session Detail page renders insight
         │
         ▼
  Parent gives feedback (optional)
  POST /session/{id}/feedback
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  feedback_processor Lambda                           │
│  ─────────────────────────────────────────────────── │
│  1. Quality gates (5 checks)                         │
│  2. Anonymize TrainingFeatures record (remove PII)   │
│  3. Mark is_confirmed = True                         │
│  4. Save feedback record                             │
└─────────────────────────────────────────────────────┘
         │
         ▼
  [Daily] training_check Lambda (EventBridge)
  Counts confirmed samples → triggers if thresholds met
         │
         ▼
┌─────────────────────────────────────────────────────┐
│  Training Step Function (4 states)                   │
│  Load → Train → Validate → Promote                   │
│  Two-branch age-conditioned network                  │
│  768-dim embeddings + 4-dim age encoding             │
│  Must beat current model by +2%                      │
│  Promoted to S3 → loaded at next Lambda cold start   │
└─────────────────────────────────────────────────────┘
```
