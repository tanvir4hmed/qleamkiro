# Qleam System Analysis — Complete Data Flow, Calculations & Output Reference

> Generated: 2026-03-02 | Scope: Full codebase analysis (excluding docs/)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [End-to-End Data Flow](#3-end-to-end-data-flow)
4. [Input Data Types](#4-input-data-types)
5. [Processing Pipeline (Step Functions)](#5-processing-pipeline-step-functions)
6. [Feedback Loop](#6-feedback-loop)
7. [Daily Aggregation (Federated Learning)](#7-daily-aggregation-federated-learning)
8. [All Formulas & Calculations](#8-all-formulas--calculations)
9. [Lambda-by-Lambda Reference](#9-lambda-by-lambda-reference)
10. [Shared Module Functions](#10-shared-module-functions)
11. [API Routes & Data Contracts](#11-api-routes--data-contracts)
12. [DynamoDB Tables & Schemas](#12-dynamodb-tables--schemas)
13. [Frontend Pages & Data Consumption](#13-frontend-pages--data-consumption)
14. [Infrastructure Summary](#14-infrastructure-summary)
15. [Constants & Thresholds Reference](#15-constants--thresholds-reference)

---

## 1. System Overview

Qleam is a baby vocalization analysis platform. Parents record their baby's sounds via a mobile-friendly web app. The system classifies the audio, identifies intent (hunger, pain, happiness, etc.), tracks developmental progress, and learns each baby's personal language over time.

**What goes in:** Audio recording (5–30s, WebM) + optional context (feeding time, health state, environment)

**What comes out:**
- Real-time insight card (what the baby is communicating)
- Developmental tracking (CBR trends, VTL growth, φ language readiness)
- Personal vocabulary (proto-words, confirmed concepts)
- Language analysis (MLU, fluency, pragmatic type) — for 12m+ children
- Population-level priors (federated learning, differentially private)

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (React SPA)                        │
│  Dashboard │ SessionDetail │ ProgressPage │ LanguagePage │ Settings │
└──────┬──────────┬──────────────┬──────────────┬─────────────────────┘
       │          │              │              │
       │  Cognito Auth (JWT)     │              │
       ▼          ▼              ▼              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (REST, COGNITO)                       │
│  /child  /session/upload  /session/{id}/start  /session/{id}/insight│
│  /session/{id}/feedback  /child/{id}/concepts  /child/{id}/milestones│
│  /child/{id}/language-signals  /account                             │
└──────┬──────────┬──────────────┬────────────────────────────────────┘
       │          │              │
       ▼          │              ▼
┌──────────┐      │    ┌─────────────────────────────────────────┐
│api_handler│◄─────┘    │       STEP FUNCTIONS PIPELINE           │
│ (Lambda) │─────────►  │                                         │
└──────────┘            │  1. feature_extraction (classify audio)  │
       │                │  2. insight_generator (generate insight)  │
       │                │  3. cluster_engine (sound clustering)     │
       │                │  4. developmental_tracker (CBR/φ/VTL)    │
       │                │  5. concept_decoder (proto-word check)    │
       │                │  6. speech_analyzer (LINGUISTIC only)     │
       │                └─────────────────────────────────────────┘
       │
       ▼ (feedback submission)
┌──────────────────┐     async     ┌─────────────────────┐
│feedback_processor │─────────────► │reinforcement_engine │
│   (sync Lambda)  │               │   (async Lambda)    │
│                  │     async     ├─────────────────────┤
│                  │─────────────► │  nlp_processor      │
└──────────────────┘               │   (async Lambda)    │
                                   └─────────────────────┘

┌─────────────────────────┐
│ federated_aggregator    │ ◄── EventBridge (daily schedule)
│ (daily FL aggregation)  │
│ Writes: PopulationModel │
└─────────────────────────┘
```

**Storage:**
- S3: raw audio files (90-day retention)
- DynamoDB: 10 tables (child profiles, sessions, clusters, feedback, concepts, milestones, population models, training data, model registry)
- CloudFront + S3: frontend static hosting

---

## 3. End-to-End Data Flow

### 3.1 Recording → Insight (Happy Path)

```
Parent opens app → selects child → taps Record
    │
    ▼
RecordButton captures audio (5–30s, WebM via MediaRecorder)
    │  + collects context: feeding_minutes_ago, health_state, environment
    │
    ▼
POST /session/upload  →  { child_id, session_context }
    │  Response: { session_id, upload_url (presigned S3 PUT) }
    │
    ▼
PUT <upload_url>  →  raw audio blob uploaded directly to S3
    │
    ▼
POST /session/{id}/start  →  triggers Step Functions pipeline
    │
    ▼
═══════════════════════════════════════════════════
STEP FUNCTIONS PIPELINE (runs ~10–20 seconds)
═══════════════════════════════════════════════════
    │
    ├─ Step 1: FEATURE EXTRACTION
    │   Input:  S3 audio path + child birth_date
    │   Does:   Download audio → VAD trim → quality gate → extract 65+ features
    │           → diarize speakers → classify sound → detect baby vs adult
    │   Output: sound_type, is_adult, embedding_vector, formants, VTL,
    │           rich_features (65 features), biological validation, routing flags
    │
    ├─ Step 2: FAST REJECT CHECK (Choice state)
    │   If silence/quality failure → generate "no sound detected" insight → DONE
    │   If valid → continue pipeline
    │
    ├─ Step 3: INSIGHT GENERATOR
    │   Input:  Classification results from Step 1
    │   Does:   Route by sound_type:
    │           - CRY → emotion analysis (age-specific), Dunstan sounds (0-6m)
    │           - SPEECH → transcription, word detection, age matching
    │           - LAUGH → happy emotion insight
    │           - MIXED → priority routing (words > cry > laugh)
    │           Uses Three-Source Evidence Model (acoustic 60%, research 15%, feedback 25%)
    │   Output: Insight card (headline, description, emotion, confidence)
    │
    ├─ Step 4: CLUSTER ENGINE
    │   Input:  1024-dim embedding vector
    │   Does:   Cosine similarity against existing clusters
    │           Match ≥ 0.75 → attach to cluster (update centroid)
    │           No match → create new cluster
    │   Output: cluster_id, action (attached/created), similarity_score
    │
    ├─ Step 5: DEVELOPMENTAL TRACKER
    │   Input:  session_id, cluster_id
    │   Does:   Extract CBR from rich_features → compute CBR EMA (adaptive α)
    │           → compute φ order parameter → check milestone criteria
    │           → log milestones (first canonical babble, etc.)
    │   Output: developmental_view (cbr, cbr_ema, vtl_cm, phi, phi_label, milestones)
    │
    ├─ Step 6: CONCEPT DECODER
    │   Input:  session_id, cluster_id
    │   Does:   Check 5 proto-word criteria → determine status
    │           (CRYSTALLIZED / CANDIDATE / NONE)
    │           → find top concepts linked to this cluster
    │   Output: concept_decode (proto_word_status, top_concepts, unknown_flag)
    │
    └─ Step 7: SPEECH ANALYZER (LINGUISTIC mode only, 12m+)
        Input:  session_id
        Does:   If developmental_mode == LINGUISTIC:
                Compute MLU, vocabulary diversity, pragmatic type, fluency
                Update MLU EMA → check milestones (MLU≥2, MLU≥3, vocab 20/50)
        Output: speech_analysis (mlu, vocab_diversity, pragmatic_type, fluency)

═══════════════════════════════════════════════════
    │
    ▼
SessionDetail page polls GET /session/{id}/insight (2–5s backoff)
    │  Receives: insight + developmental_view + concept_decode + speech_analysis
    │
    ▼
Parent sees insight card + submits feedback via FeedbackForm
```

### 3.2 Feedback Loop

```
Parent submits feedback (POST /session/{id}/feedback)
    │
    ├─ Language feedback: baby_sound + parent_meaning
    │   → stores in ConceptGraph (personal vocabulary)
    │   → links to acoustic cluster
    │
    ├─ Cry emotion feedback: confirmed_emotion + was_correct
    │   → stores cry training sample (TrainingCandidate)
    │   → triggers model retrain if threshold reached (≥20 samples)
    │
    └─ General feedback: response_type + effectiveness + notes
        │
        ├─ ASYNC → reinforcement_engine
        │   Updates cluster: reinforcement_weight ± learning rate
        │   Updates probable_intents distribution
        │   Creates/updates semantic bridges (word↔cluster links)
        │
        └─ ASYNC → nlp_processor (if notes present)
            Calls Bedrock Claude to extract:
            - Intent (hunger, sleep, pain, etc.)
            - Objects (bottle, teddy, blanket, etc.)
            Updates ConceptGraph with extracted concepts
```

### 3.3 Daily Aggregation

```
EventBridge timer (daily) → federated_aggregator Lambda
    │
    ├─ Scan all feedback records with delta_score + frs_after
    ├─ Quality gate: FRS > 0.60 AND DS > 0.65
    ├─ Group by developmental_stage (7 stages)
    ├─ Per stage:
    │   FedAvg across qualifying intent distributions
    │   + Gaussian DP noise (ε=1.0, δ=1e-5)
    │   + blend with research floor (10%)
    │
    └─ Write to PopulationModel table (1 row per stage)
        → Used by insight_generator on NEXT session as population_prior
```

---

## 4. Input Data Types

### 4.1 Audio Recording
| Property | Value |
|----------|-------|
| Format | WebM (audio/webm via MediaRecorder) |
| Duration | 5–30 seconds (min 5s enforced by UI) |
| Sample rate | Resampled to 22,050 Hz for processing |
| Source | Browser microphone (navigator.mediaDevices.getUserMedia) |

### 4.2 Session Context (Optional)
| Field | Type | When Shown | Values |
|-------|------|------------|--------|
| feeding_minutes_ago | int | 0–180 days | Minutes since last feed |
| health_state | string | Always (91+ days) | normal, sick, fussy, teething |
| environment | string | 91+ days | quiet, noisy, outdoors, car, other |
| notes | string | 181+ days (not for 0-6m) | Free text |

### 4.3 Parent Feedback (Post-Insight)
| Feedback Type | Fields | When Available |
|---------------|--------|----------------|
| Speaker verification | speaker_answer (adult/baby/both/older_child) | Speech or laugh detected |
| Cry emotion | was_correct (bool), confirmed_emotions[] | Cry or mixed detected |
| Language | baby_sound (text), parent_meaning (text) | Baby sound detected |
| Concept picker | selected concept labels | PROTO stage (12m+) |
| Transcription | corrected_text | LANGUAGE stage (24m+) |

---

## 5. Processing Pipeline (Step Functions)

### State Machine Definition

```
State 1: AudioClassifier         →  feature_extraction Lambda
    ↓
State 2: ShouldFastReject        →  Choice (check fast_reject flag)
    ├── true  → InsightGeneratorFastReject → ProcessingComplete
    └── false ↓
State 3: InsightGenerator         →  insight_generator Lambda
    ↓
State 4: ClusterEngine            →  cluster_engine Lambda (non-fatal)
    ↓
State 5: DevelopmentalTracker     →  developmental_tracker Lambda (non-fatal)
    ↓
ProcessingComplete (Succeed)
```

**Error handling:** States 4–5 are non-fatal (catch all errors, continue). States 1–3 retry 2–3 times with exponential backoff.

**Concept decoder and speech analyzer** are invoked within the developmental_tracker or as additional processing steps within the pipeline.

---

## 6. Feedback Loop

### 6.1 Feedback Processor (Synchronous)

Called directly by api_handler via Lambda invoke (RequestResponse mode).

**Language feedback path:**
1. Extract baby_sound, parent_meaning from payload
2. Get session's embedding_vector
3. Check for existing private language match (cosine similarity ≥ 0.75)
4. Store/update in ConceptGraph (category: "personal")
5. Link to acoustic cluster

**Cry emotion feedback path:**
1. Extract confirmed_emotion, was_correct
2. Derive age_bracket from child birth_date
3. Extract sound_features from session
4. Store training sample in TrainingCandidate table
5. If samples ≥ 20 per age bracket → trigger cry model retrain

### 6.2 Reinforcement Engine (Asynchronous)

Updates cluster learning signals based on parent effectiveness rating:

| Effectiveness | Weight Change |
|--------------|---------------|
| helpful | +0.10 (REINFORCEMENT_LEARNING_RATE) |
| neutral | -0.02 (REINFORCEMENT_DECAY_NEUTRAL) |
| ineffective | -0.05 (REINFORCEMENT_DECAY_INEFFECTIVE) |

Weight clamped to [0.0, 1.0].

Also updates:
- probable_intents distribution (increase/decrease confirmed intent)
- Semantic bridges (word↔cluster co-occurrence links)
- semantic_alignment_score on cluster

### 6.3 NLP Processor (Asynchronous)

Uses Bedrock Claude to extract structured data from parent free-text notes:
- extracted_intent: one of {hunger, thirst, sleep, discomfort, pain, cold, hot, connection, attention, comfort, fear}
- detected_objects: concrete nouns (bottle, teddy, blanket) — max 5
- confidence_modifier: 0.5–1.0

Results stored in ConceptGraph (both universal intents and personal objects).

---

## 7. Daily Aggregation (Federated Learning)

### Process

1. **Scan** all feedback records with `delta_score` and `frs_after` attributes
2. **Quality gate**: FRS > 0.60 AND delta_score > 0.65
3. **Group** qualifying records by developmental_stage (7 stages)
4. **Per stage:**
   - FedAvg: arithmetic mean of all local intent distributions
   - DP noise: Gaussian mechanism (ε=1.0, δ=1e-5)
   - Research floor blend: `final = 0.90 × noisy_avg + 0.10 × uniform_prior`
5. **Write** to PopulationModel table (one row per stage)
6. **Reliability flag**: `is_reliable = n_participants ≥ 10`

### Output (PopulationModel record)

```json
{
  "stage": "CANONICAL_BABBLE",
  "population_prior": {
    "hunger": 0.14, "fatigue": 0.10, "pain": 0.08,
    "discomfort": 0.14, "closeness": 0.14, "frustration": 0.11,
    "happy": 0.09, "exploration": 0.15, "distress_unknown": 0.05
  },
  "n_participants": 47,
  "is_reliable": true,
  "epsilon": 1.0,
  "delta": 1e-5,
  "aggregated_at": "2026-03-01T00:00:00Z"
}
```

---

## 8. All Formulas & Calculations

### 8.1 Audio Quality Gate (Layer 0)

| Check | Formula | Threshold |
|-------|---------|-----------|
| Duration | Direct measurement | 3.0s ≤ d ≤ 600.0s |
| SNR | `SNR_dB = 10 × log₁₀(signal_mean / noise_mean)` (top/bottom 20% of RMS frames) | ≥ 10.0 dB |
| Silence ratio | `silent_frames / total_frames` (frame < 5% of peak RMS) | < 0.80 |
| Clipping ratio | `samples ≥ 0.99 / total_samples` | < 0.005 |
| Voiced energy | `frames > 3× noise_floor / total_frames` | ≥ 0.08 |

### 8.2 Formant Extraction (LPC)

- Analyze 7 evenly-spaced 25ms frames from middle 80% of audio
- LPC order: `min(2 + sr/1000, frame_length - 2)`
- Pre-emphasis coefficient: 0.97
- Window: Hamming
- Extract roots → filter (imag ≥ 0.01, |root| < 1.0, 90 Hz ≤ f ≤ sr/2 - 100 Hz)
- Extract F1, F2, F3, F4 → take median across frames

### 8.3 Vocal Tract Length (VTL)

```
VTL = c(T) / (2 × ΔF̄)   [cm]

where:
  ΔF̄ = mean(F2-F1, F3-F2, F4-F3)   [Hz]
  c(T) = (331.3 + 0.606 × T) × 100   [cm/s]   (T in °C, default 20°C)
```

At 20°C: c = 34,330 cm/s

**Reference VTL ranges:**
| Age | VTL (cm) | Approx ΔF̄ (Hz) |
|-----|----------|-----------------|
| 0–6 months | 6–8 | 2145–1608 |
| 6–18 months | 8–11 | 1608–1169 |
| 18–24 months | 10–12 | 1169–975 |
| Adult female | 14–17 | 699–577 |
| Adult male | 16–18 | 611–543 |

**Adult threshold:** VTL ≥ 13.0 cm → classified as adult speaker

### 8.4 Jitter (Pitch Stability)

```
Jitter% = mean(|F0ᵢ₊₁ - F0ᵢ|) / mean(F0) × 100
```

### 8.5 Shimmer (Amplitude Stability)

```
Shimmer_linear = mean(|RMSᵢ₊₁ - RMSᵢ|) / mean(RMS)
Shimmer_dB = -20 × log₁₀(1 - Shimmer_linear)
```

### 8.6 HNR (Harmonics-to-Noise Ratio)

```
HNR = 10 × log₁₀(r / (1 - r))   [dB]

where r = normalized autocorrelation peak in F0 range (50–500 Hz)
Clipped to [-20, 40] dB
```

### 8.7 Spectral Entropy

```
H = -Σ pᵢ × log₂(pᵢ)

where pᵢ = power_bandᵢ / Σ power_bands
```

### 8.8 CBR (Canonical Babbling Ratio) Estimate

```
voice_quality = clamp((hnr_db - 3) / 10, 0, 1)

formant_factor =
  1.0  if F1 > 300 AND F2 > 700
  0.6  if F1 > 200
  0.3  otherwise

cbr_estimate = babble_fraction × voice_quality × formant_factor
```

### 8.9 CBR EMA (Exponential Moving Average)

```
α = 0.30 (default)
  if stage_transition:  α = min(0.80, α + 0.50)
  if cbr_trend == FALLING: α = max(0.10, α - 0.10)

cbr_ema_new = α × current_cbr + (1 - α) × cbr_ema_old
```

CBR trend: `delta = current_cbr - oldest_cbr` (5-session window)
- RISING: delta > 0.08
- FALLING: delta < -0.08
- STABLE: otherwise

### 8.10 φ (Phi) Order Parameter — Language Readiness

```
φ = 0.30 × cbr_ema
  + 0.25 × cluster_stability
  + 0.20 × f2_diversity
  + 0.15 × cross_situational
  + 0.10 × parent_trust

clamped to [0, 1]
```

| Component | Derivation |
|-----------|-----------|
| cbr_ema | From child profile (see 8.9) |
| cluster_stability | clusters_with_freq≥3 / total_clusters |
| f2_diversity | std(F2 across last 5 sessions) / 500.0, clamped [0,1] |
| cross_situational | context_reliability from child profile |
| parent_trust | parent_trust_score from child profile |

**Labels:**
| φ Range | Label |
|---------|-------|
| < 0.25 | Early vocal exploration |
| 0.25–0.45 | Language signals forming |
| 0.45–0.65 | Patterns stabilizing |
| ≥ 0.65 | Rich personal vocabulary |

### 8.11 Three-Source Evidence Model

#### Source Weights (Stage-Specific Base)

| Stage | Acoustic | Research | Feedback |
|-------|----------|----------|----------|
| NEWBORN (0–3m) | 45% | 40% | 15% |
| EARLY_VOCAL (3–6m) | 50% | 30% | 20% |
| CANONICAL_BABBLE (6–9m) | 55% | 25% | 20% |
| PROTO_WORDS (9–12m) | 58% | 20% | 22% |
| FIRST_WORDS (12–18m) | 62% | 15% | 23% |
| WORD_COMBINATIONS (18–24m) | 65% | 12% | 23% |
| EARLY_SENTENCES (24m+) | 70% | 10% | 20% |

#### Source 1: Acoustic Intent Scores

Computed from 4 primary feature scores + 5 rich features:

```
distress = emotional_intensity×0.65 + min(cry_fraction, 0.8)×0.35
calm = 1 - emotional_intensity
irregular = 1 - rhythm
bursty = 1 - expressive_flow
social_harmonic = clamp(hnr_db / 20, 0, 1)
high_jitter = clamp((jitter_pct - 3) / 17, 0, 1)
high_pause = clamp((pause_ratio - 0.45) / 0.55, 0, 1)
syllable_activity = clamp(syllable_rate / 6, 0, 1)
```

**Intent formulas:**

| Intent | Formula |
|--------|---------|
| hunger | distress×0.36 + rhythm×0.24 + repetition×0.14 + cry_fraction×0.26 |
| fatigue | calm×0.20 + repetition×0.26 + bursty×0.30 + high_pause×0.24 |
| pain | distress×0.40 + high_jitter×0.35 + irregular×0.15 + cry_fraction×0.10 |
| discomfort | distress×0.34 + irregular×0.24 + high_jitter×0.20 + repetition×0.12 + cry_fraction×0.10 |
| closeness | calm×0.30 + expressive_flow×0.30 + social_harmonic×0.25 + (1-high_pause)×0.15 |
| frustration | emotional_intensity×0.34 + irregular×0.22 + repetition×0.20 + bursty×0.14 + high_jitter×0.10 |
| happy | calm×0.28 + expressive_flow×0.24 + social_harmonic×0.32 + syllable_activity×0.16 |
| exploration | calm×0.24 + (1-repetition)×0.26 + expressive_flow×0.20 + syllable_activity×0.18 + social_harmonic×0.12 |
| distress_unknown | distress×0.55 + irregular×0.15 + high_jitter×0.10 + bonus adjustments |

#### Source 2: Research Priors

Stage-specific base distributions (example for NEWBORN):
```
hunger: 0.24, fatigue: 0.10, pain: 0.15, discomfort: 0.20,
closeness: 0.11, frustration: 0.07, happy: 0.03, exploration: 0.03,
distress_unknown: 0.07
```

**Context adjustments** (scaled by context_reliability):
- Feeding ≥180m ago: hunger += 0.20 × cr
- Feeding ≤30m ago: hunger -= 0.12 × cr
- Sick: discomfort += 0.12×cr, pain += 0.08×cr
- Teething: pain += 0.12×cr, discomfort += 0.10×cr

#### Source 3: Feedback History

From cluster's `probable_intents` distribution, maintained by reinforcement_engine.

#### Blending

```
blended[intent] = acoustic_w × acoustic[intent]
                + research_w × research[intent]
                + feedback_w × feedback[intent]
```

**FRS dynamic weighting:**
```
effective_feedback_w = base_feedback_w × max(0.1, FRS)
remaining = 1 - effective_feedback_w
acoustic_w = remaining × (base_acoustic / (base_acoustic + base_research))
research_w = remaining × (base_research / (base_acoustic + base_research))
```

#### Confidence Calculation

```
confidence = best_weight × (0.50 + reinforcement_weight × 0.25 × freq_factor) × sem_factor + agreement_bonus

where:
  best_weight = blended[top_intent]
  freq_factor = min(cluster.frequency_count / 10, 1)
  sem_factor = 1 + semantic_alignment_score × 0.20
  agreement_bonus = 0.05 if all 3 sources agree on top intent, else 0.0
```

**Confidence caps:**
| Condition | Max |
|-----------|-----|
| Always | 0.92 |
| ≤5 sessions | 0.40 |
| Weak signal (top acoustic < 0.30) | 0.35 |
| Floor | 0.10 |

### 8.12 Hunger vs Discomfort Resolution

When both are competitive (total ≥ 0.20, margin ≤ 0.12):
```
hunger_signal = distress×0.40 + rhythm×0.26 + repetition×0.18 + cry_fraction×0.16
discomfort_signal = distress×0.28 + irregular×0.34 + high_jitter×0.28 + cry_fraction×0.10

support_delta = acoustic_delta×0.46×reliability + pair_delta×0.22 + prior_delta×0.20 + context_delta×0.12

Shift: min(0.05, needed, 0.018 + support_delta × 0.22)
```

### 8.13 Proto-Word Criteria (5 Checks)

| # | Criterion | Threshold |
|---|-----------|-----------|
| 1 | stable_across_sessions | frequency_count ≥ 3 |
| 2 | sufficient_observations | frequency_count ≥ 5 |
| 3 | semantic_context | semantic_alignment_score ≥ 0.50 |
| 4 | effective_response | reinforcement_weight ≥ 0.65 |
| 5 | parent_confirmation | semantic_alignment_score > 0.0 |

**Status:**
- ESTABLISHED (aka CRYSTALLIZED): all 5 met AND semantic_alignment_score ≥ 0.85
- CANDIDATE: ≥3 criteria met
- NONE: <3 criteria met

### 8.14 MLU (Mean Length of Utterance)

```
utterances_per_sec = syllable_rate / (3.0 + pause_ratio × 2.0)

MLU = syllable_rate / utterances_per_sec   (if > 0, else 1.5)
clamped to [1.0, 6.0]
```

### 8.15 MLU EMA

```
mlu_ema_new = 0.25 × mlu + 0.75 × mlu_ema_old
```

### 8.16 Vocabulary Diversity

```
diversity = min(1, spectral_entropy / 10) + min(0.3, known_concepts × 0.015)
clamped to [0, 1]
```

### 8.17 Pragmatic Type Classification

| Type | Rule |
|------|------|
| question | f0_max > f0_mean × 1.4 (terminal pitch rise) |
| exclamation | f0_range > 200 AND syllable_rate > 5.0 |
| request | f0_range > 80 AND syllable_rate ≤ 5.0 |
| declaration | fallback default |

### 8.18 Fluency Score

```
voice_clarity = clamp((hnr_db - 3) / 15, 0, 1)
fluency = (1 - pause_ratio) × (0.6 + 0.4 × voice_clarity)
clamped to [0, 1]
```

### 8.19 Differential Privacy (Gaussian Mechanism)

```
σ = √(2 × ln(1.25/δ)) × sensitivity / ε

sensitivity = 2.0 / n_participants

noisy[intent] = max(0, prob + N(0, σ²))
→ re-normalize to probability simplex
```

For ε=1.0, δ=1e-5: σ ≈ 4.845 × sensitivity

### 8.20 Federated Averaging

```
μ̄[intent] = (1/N) × Σᵢ μᵢ[intent]   (equal-weight average)
```

### 8.21 Research Floor Blend

```
blended[intent] = research_floor × (1/n_intents) + (1 - research_floor) × population[intent]
re-normalize
```

research_floor = 0.10 (ensures population model cannot fully override literature priors)

### 8.22 Concept Confidence EMA

```
new_confidence = min(1.0, 0.10 × 1.0 + 0.90 × old_confidence)
```

### 8.23 Cluster Centroid Update (Incremental Mean)

```
new_centroid = (old_centroid × old_count + new_vector) / new_count
```

### 8.24 Speaker Classification

Scores computed across 6 categories based on F0, VTL, jitter, shimmer, HNR, spectral centroid:

| Category | F0 Range (Hz) | VTL Range (cm) |
|----------|---------------|----------------|
| Newborn | >450 | — |
| Infant | 300–450 | 8–10 |
| Toddler | 250–350 | 10–11 |
| Child | 200–300 | 11–13 |
| Adult female | 165–255 | 14–17 |
| Adult male | 85–180 | 16–18 |

**Adult detection threshold:** F0 < 250 Hz (INFANT_F0_MIN_HZ)

---

## 9. Lambda-by-Lambda Reference

### 9.1 feature_extraction

| Property | Value |
|----------|-------|
| Trigger | Step Functions State 1 |
| Memory | 1024 MB |
| Timeout | 60s |
| Input | child_id, session_id, s3_audio_path, session_context |
| Reads | ChildProfile (birth_date) |
| Writes | Session (classification data, features, biological) |
| Output | sound_type, is_adult, embedding_vector, rich_features, biological, routing, quality_gate |

**Processing:** Download audio → VAD trim → quality gate → extract 65+ features → diarize → classify sound → biological validation → save session

### 9.2 cluster_engine

| Property | Value |
|----------|-------|
| Trigger | Step Functions State 4 (non-fatal) |
| Memory | 512 MB |
| Timeout | 60s |
| Input | child_id, session_id, embedding_vector |
| Reads | SoundCluster (all for child) |
| Writes | SoundCluster (create/update), Session (cluster_id) |
| Output | cluster_id, action, similarity_score |

**Processing:** Query clusters → cosine similarity → attach (≥0.75) or create new → update centroid

### 9.3 insight_generator

| Property | Value |
|----------|-------|
| Trigger | Step Functions State 3 |
| Memory | 512 MB |
| Timeout | 60s |
| Input | All feature_extraction output |
| Reads | ChildProfile (name), ConceptGraph (private language), ModelRegistry (cry model), PopulationModel (FL prior) |
| Writes | Session (insight, insight_generated_at) |
| Output | insight card (headline, description, emotion, confidence, sections) |

**Processing:** Route by sound_type → evidence model blend → generate insight text → private language match → save

### 9.4 developmental_tracker

| Property | Value |
|----------|-------|
| Trigger | Step Functions State 5 (non-fatal) |
| Memory | 512 MB |
| Timeout | 30s |
| Input | child_id, session_id, cluster_id |
| Reads | Session (rich_features), ChildProfile (cbr_ema, parent_trust), SoundCluster (stability) |
| Writes | ChildProfile (cbr_ema, phi), Session (developmental_view), Milestones |
| Output | developmental_view (cbr, cbr_ema, vtl, phi, milestones) |

### 9.5 concept_decoder

| Property | Value |
|----------|-------|
| Trigger | Within pipeline after developmental_tracker |
| Memory | 512 MB |
| Timeout | 30s |
| Input | child_id, session_id, cluster_id |
| Reads | SoundCluster, ConceptGraph |
| Writes | Session (concept_decode) |
| Output | proto_word_status, top_concepts, unknown_flag |

### 9.6 speech_analyzer

| Property | Value |
|----------|-------|
| Trigger | Within pipeline (LINGUISTIC mode only) |
| Memory | 512 MB |
| Timeout | 60s |
| Input | child_id, session_id |
| Reads | Session (rich_features, mode), ChildProfile (mlu_ema), ConceptGraph (vocab count) |
| Writes | ChildProfile (mlu_ema, vocab_size), Session (speech_analysis), Milestones |
| Output | mlu, vocab_diversity, pragmatic_type, fluency_score |

### 9.7 feedback_processor

| Property | Value |
|----------|-------|
| Trigger | API Gateway POST /session/{id}/feedback (sync invoke) |
| Memory | 512 MB |
| Timeout | 30s |
| Input | feedback payload (language, cry_emotion, or general) |
| Reads | Session (embedding), ChildProfile (birth_date) |
| Writes | Feedback, ConceptGraph (language), TrainingCandidate (cry) |
| Invokes | reinforcement_engine (async), nlp_processor (async) |

### 9.8 reinforcement_engine

| Property | Value |
|----------|-------|
| Trigger | Async from feedback_processor |
| Memory | 512 MB |
| Timeout | 30s |
| Input | child_id, session_id, cluster_id, response_type, effectiveness, word_token |
| Reads | SoundCluster, SemanticBridge |
| Writes | SoundCluster (weights, intents), SemanticBridge |

### 9.9 nlp_processor

| Property | Value |
|----------|-------|
| Trigger | Async from feedback_processor (when notes present) |
| Memory | 512 MB |
| Timeout | 60s |
| Input | child_id, cluster_id, notes, session_id |
| Reads | — |
| Writes | ConceptGraph (objects + intents) |
| External | Bedrock Claude (anthropic.claude-3-5-haiku) |

### 9.10 federated_aggregator

| Property | Value |
|----------|-------|
| Trigger | EventBridge daily schedule |
| Memory | 512 MB |
| Timeout | 60s |
| Input | None (reads from tables) |
| Reads | Feedback (scan), Session, ChildProfile |
| Writes | PopulationModel (per stage) |

### 9.11 api_handler

| Property | Value |
|----------|-------|
| Trigger | API Gateway (all routes) |
| Memory | 512 MB |
| Timeout | 30s |
| Auth | Cognito JWT (user_id from claims) |
| Invokes | feedback_processor (sync), Step Functions (start) |

---

## 10. Shared Module Functions

### audio_utils.py

| Function | Purpose | Key I/O |
|----------|---------|---------|
| `audio_quality_gate(y, sr, duration)` | Validate audio quality | Returns {passed, issues, snr_db, silence_ratio, ...} |
| `extract_formants_lpc(y, sr)` | Extract F1–F4 via LPC | Returns {f1, f2, f3, f4} in Hz |
| `estimate_vtl_from_formants(formants, temp)` | Calculate vocal tract length | Returns VTL in cm |
| `compute_jitter(f0_contour)` | Pitch stability | Returns jitter % |
| `compute_shimmer(rms_contour)` | Amplitude stability | Returns shimmer linear |
| `compute_hnr(y, sr)` | Harmonics-to-noise ratio | Returns HNR in dB |
| `classify_speaker_type(f0, vtl, ...)` | Speaker age/type classification | Returns {type, scores, confidence} |

### rich_features.py

| Function | Purpose | Key I/O |
|----------|---------|---------|
| `extract_rich_features(y, sr)` | Extract all 65+ features | Returns dict with 8 feature groups |

**Feature groups:** prosodic (7), voice_quality (2), mfcc (39), spectral (7), temporal (5), formants (3), cry_babble (2), cbr_estimate (1)

### evidence_model.py

| Function | Purpose |
|----------|---------|
| `compute_acoustic_intent_scores(feature_scores, rich_features)` | Convert acoustic features to intent probabilities |
| `compute_research_priors(stage, context, cr, population_prior)` | Stage + context-adjusted priors |
| `blend_evidence_sources(acoustic, research, feedback, w1, w2, w3)` | Three-source weighted blend |
| `compute_intent_confidence(blended, cluster, acoustic, research, sessions)` | Final confidence with caps |
| `_resolve_hunger_discomfort_pair(...)` | Pairwise intent disambiguation |

### proto_word.py

| Function | Purpose |
|----------|---------|
| `check_proto_word_criteria(cluster)` | Evaluate 5 proto-word criteria → status |
| `compute_phi(cbr_ema, stability, f2_div, cross_sit, trust)` | Language readiness order parameter |

### language_analysis.py

| Function | Purpose |
|----------|---------|
| `estimate_mlu(rich_features)` | Mean Length of Utterance |
| `estimate_vocabulary_diversity(rich_features, known_concepts)` | Vocabulary variety score |
| `classify_pragmatic_type(rich_features)` | Utterance type (question/exclamation/request/declaration) |
| `score_fluency(rich_features)` | Speech fluency (0–1) |

### federated_learning.py

| Function | Purpose |
|----------|---------|
| `federated_average(distributions)` | FedAvg across participants |
| `add_gaussian_noise(dist, ε, δ, n)` | Differential privacy noise |
| `passes_quality_gate(frs, delta_score)` | FL inclusion check |
| `blend_with_research_floor(dist, floor, stage)` | Literature prior blend |
| `aggregate_stage(distributions, ε, δ)` | Full FL pipeline per stage |

### concept_graph.py

| Function | Purpose |
|----------|---------|
| `pre_populate_universal_concepts(child_id, table)` | Initialize 16 universal concepts |
| `upsert_concept(child_id, label, category, ...)` | Create/update concept entry |
| `get_concepts(child_id, table, limit)` | Retrieve top concepts by confirmation |

### constants.py

All thresholds, table names, developmental stages, intent labels. See Section 15 for complete reference.

---

## 11. API Routes & Data Contracts

### 11.1 Child Management

**GET /child** → List children for authenticated parent
```json
Response 200: {
  "children": [
    { "child_id": "uuid", "name": "Emma", "birth_date": "2025-06-15", "created_at": "..." }
  ]
}
```

**POST /child** → Create child (birth_date mandatory)
```json
Request: { "name": "Emma", "birth_date": "2025-06-15" }
Response 201: { "child_id": "uuid" }
```

**DELETE /child/{child_id}** → Delete child and all data
```json
Response 200: { "status": "deleted", "counts": { "sessions": 12, "feedback": 8, ... } }
```

### 11.2 Session Flow

**POST /session/upload** → Get presigned URL
```json
Request: { "child_id": "uuid", "session_context": { "health_state": "normal" } }
Response 200: { "session_id": "uuid", "upload_url": "https://s3...", "s3_key": "..." }
```

**POST /session/{id}/start** → Trigger pipeline
```json
Response 202: { "status": "processing_started", "execution_arn": "..." }
```

**GET /session/{id}/insight** → Get analysis results
```json
Response 200 (ready): {
  "status": "complete",
  "child_name": "Emma",
  "session_context": { "health_state": "normal" },
  "insight": {
    "sound_type": "cry",
    "display_type": "cry",
    "headline": "😢 Hunger cry detected",
    "description": "Emma's cry has a rhythmic, repetitive pattern...",
    "emotion": "hunger",
    "emotion_confidence": 0.72,
    "top_emotions": [
      { "intent": "hunger", "score": 0.72 },
      { "intent": "discomfort", "score": 0.15 }
    ],
    "insight_sections": {
      "what_i_hear": "Rhythmic crying with escalating intensity...",
      "what_it_means": "This pattern is commonly associated with hunger...",
      "what_to_try": "Try offering a feed..."
    }
  },
  "developmental_view": {
    "current_stage": "EARLY_VOCAL",
    "cbr": 0.12,
    "cbr_ema": 0.15,
    "vtl_cm": 7.8,
    "phi": 0.18,
    "phi_label": "Early vocal exploration"
  },
  "concept_decode": {
    "proto_word_status": "NONE",
    "top_concepts": []
  },
  "speech_analysis": null,
  "biological": { "vtl_cm": 7.8, "f0_hz": 380, "is_infant": true }
}

Response 202 (still processing): { "status": "processing" }
```

**POST /session/{id}/feedback** → Submit feedback
```json
Request (language): {
  "feedback_type": "language",
  "baby_sound": "ba-ba",
  "parent_meaning": "bottle"
}

Request (cry emotion): {
  "feedback_type": "cry_emotion",
  "was_correct": false,
  "confirmed_emotion": "fatigue"
}

Response 200: { "status": "feedback_processed", "feedback_id": "uuid" }
```

### 11.3 Data Retrieval

**GET /child/{id}/sessions** → Session list (most recent first, limit 50)

**GET /child/{id}/concepts** → Concept graph (top 20 by confirmation_count)

**GET /child/{id}/milestones** → Milestone log (most recent first)

**GET /child/{id}/language-signals** → Private language clusters
```json
Response 200: {
  "signals": [
    {
      "cluster_id": "uuid",
      "label": "ba-ba",
      "proto_word_status": "CRYSTALLIZED",
      "frequency_count": 12,
      "reinforcement_weight": 0.85
    }
  ]
}
```

**DELETE /account** → Delete all children and data for parent

---

## 12. DynamoDB Tables & Schemas

| Table | PK | SK | GSI | Purpose |
|-------|----|----|-----|---------|
| **ChildProfile** | child_id (S) | — | parent_id-index | Child metadata, CBR EMA, φ, parent trust |
| **Session** | session_id (S) | — | child_id-timestamp-index | Session data, features, insight, developmental view |
| **SoundCluster** | cluster_id (S) | — | child_id-last_updated-index | Acoustic cluster centroids, weights, intents |
| **SemanticBridge** | bridge_id (S) | — | child_id-index, cluster_id-index | Word↔cluster co-occurrence links |
| **Feedback** | feedback_id (S) | — | session_id-created_at-index | Parent feedback records, FRS, delta scores |
| **ConceptGraph** | child_id (S) | concept_id (S) | — | Personal + universal concepts |
| **Milestones** | child_id (S) | milestone_id (S) | child_id-first_date-index | Developmental milestones |
| **PopulationModel** | stage (S) | — | — | FL population priors per stage |
| **TrainingCandidate** | candidate_id (S) | — | developmental_stage-accepted_at-index | De-identified training samples |
| **ModelRegistry** | model_id (S) | — | developmental_stage-created_at-index | Trained model versions |

All tables: PAY_PER_REQUEST billing, server-side encryption, PITR enabled.

---

## 13. Frontend Pages & Data Consumption

### 13.1 Dashboard (`/`)

**Data sources:** GET /child, GET /child/{id}/sessions, localStorage
**Displays:** Child selector, session history grid, latest insight, recording button, settings panel
**Key behavior:** Clears previous child data on switch; persists selection in localStorage

### 13.2 Session Detail (`/session/:sessionId`)

**Data sources:** GET /session/{id}/insight (polled with progressive backoff 2–5s, max 20 polls)
**Displays:** Insight card (headline, emotion, description, sections), feedback form
**Key behavior:** 5-mode feedback schema (INFANT/BABBLE/PROTO/TODDLER/LANGUAGE)

### 13.3 Progress Page (`/progress/:childId`)

**Data sources:** GET /child/{id}/sessions, GET /child/{id}/milestones
**Displays:**
- CBR trend chart (last 12 sessions, % format)
- VTL growth chart (last 12 sessions, cm format, 20cm max bar)
- φ trend chart (0–1 scale)
- Interleaved session + milestone timeline
- Current snapshot: stage badge, φ label, CBR percentage

### 13.4 Language Page (`/language/:childId`)

**Data sources:** GET /child/{id}/language-signals, GET /child/{id}/concepts
**Displays:**
- Confirmed signals (CRYSTALLIZED proto-words)
- Emerging patterns (CANDIDATE proto-words)
- Personal vocabulary chips (concepts with ≥2 confirmations)
- Frequently heard sounds (≥3× frequency, NONE status)
- Signal cards: label, frequency, reinforcement weight, status badge

### 13.5 Frontend Tech Stack

| Library | Version | Purpose |
|---------|---------|---------|
| React | 18.x | UI framework |
| react-router-dom | 6.22 | Client-side routing |
| aws-amplify | 6.3 | Cognito authentication |
| @aws-amplify/ui-react | 6.1 | Auth UI components |
| recharts | 2.12 | Charts (RadarChart) |

**State management:** React hooks only (useState, useEffect, useCallback, useRef). No Redux or Context API.
**Auth:** Cognito JWT via fetchAuthSession(). All API calls include Bearer token.
**Caching:** localStorage for children list and selected child ID.

---

## 14. Infrastructure Summary

### AWS Services Used

| Service | Purpose |
|---------|---------|
| Lambda (container) | 10 processing functions + 1 API handler |
| API Gateway (REST) | 12 routes + CORS preflight |
| Step Functions | 6-state processing pipeline |
| DynamoDB | 10 tables (on-demand billing) |
| S3 | Audio storage (90-day retention) + frontend hosting |
| CloudFront | CDN for frontend SPA |
| Cognito | User authentication (email-based) |
| EventBridge | Daily FL aggregation trigger |
| ECR | Docker image registry (1 per Lambda) |
| Bedrock | Claude 3.5 Haiku for NLP + cry analysis |
| VPC | Private subnets for Lambda execution |
| CloudWatch | Logging + alarms |

### CI/CD (GitHub Actions)

| Workflow | Trigger | Action |
|----------|---------|--------|
| 1-infra-deploy | Push to staging (infrastructure/**) | Terraform plan + apply |
| 2-lambda-deploy | Push to staging (lambdas/**, shared/**) | Docker build → ECR → Lambda update |
| 3-frontend-deploy | Push to staging (frontend/**) | npm build → S3 → CloudFront invalidate |
| 4-infra-destroy | Manual with confirmation | Full teardown (10-phase) |

### Lambda Resource Allocation

| Lambda | Memory | Timeout |
|--------|--------|---------|
| feature_extraction | 1024 MB | 60s |
| cluster_engine | 512 MB | 60s |
| insight_generator | 512 MB | 60s |
| developmental_tracker | 512 MB | 30s |
| concept_decoder | 512 MB | 30s |
| speech_analyzer | 512 MB | 60s |
| feedback_processor | 512 MB | 30s |
| reinforcement_engine | 512 MB | 30s |
| api_handler | 512 MB | 30s |
| nlp_processor | 512 MB | 60s |

---

## 15. Constants & Thresholds Reference

### Audio Processing

| Constant | Value | Usage |
|----------|-------|-------|
| SAMPLE_RATE | 22,050 Hz | Audio resampling target |
| N_MFCC | 13 | MFCC coefficient count |
| HOP_LENGTH | 512 | Frame hop size |
| N_FFT | 2,048 | FFT window size |
| MAX_AUDIO_DURATION_SECONDS | 30 | Max recording length |

### Quality Gate

| Constant | Value |
|----------|-------|
| QUALITY_MIN_DURATION_SECONDS | 3.0 |
| QUALITY_MAX_DURATION_SECONDS | 600.0 |
| QUALITY_MIN_SNR_DB | 10.0 |
| QUALITY_MAX_SILENCE_RATIO | 0.80 |
| QUALITY_MAX_CLIPPING_RATIO | 0.005 |
| LOMBARD_NOISE_FLOOR_DB | -30.0 |

### Biological Validation

| Constant | Value |
|----------|-------|
| VTL_INFANT_MAX_CM | 13.0 |
| VTL_UNCERTAIN_MIN_CM | 12.5 |
| VTL_AMBIENT_TEMP_C | 20.0 |
| INFANT_F0_MIN_HZ | 250.0 |
| STRONG_INFANT_F0_HZ | 300.0 |

### Clustering & Reinforcement

| Constant | Value |
|----------|-------|
| CLUSTER_SIMILARITY_THRESHOLD | 0.85 (env) / 0.75 (code) |
| ALPHA_VALUE (EMA) | 0.30 |
| REINFORCEMENT_LEARNING_RATE | 0.10 |
| REINFORCEMENT_DECAY_NEUTRAL | 0.02 |
| REINFORCEMENT_DECAY_INEFFECTIVE | 0.05 |
| REINFORCEMENT_MAX | 1.0 |
| REINFORCEMENT_MIN | 0.0 |
| REINFORCEMENT_NEUTRAL_START | 0.5 |
| SEMANTIC_CONFIDENCE_INCREMENT | 0.05 |

### Federated Learning

| Constant | Value |
|----------|-------|
| FL_EPSILON | 1.0 |
| FL_DELTA | 1e-5 |
| FL_MIN_PARTICIPANTS | 10 |
| FL_FRS_QUALITY_GATE | 0.60 |
| FL_DELTA_QUALITY_GATE | 0.65 |
| FL_RESEARCH_FLOOR | 0.10 |
| FL_ROUND_INTERVAL_HOURS | 24 |

### Evidence Model

| Constant | Value |
|----------|-------|
| Default weights | 60% acoustic, 15% research, 25% feedback |
| Confidence ceiling | 0.92 |
| Early session cap (≤5) | 0.40 |
| Weak signal cap | 0.35 |
| Confidence floor | 0.10 |

### Developmental Stages

| Stage | Age Range | Mode |
|-------|-----------|------|
| NEWBORN | 0–90 days | PRE_LINGUISTIC |
| EARLY_VOCAL | 91–180 days | PRE_LINGUISTIC |
| CANONICAL_BABBLE | 181–270 days | PRE_LINGUISTIC |
| PROTO_WORDS | 271–365 days | TRANSITION |
| FIRST_WORDS | 366–548 days | LINGUISTIC |
| WORD_COMBINATIONS | 549–730 days | LINGUISTIC |
| EARLY_SENTENCES | 731+ days | LINGUISTIC |

### Milestone Types

| Milestone | Trigger |
|-----------|---------|
| FIRST_CANONICAL_BABBLE | CBR > 0.20 |
| FIRST_PROTO_WORD_CANDIDATE | Proto-word status = CANDIDATE |
| FIRST_CONFIRMED_PROTO_WORD | Proto-word status = CRYSTALLIZED |
| LINGUISTIC_MODE_TRANSITION | Mode changes to LINGUISTIC |
| FIRST_MLU_2 | MLU EMA ≥ 2.0 |
| FIRST_MLU_3 | MLU EMA ≥ 3.0 |
| VOCAB_SIZE_20 | Confirmed concepts ≥ 20 |
| VOCAB_SIZE_50 | Confirmed concepts ≥ 50 |
| CONCEPT_GRAPH_10_NODES | Concept graph ≥ 10 nodes |
| CONCEPT_GRAPH_25_NODES | Concept graph ≥ 25 nodes |

### Intent Labels (v2 Taxonomy)

hunger, fatigue, pain, discomfort, closeness, frustration, happy, exploration, distress_unknown, non_baby_spoof_noise

### Training Acceptance

| Constant | Value |
|----------|-------|
| TRAINING_ACCEPT_DELTA_MIN | 0.72 |
| TRAINING_ACCEPT_FRS_MIN | 0.70 |
| TRAINING_ACCEPT_ACOUSTIC_RELIABILITY_MIN | 0.62 |
| TRAINING_ACCEPT_TOP_MARGIN_MIN | 0.08 |
| TRAINING_ACCEPT_SCORE_MIN | 0.76 |

### Private Language Model

| Constant | Value |
|----------|-------|
| PRIVATE_LANG_MATCH_THRESHOLD | 0.75 |
| PRIVATE_LANG_MIN_OBSERVATIONS | 2 |

### Cry Model

| Constant | Value |
|----------|-------|
| CRY_MODEL_RETRAIN_THRESHOLD | 20 |
| CRY_MODEL_MIN_SAMPLES_PER_EMOTION | 5 |
| CRY_MODEL_MIN_TOTAL_SAMPLES | 15 |

---

## File Index

### Lambda Handlers
- `lambdas/feature_extraction/handler.py`
- `lambdas/cluster_engine/handler.py`
- `lambdas/insight_generator/handler.py`
- `lambdas/developmental_tracker/handler.py`
- `lambdas/concept_decoder/handler.py`
- `lambdas/speech_analyzer/handler.py`
- `lambdas/feedback_processor/handler.py`
- `lambdas/reinforcement_engine/handler.py`
- `lambdas/nlp_processor/handler.py`
- `lambdas/federated_aggregator/handler.py`
- `lambdas/api_handler/handler.py`

### Shared Modules
- `shared/audio_utils.py` — Formants, VTL, quality gate, speaker classification
- `shared/evidence_model.py` — Three-Source Evidence Model, confidence
- `shared/rich_features.py` — 65+ acoustic features (8 groups)
- `shared/proto_word.py` — Proto-word criteria, φ parameter
- `shared/language_analysis.py` — MLU, diversity, pragmatic type, fluency
- `shared/federated_learning.py` — FedAvg, DP noise, research floor
- `shared/concept_graph.py` — Concept CRUD, universal concepts
- `shared/constants.py` — All thresholds, table names, stages

### Frontend
- `frontend/src/App.js` — Router (4 routes)
- `frontend/src/pages/Dashboard.js` — Main page, child management, recording
- `frontend/src/pages/SessionDetail.js` — Insight display, feedback form
- `frontend/src/pages/ProgressPage.js` — CBR/VTL/φ charts, timeline
- `frontend/src/pages/LanguagePage.js` — Proto-words, concepts, signals
- `frontend/src/components/RecordButton.js` — Audio capture, upload, context
- `frontend/src/components/FeedbackForm.js` — 5-mode feedback submission
- `frontend/src/components/InsightPanel.js` — Insight card rendering

### Infrastructure
- `infrastructure/modules/step_functions/main.tf` — Pipeline state machine
- `infrastructure/modules/api_gateway/main.tf` — REST API + CORS
- `infrastructure/modules/dynamodb/main.tf` — 10 tables
- `infrastructure/modules/lambda/main.tf` — 10 Lambda functions
- `infrastructure/modules/cognito/main.tf` — User auth
- `infrastructure/modules/s3/main.tf` — Audio storage
- `infrastructure/modules/frontend/main.tf` — CloudFront + S3 hosting
