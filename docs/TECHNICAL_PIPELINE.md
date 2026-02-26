# Technical Architecture: Evolving Processing Pipeline for Infant Vocalization Intelligence

**Document Type:** Technical Specification
**Project:** Qleam — Infant Vocalization Intelligence System
**Version:** 1.0
**Date:** 2026-02-24
**Status:** Reference Architecture

---

## 1. System Overview

### 1.1 High-Level Architecture

The Qleam system is organized as a 10-layer sequential processing pipeline (Layers 0–9), a parallel dataset ecosystem of four distinct data stores, a federated learning orchestration layer, and an AWS serverless infrastructure backing. The architecture is fundamentally event-driven: a new audio recording triggers the pipeline; each layer gates and enriches the session record before passing it to the next.

```
=============================================================================
                     QLEAM SYSTEM ARCHITECTURE (v2.0)
=============================================================================

AUDIO INPUT
    |
    v
+------------------+     +---------------------+     +--------------------+
| MOBILE CLIENT    |---->| AWS API GATEWAY      |---->| STEP FUNCTIONS     |
| iOS / Android    |     | REST + WebSocket     |     | PIPELINE ORCHESTR. |
+------------------+     +---------------------+     +--------------------+
                                                              |
              +-----------------------------------------------+
              |
              v
+==============================================================================+
|  PIPELINE LAYERS (sequential, each gates the next)                          |
+==============================================================================+
|                                                                              |
|  L0: AUDIO QUALITY GATE                                                     |
|      SNR check | Clipping detect | Duration validate | Silence ratio         |
|      Lombard Effect flag | Temperature correction                            |
|      OUTPUT: PASS / REJECT(reason)                                           |
|           |                                                                  |
|           v                                                                  |
|  L1: BIOLOGICAL VALIDATION GATE                                              |
|      VTL estimation | F0 range classify | Glottal source analysis            |
|      Jitter/Shimmer profile | Nonlinear dynamics check                       |
|      OUTPUT: INFANT_CONFIRMED / REJECT / UNCERTAIN                           |
|           |                                                                  |
|           v                                                                  |
|  L2: SPEAKER IDENTITY                                                        |
|      Age group classification | Speaker diarization                          |
|      Enrolled baby verification | Session-count confidence floor             |
|      OUTPUT: identity_confirmed + developmental_stage + speaker_segments     |
|           |                                                                  |
|           v                                                                  |
|  L3: CONTEXT COLLECTION                                                      |
|      Device clock | Weather API | Parent questionnaire                       |
|      Audio-derived context | Session history                                 |
|      OUTPUT: context_bundle attached to session_record                       |
|           |                                                                  |
|           v                                                                  |
|  L4: RICH FEATURE EXTRACTION (50-80 features)                               |
|      Temporal(7) | Spectral(7) | Cepstral/Formant(8)                         |
|      Pitch/Prosodic(8) | Voice Quality(5) | Developmental(5)                 |
|      Nonlinear Dynamics(4) + wav2vec2/HuBERT embeddings (optional)           |
|      OUTPUT: feature_vector(50-80D) + acoustic_confidence                    |
|           |                                                                  |
|           v                                                                  |
|  L5: PER-SESSION INSIGHT (Three-Source Evidence Model)                      |
|      Acoustic-only score | Research prior | Trust-modulated feedback         |
|      Dimensional classification (Arousal x Valence)                         |
|      Confidence formula | Source agreement check | Health flag                |
|      OUTPUT: intent_distribution + confidence + reasoning + flags            |
|           |                                                                  |
|           v                                                                  |
|  L6: DYADIC INTERACTION ANALYSIS                                            |
|      Turn-taking timing | Contingent responsiveness                          |
|      Acoustic imitation | F0 convergence | Parentese detection               |
|      OUTPUT: interaction_quality_score + dyadic_synchrony                    |
|           |                                                                  |
|           v                                                                  |
|  L7: LONGITUDINAL DEVELOPMENTAL TRACKING                                    |
|      Stage classification | CBR trend | VTL growth curve                     |
|      Adaptive EMA baseline | Regression detection | Milestone logging         |
|      OUTPUT: developmental_stage + trajectory + deviation_flag               |
|           |                                                                  |
|           v                                                                  |
|  L8: PRIVATE LANGUAGE EXTRACTION                                            |
|      Cross-situational meaning map | Proto-word crystallization              |
|      Personal concept graph update | Phoneme inventory | phi order param      |
|      OUTPUT: concept_graph_update + proto_word_candidates + phi               |
|           |                                                                  |
|           v                                                                  |
|  L9: PARENT INTERFACE (Progressive Disclosure)                              |
|      Session view | Developmental progress | Private language page           |
|      Language emergence indicator | Journey view                             |
|      OUTPUT: parent-facing JSON for mobile rendering                         |
|                                                                              |
+==============================================================================+

PARALLEL DATA FLOWS:
    |                     |                    |
    v                     v                    v
+----------+     +--------------+     +------------------+
| INDIVID. |     | POPULATION   |     | FEDERATED        |
| BABY DB  |     | MODEL DB     |     | AGGREGATOR       |
| DynamoDB |     | (aggregated) |     | (gradient avg)   |
+----------+     +--------------+     +------------------+
                        ^
                        |
            +---------------------+
            | OLD RESEARCH DATASET|
            | (static prior base) |
            +---------------------+
```

### 1.2 Technology Stack Summary

| Layer | Technology | Role |
|-------|------------|------|
| Mobile Client | React Native / Swift / Kotlin | Audio capture, UI rendering |
| API Gateway | AWS API Gateway | REST endpoint for session submission |
| Pipeline Orchestration | AWS Step Functions | Sequential layer execution with error handling |
| Compute | AWS Lambda (Python) | Per-layer processing functions |
| Audio Storage | AWS S3 | Temporary raw audio; feature vectors long-term |
| Baby Data | AWS DynamoDB | Per-baby session records, concept graph, embeddings |
| Population Model | AWS S3 + SageMaker | Federated model weights; training jobs |
| LLM Generation | AWS Bedrock (Claude) | Natural language output generation only |
| Weather Context | OpenMeteo API | Temperature, humidity, barometric pressure |
| Feature Extraction | Python: librosa, scipy, parselmouth | Audio feature computation |
| Deep Embeddings | HuggingFace wav2vec2/HuBERT | Optional rich embeddings |
| NLP Pipeline | spaCy / HuggingFace transformers | Parent free text concept extraction |
| Graph Storage | DynamoDB (adjacency list) or Neptune | Personal concept graph per baby |

---

## 2. Processing Pipeline Evolution

The pipeline is not static. As the child develops from pre-linguistic infant to speaking child, different processing stages activate, deactivate, or change their internal logic. The developmental mode (pre-linguistic, transitional, linguistic) is determined by Layer 2's Developmental Mode Detection and routes the session through the appropriate sub-pipeline.

### 2.1 Stage A: Pre-Linguistic Pipeline (0–18 Months)

**Dominant activity:** Layers 0–8 all active, with focus on acoustic validation, feature extraction, dimensional intent inference, and concept graph building.

**Key characteristics:**
- Biological validation gate is most critical — infants in this stage cannot produce linguistic speech, so the acoustic signal is entirely non-linguistic.
- Intent inference operates entirely from acoustic features, context, and dimensional model (Arousal × Valence space).
- Concept graph is building from parent free text and context co-occurrence.
- Proto-word crystallization begins around 9–12 months; detection begins in Layer 8.
- Parent feedback mechanism uses fixed physiological categories (0–6 months) evolving to personal concept graph options (6–18 months).

**Layer 5 in Stage A:**
- Dimensional classification outputs (arousal, valence) + top 3 categorical interpretation
- Research prior weight highest (0.25) early, decreasing to 0.15 as population model matures
- Session calibration factor caps confidence at 0.40 for first 5 sessions

**Layer 8 in Stage A:**
- Cross-situational co-occurrence tracking active from session 1
- Proto-word crystallization monitoring begins at ~6 months developmental age
- Personal concept graph nodes grow: universal layer active from birth, personal layer activating at 6 months
- φ order parameter computed but not surfaced to parent until meaningful

### 2.2 Stage B: Transition Pipeline (18–24 Months)

**Dominant activity:** Hybrid pipeline — pre-linguistic intent inference runs in parallel with early word detection. Both pipelines active simultaneously.

**Key characteristics:**
- Developmental Mode Detection (DMD) has classified mode as MODE_TRANSITION.
- Some recordings will contain recognizable words; others will remain fully pre-linguistic.
- Voice Onset Time (VOT) patterns begin appearing, detected in Layer 4.
- Word-like units detectable via syllable structure analysis.
- Parent free text transitions to primary input method; free text NLP runs on every session.
- Concept graph is richest at this stage — near-maximum personal concept density.
- Stream Decoder (real-time concept graph lookup) is fully active.

**Layer 4 additions in Stage B:**
- VOT measurement added
- Utterance-level prosodic analysis (sentence-level F0 contour detection)
- Word-boundary acoustic structure detection

**Layer 5 in Stage B:**
- Dual output: pre-linguistic intent distribution AND word candidate list
- Hybrid confidence: concepts from concept graph receive higher weight than dimensional-only inference
- If word detected with confidence > 0.70, surface as word rather than acoustic cluster

**Layer 8 in Stage B:**
- Stream Decoder active: real-time concept-cluster lookup per acoustic segment
- Proto-word crystallization ongoing — established signals named in output
- φ order parameter rising; parent-facing emergence indicator active

### 2.3 Stage C: Linguistic Pipeline (24+ Months)

**Dominant activity:** Pre-linguistic analysis terminates. Speech analysis pipeline activates. Layer 8 transitions from concept graph building to linguistic development tracking.

**Key characteristics:**
- DMD has classified mode as MODE_LINGUISTIC.
- Pre-linguistic intent inference STOPS (applying pre-linguistic analysis to a speaking child produces invalid results).
- Speech analysis pipeline produces: MLU, vocabulary diversity, phonological accuracy, sentence structure, pragmatic classification.
- Emotional prosody extraction continues — HOW the child says something remains analytically valuable.
- Concept graph knowledge is preserved as semantic background for speech analysis context.
- Parent interface transitions to developmental milestone tracking mode.

**New Layer 4 features in Stage C:**
- Word boundary detection (prosodic, spectral, VOT-based)
- Utterance segmentation into word tokens
- Phoneme-level accuracy analysis
- Sentence prosody classification

**Layer 5 in Stage C:**
- Intent inference replaced by linguistic content analysis
- Output: what the child communicated (semantic content) + how they communicated (prosodic/articulatory quality)
- Developmental milestone comparison against age norms

**Layer 8 in Stage C:**
- Private language mapping transitions to vocabulary tracking
- Established proto-words linked to their conventional word successors
- Language journey documentation active

---

## 3. Each Pipeline Layer in Detail

### Layer 0: Audio Quality Gate

**Purpose:** Ensure the raw audio recording meets minimum quality standards for any analysis to proceed. This is the foundational gate — everything else depends on clean input.

**Runtime optimization (implemented):** Critical failures (`no_signal`, `no_vocal_activity_detected`, `too_short`) trigger a fast-reject short-circuit. The pipeline generates a rejection insight immediately and skips expensive downstream stages (clustering, longitudinal tracking, concept decoding, speech analysis) for that session.

**Input Specification:**
```
{
  "audio_file": "s3://qleam-audio/{baby_id}/{session_id}.wav",
  "format": "WAV | WebM | AAC",
  "sample_rate": 44100,  // or 16000, 22050 — normalized during processing
  "channels": 1,         // mono required; stereo converted
  "duration_seconds": float,
  "upload_timestamp": ISO8601,
  "device_info": { "os": str, "model": str, "microphone_type": str }
}
```

**Processing Algorithms:**

*SNR Measurement:*
```
signal_rms = sqrt(mean(x_voiced_frames^2))
noise_rms  = sqrt(mean(x_silent_frames^2))
SNR_dB     = 20 * log10(signal_rms / noise_rms)
THRESHOLD  = 10 dB (reject below)
```

*Clipping Detection:*
```
clipping_ratio = count(|x| > 0.98 * max_amplitude) / total_samples
REJECT if clipping_ratio > 0.005 (more than 0.5% of samples clipped)
```

*Duration Validation:*
```
minimum_duration = 3.0 seconds  (too short for meaningful feature extraction)
maximum_duration = 600 seconds  (above this, segment into sub-sessions)
REJECT if duration < minimum_duration
SEGMENT if duration > maximum_duration
```

*Silence Ratio:*
```
frame_rms per 10ms frame
silence_frame = frame_rms < adaptive_threshold (percentile-based)
silence_ratio = count(silence_frames) / total_frames
REJECT if silence_ratio > 0.80 (recording is mostly silence)
```

*Lombard Effect Flag:*
```
background_noise_level = median(SNR over silent frames) inverted
If SNR variance is high AND background_noise_level > 55 dB SPL:
  FLAG: lombard_effect_likely = True
  estimate_lombard_shift_Hz = 0.25 * (background_dB - 55)  // ~0.25 Hz shift per dB
  record for downstream correction in Layer 4
```

*Temperature Correction:*
```
temperature_celsius = from_context_bundle (weather API, default 20°C)
speed_of_sound = 331.0 + 0.6 * temperature_celsius  // m/s
store: c_corrected for use in Layer 1 VTL estimation
```

**Output Schema:**
```json
{
  "quality_gate": "PASS | REJECT",
  "reject_reason": "null | SNR_TOO_LOW | CLIPPING | TOO_SHORT | MOSTLY_SILENCE",
  "snr_db": 24.3,
  "clipping_ratio": 0.0001,
  "duration_seconds": 47.2,
  "silence_ratio": 0.31,
  "lombard_flag": false,
  "lombard_shift_estimate_hz": 0.0,
  "speed_of_sound_corrected": 343.0,
  "normalized_audio_path": "s3://qleam-processed/{session_id}_norm.wav"
}
```

**Error Conditions:**
- `AUDIO_UNREADABLE`: file corrupt or undecodable — surface to parent with retry prompt
- `SAMPLE_RATE_UNSUPPORTED`: resample to 16kHz before processing
- `DURATION_ZERO`: file empty — discard silently

---

### Layer 1: Biological Validation Gate

**Purpose:** Determine whether the vocalization in the recording is consistent with infant anatomy. This gate uses physics that cannot be defeated by pitch manipulation.

**Input:** Normalized audio from Layer 0 + temperature-corrected speed of sound.

**Processing Algorithms:**

*Formant Extraction (F1–F4):*
```
method: LPC peak-picking (order = 2 + sample_rate/1000)
   OR: Praat/parselmouth formant tracker
   OR: STRAIGHT algorithm for clean signals

F1, F2, F3, F4 = peaks of LPC spectrum in expected frequency ranges
F1: 200–1200 Hz (infant), 200–900 Hz (adult female), 200–800 Hz (adult male)
F2: 700–3500 Hz (infant), 700–2800 Hz (adult)
F3: 1800–5000 Hz (infant), 1800–4000 Hz (adult)
F4: 3000–6000 Hz (infant), 3000–5000 Hz (adult)
```

*Vocal Tract Length (VTL) Estimation:*
```
mean_formant_spacing = mean(F2-F1, F3-F2, F4-F3)
VTL_cm = (c_corrected / (2 * mean_formant_spacing)) * 100

INTERPRETATION:
  VTL < 8.5 cm: NEWBORN range (0-3 months typical)
  VTL 8.5-11.0 cm: INFANT range (3-12 months typical)
  VTL 11.0-12.5 cm: TODDLER range (12-24 months typical)
  VTL > 12.5 cm: CHILD/ADULT range

GATE: VTL > 13.0 cm -> REJECT "Adult vocal tract detected"
      VTL 12.5-13.0 cm -> UNCERTAIN "Marginal infant/child boundary"
```

*F0 Range Classification:*
```
F0 estimation: YIN algorithm or CREPE (neural F0 tracker)
F0_median = median of all voiced frames

GATE: F0_median < 200 Hz -> likely adult male (REJECT)
      F0_median < 230 Hz + VTL > 12.5 cm -> likely adult female (REJECT)
      F0_median 250-600 Hz -> consistent with infant
```

*Glottal Source Analysis:*
```
Glottal pulse characteristics:
  H1-H2 difference (spectral tilt) — infant glottal pulses have distinct H1-H2 profile
  Glottal closure rate (derived from inverse filtering)

Adult glottal profile classifier (trained on known adult/infant data):
  Features: H1-H2, open quotient estimate, closure ratio
  If adult_glottal_probability > 0.80 -> REJECT
```

*Jitter/Shimmer Profile:*
```
Jitter = mean(|T_n - T_{n-1}|) / mean(T_n)
Shimmer = mean(|A_n - A_{n-1}|) / mean(A_n)

Expected ranges:
  Infant:      Jitter 1.5-4.0%, Shimmer 2.0-5.0% (higher irregularity is normal)
  Adult female: Jitter 0.5-2.5%, Shimmer 1.0-3.5%
  Adult male:   Jitter 0.3-1.8%, Shimmer 0.8-2.8%
  Pain cry:     Jitter > 5.0%, Shimmer > 6.0% (distinct from all adult profiles)

Adult voice profile detector: Mahalanobis distance from infant jitter/shimmer distribution
If distance > threshold -> REJECT
```

*Nonlinear Dynamics Screening:*
```
Maximum Lyapunov exponent (λ₁) from phase space reconstruction:
  Embedding dimension m = 6-10 (Cao's method for optimal d)
  Time delay τ = first minimum of mutual information

  λ₁ > 0.3 bits/period: chaotic (consistent with pain cry, extreme distress)
  λ₁ 0.0-0.3: periodic/quasi-periodic (normal vocalization)
  λ₁ < 0 (unlikely in cry): stable

Adult cry produced under artificial conditions has different λ₁ profile from infant cry
Used as supplementary discriminant when VTL/F0/glottal analysis is marginal
```

**Output Schema:**
```json
{
  "biological_gate": "INFANT_CONFIRMED | REJECT | UNCERTAIN",
  "reject_reason": "null | ADULT_VTL | ADULT_F0 | ADULT_GLOTTAL | ADULT_JITTER",
  "vtl_cm": 9.2,
  "vtl_age_category": "INFANT_3_12M",
  "f0_median_hz": 380.0,
  "f0_category": "INFANT",
  "glottal_adult_probability": 0.08,
  "jitter_percent": 2.8,
  "shimmer_percent": 3.4,
  "lyapunov_exponent": 0.18,
  "formants": { "F1": 780, "F2": 2100, "F3": 3400, "F4": 4600 },
  "estimated_developmental_stage_from_biology": "INFANT_6_12M",
  "confidence": 0.91
}
```

**Error Conditions:**
- `FORMANT_EXTRACTION_FAILED`: extreme noise or cry phonation suppresses formant structure — attempt backup algorithm (autocorrelation-based), flag as UNCERTAIN if fails
- `SIGNAL_TOO_SHORT_FOR_VTL`: utterance < 500ms — insufficient for reliable formant extraction, fall back to F0-only gate
- `HIGHLY_DISTRESSED_CRY`: extreme phonation suppresses formant structure — VTL gate bypassed, Lyapunov exponent used as primary discriminant

---

### Layer 2: Speaker Identity

**Purpose:** Determine which baby this is, confirm it matches the enrolled child, and classify the developmental stage.

**Processing Algorithms:**

*Developmental Age Group Classification:*
```python
THRESHOLDS = {
  'NEWBORN':        {'vtl_max': 8.5,  'f0_min': 380},
  'YOUNG_INFANT':   {'vtl': (8.5, 9.5),  'f0': (300, 450)},   # 3-6 months
  'OLDER_INFANT':   {'vtl': (9.5, 11.0), 'f0': (260, 380)},   # 6-12 months
  'TODDLER':        {'vtl': (11.0, 12.5),'f0': (220, 330)},   # 12-24 months
  'YOUNG_CHILD':    {'vtl_min': 12.5, 'f0': (180, 280)}        # 2-4 years
}
# VTL from Layer 1, F0 from Layer 1
# Output: developmental_stage in [NEWBORN, YOUNG_INFANT, OLDER_INFANT, TODDLER, YOUNG_CHILD]
```

*Speaker Diarization:*
```
If multiple voices detected in recording:
  Segment audio by voice activity detection (VAD)
  Embed each segment using x-vector or d-vector extractor
  Cluster embeddings: 2-5 speakers (k-means with BIC for k selection)
  Label each cluster: INFANT | OLDER_CHILD | ADULT (from VTL/F0 profile)
  Extract: infant-only segments for downstream analysis
  Record: which other speakers present (contextual metadata)
```

*Enrolled Baby Verification:*
```
Load: enrolled_embedding_history for baby_id
      (list of (embedding, session_id, session_count) tuples)

enrolled_centroid = weighted_mean(embeddings, weights=session_recency_weights)

new_embedding = mean_embedding over infant-only segments (from current session)

cosine_similarity = dot(new_embedding, enrolled_centroid) /
                    (norm(new_embedding) * norm(enrolled_centroid))

stage_consistency_factor:
  same_stage_as_enrolled_history: 1.0
  adjacent_stage (expected growth): 0.85
  unexpected_stage_jump: 0.60 (flag for review)

session_count_confidence = min(enrolled_session_count / 20, 1.0)

verification_score = cosine_similarity * stage_consistency_factor * session_count_confidence

THRESHOLDS:
  > 0.80: CONFIRMED — proceed
  0.55-0.80: UNCERTAIN — proceed with reduced downstream confidence
  < 0.55: FLAG "May not be enrolled baby" — notify parent, proceed with low confidence
```

*Developmental Mode Detection (DMD):*
```
MODE_PRELINGUISTIC:
  CBR < 0.80 (from Layer 4 of previous session, if available)
  No consistent VOT patterns
  No word-boundary acoustic structure
  -> Pre-linguistic pipeline

MODE_TRANSITION:
  CBR 0.80-1.0
  Some VOT patterns present
  Occasional word-like units detected
  -> Hybrid pipeline (pre-linguistic + word detection)

MODE_LINGUISTIC:
  Consistent consonant-vowel structure
  Sentence-level F0 contours present
  Word-boundary patterns consistent
  Utterance length > 2 units consistently
  -> Linguistic pipeline

NOTE: DMD uses a Hidden Markov Model over last 10 sessions to prevent spurious mode switching.
Mode transitions require evidence across multiple sessions, not just one unusual session.
```

**Output Schema:**
```json
{
  "speaker_identity": {
    "verification_score": 0.87,
    "identity_status": "CONFIRMED | UNCERTAIN | UNMATCHED",
    "developmental_stage": "OLDER_INFANT",
    "developmental_mode": "MODE_PRELINGUISTIC | MODE_TRANSITION | MODE_LINGUISTIC",
    "enrolled_session_count": 34,
    "diarization": {
      "speakers_detected": 2,
      "infant_segments": [{"start": 0.0, "end": 12.4}, {"start": 15.1, "end": 31.7}],
      "adult_segments": [{"start": 12.4, "end": 15.1}]
    }
  }
}
```

---

### Layer 3: Contextual Data Collection

**Purpose:** Assemble the context bundle that makes acoustic interpretation situationally valid.

**Data Sources and Collection:**

*Automatic (no parent action required):*
```
time_of_day: device clock -> ISO8601 timestamp
  circadian_category: NIGHT(0-5h) | DAWN(5-8h) | MORNING(8-12h) | AFTERNOON(12-17h) | EVENING(17-21h) | NIGHT(21-24h)
  hunger_probability_from_time: lookup table based on typical infant feeding cycles

temperature_celsius: weather API (OpenMeteo, by device geolocation, non-precise)
humidity_percent: same API call
weather_condition: clear | cloudy | rain | snow (affects outdoor recording probability)

session_history:
  time_since_last_session: minutes since previous recording
  sessions_today: count of recordings in past 24 hours

audio_derived_context:
  lombard_flag: from Layer 0
  room_acoustics_RT60: reverb time estimate (indoor vs outdoor indicator)
  background_sound_type: classifier -> quiet | TV | voices | traffic | music
  background_noise_level_db: from Layer 0 SNR analysis
```

*Parent questionnaire (max 3 taps, pre-session):*
```
REQUIRED (one tap):
  feeding_time: UNDER_1H | 1_TO_2H | 2_TO_4H | OVER_4H

OPTIONAL (one tap each):
  sleep_state_before: JUST_WOKE | ACTIVE | DROWSY | UNKNOWN
  health_state: WELL | MILD_COLD | FEVER | EAR_ISSUE | OTHER
  environment: HOME_QUIET | HOME_NOISY | CAR | OUTSIDE
  who_present: PARENT_ONLY | BOTH_PARENTS | SIBLINGS | OTHERS
```

**Output Schema:**
```json
{
  "context_bundle": {
    "timestamp": "2024-10-14T11:32:00Z",
    "circadian_category": "MORNING",
    "feeding_time": "2_TO_4H",
    "sleep_state_before": "ACTIVE",
    "health_state": "WELL",
    "environment": "HOME_QUIET",
    "who_present": "PARENT_ONLY",
    "temperature_celsius": 19.5,
    "humidity_percent": 58,
    "background_noise_level_db": 42,
    "background_sound_type": "quiet",
    "lombard_correction_required": false,
    "time_since_last_session_minutes": 94,
    "sessions_today": 2,
    "context_coherence_score": 0.84
  }
}
```

---

### Layer 4: Rich Feature Extraction

**Purpose:** Extract the full 50–80 dimensional acoustic feature vector from infant-only audio segments.

**Input:** Infant-only segments (from Layer 2 diarization), Lombard correction parameters (Layer 0), temperature-corrected c (Layer 0).

**Feature Groups:**

#### 4.1 Temporal Features (7 features)
```
f1:  RMS_energy_envelope = [rms_per_10ms_frame]  (used as time series; scalar summary: mean, std)
f2:  zero_crossing_rate = sum(|sign(x_n) - sign(x_{n-1})|) / 2N  (per frame, summarized)
f3:  onset_strength = first_order_diff(spectral_flux)  (summary: mean, peak)
f4:  silence_ratio = silence_frames / total_frames
f5:  vocalization_bout_lengths = [duration of each continuous voiced segment]  (mean, std, max)
f6:  burst_frequency = onset_events_per_second
f7:  envelope_shape = [ADSR parameters fitted to RMS envelope]
     (attack_time_ms, decay_time_ms, sustain_level, release_time_ms)
```

#### 4.2 Spectral Features (7 features)
```
f8:  spectral_centroid = sum(f * M(f)) / sum(M(f))
f9:  spectral_bandwidth = sqrt(sum((f-centroid)^2 * M(f)) / sum(M(f)))
f10: spectral_rolloff = frequency below which 85% of spectral energy falls
f11: spectral_flux = sum((M_t(f) - M_{t-1}(f))^2)  per frame
f12: spectral_flatness = geometric_mean(M(f)) / arithmetic_mean(M(f))
f13: spectral_contrast = [peak - valley per sub-band for N=7 sub-bands]
f14: harmonic_ratio = harmonic_energy / total_energy
```

#### 4.3 Cepstral and Formant Features (8 features)
```
f15-27: MFCCs 1-13 = mel_filterbank -> log -> DCT  (26 coefficients standard)
        delta_MFCCs = first_order_diff(MFCCs)  (additional 13)
        delta_delta_MFCCs = second_order_diff(MFCCs)  (additional 13)
        [In practice: 13 MFCCs + 13 delta + 13 delta-delta = 39D cepstral block]

f28: LPC_coefficients (order 12-16) = linear prediction coefficients

Formant features (from LPC peak-picking or parselmouth):
f29: F1_hz, F1_bandwidth
f30: F2_hz, F2_bandwidth
f31: F3_hz, F3_bandwidth
f32: F4_hz, F4_bandwidth
f33: F2_slope = rate_of_F2_change_per_frame  (consonant transition indicator)
f34: formant_ratio_F1_F2 = F1 / F2  (tongue height/backness indicator)
```

#### 4.4 Pitch and Prosodic Features (8 features)
```
F0 estimation: YIN (primary) + CREPE (neural, for difficult signals)

f35: F0_mean_hz
f36: F0_std_hz
f37: F0_range_hz = F0_max - F0_min
f38: F0_trajectory = [F0 contour time series, resampled to 50 points for fixed-length rep]
f39: F0_contour_class = RISING | FALLING | RISE_FALL | FLAT | COMPLEX
     (classified by slope analysis of F0 trajectory)
f40: jitter_percent = mean(|T_n - T_{n-1}|) / mean(T_n) * 100
f41: shimmer_percent = mean(|A_n - A_{n-1}|) / mean(A_n) * 100
f42: vibrato_rate_hz = modulation frequency of F0 in 4-8 Hz range
```

#### 4.5 Voice Quality Features (5 features)
```
f43: HNR_db = 10 * log10(E_harmonic / E_noise)
     (harmonics-to-noise ratio: voice clarity, breathiness indicator)
f44: breathiness_index = H1_amplitude - H2_amplitude  (spectral tilt proxy)
f45: creakiness = binary flag: F0 < 70Hz AND irregular pulse spacing
f46: VOT_ms = time from consonant release to voicing onset
     (Voice Onset Time — relevant in Stage B/C; near-zero in Stage A)
f47: strain_index = 0.33*jitter + 0.33*shimmer + 0.33*high_freq_energy_ratio
```

#### 4.6 Developmental Features (5 features)
```
f48: phonation_type = VEGETATIVE | QUASI_RESONANT | FULLY_RESONANT | CANONICAL
     (rule-based: F0 presence + HNR + formant completeness)

f49: canonical_babbling_ratio (CBR):
     syllable_detection:
       - onset detection (energy-based)
       - closure duration check (100-500ms per syllable)
       - vowel nucleus detection (fully resonant: F1>300Hz, F2>700Hz, HNR>10dB)
       - consonant check: F2 transition > threshold
     CBR = canonical_syllables / total_syllables

f50: syllable_structure = [V, CV, CVC, CVCV, complex] distribution per session

f51: intonation_contour_class = cluster label from F0 trajectory clustering
     (classes learned from population data, not hand-coded)

f52: sound_type = CRY | LAUGH | BABBLE | COUGH | VEGETATIVE | MIXED
     (CNN classifier trained on labeled infant vocalizations)
```

#### 4.7 Nonlinear Dynamics Features (4 features)
```
(Applied only to CRY-type sessions where sound_type=CRY)

f53: lyapunov_exponent_1 = lambda_1 from phase space reconstruction
     (Rosenstein algorithm: embed dimension m=6, delay tau=first_MI_minimum)
     HIGH lambda_1 > 0.30: pain cry indicator
     LOW lambda_1 0.0-0.15: normal cry

f54: bifurcation_indicator = binary: sudden qualitative regime change detected
     (method: sliding window variance in embedding — sudden increase = bifurcation)

f55: recurrence_rate = density of recurrence plot (percentage of recurrent points)
     HIGH recurrence: regular, repetitive cry
     LOW recurrence: complex, irregular cry (distress indicator)

f56: determinism_RQA = DET from recurrence quantification analysis
     (proportion of recurrent points forming diagonal lines)
```

#### 4.8 Optional: Deep Embedding Features (transfer learning)

```
Transfer learning from wav2vec 2.0 (Baevski et al., 2020) or HuBERT (Hsu et al., 2021):

INPUT: raw waveform segments (16kHz mono)
MODEL: wav2vec2-base or HuBERT-base (fine-tuned on infant vocalization data when available)
OUTPUT: 768-dimensional contextualized embedding

Usage:
  - As supplementary feature alongside classical features (not replacement)
  - Particularly valuable for discriminating fine-grained acoustic patterns
  - Fine-tuning on accumulated Qleam infant data is a Phase 3 enhancement

Contrastive learning approach (SimCLR-style):
  Train encoder to produce similar embeddings for sessions with same intent label
  and dissimilar embeddings for sessions with different intent labels
  Results in richer acoustic representation than supervised classification alone
```

**Output Schema:**
```json
{
  "feature_vector": {
    "temporal": { "rms_mean": 0.23, "rms_std": 0.08, "zcr_mean": 0.12, ... },
    "spectral": { "centroid_hz": 1840, "bandwidth_hz": 920, "rolloff_hz": 3200, ... },
    "mfcc": [2.1, -0.8, 1.4, ...],  // 39D vector
    "formants": { "F1": 780, "F2": 2100, "F3": 3400, "F4": 4600 },
    "pitch": { "F0_mean": 380, "F0_std": 45, "jitter": 2.8, "shimmer": 3.4 },
    "voice_quality": { "HNR_db": 12.4, "breathiness": 6.2, "creaky": false },
    "developmental": { "phonation_type": "FULLY_RESONANT", "CBR": 0.61, "sound_type": "BABBLE" },
    "nonlinear": { "lyapunov_1": 0.14, "bifurcation": false, "recurrence_rate": 0.42 },
    "deep_embedding_768d": null,  // populated if wav2vec2 active
    "feature_vector_dimensionality": 56,
    "acoustic_confidence": 0.79
  }
}
```

---

### Layer 5: Per-Session Insight (Three-Source Evidence Model)

**Purpose:** Produce the session-level intent inference combining all three evidence sources.

**Step 1 — Acoustic-Only Score (computed first, before any feedback):**
```
P_acoustic(intent | features, context) ∝
    P(features | intent)          [acoustic likelihood from feature vector classifier]
  × P(intent | context)           [contextual prior: feeding time, time of day, health]
  × P(intent | stage)             [developmental stage prior]

Classifier: Gaussian Mixture Model (GMM) per intent category, or
            SVM with RBF kernel over feature vector, or
            Neural network (MLP) trained on population model data

acoustic_confidence = max(P_acoustic)
signal_threshold:
  STRONG   if acoustic_confidence > 0.70
  AMBIGUOUS if 0.40-0.70
  WEAK     if < 0.40

Expected Feedback Profile (EFP) computed at this step (before parent interaction):
  expected_response_type = most_probable_response given dominant_intent
  expected_helpfulness = historical probability that expected response resolves intent
  stored internally, never shown to parent
```

**Step 2 — Research Prior Score:**
```
P_research(intent | features) =
    research_literature_prior (Wolff 1969 / dimensional model) * research_weight
  + population_model_prior (from FIVL aggregation) * population_weight

As system matures:
  research_weight decreases from 0.25 to 0.10 floor
  population_weight increases from 0 to 0.15 ceiling
  (research floor NEVER drops to zero)
```

**Step 3 — Parent Feedback Trust System:**
```
After parent provides feedback:

RESPONSE MATCH SCORE (RMS):
  actual_response == expected_response_type    -> RMS = 1.0
  actual_response == plausible_alternative     -> RMS = 0.6
  actual_response == unrelated                 -> RMS = 0.2
  actual_response == direct_contradiction      -> RMS = 0.0

EFFECTIVENESS PLAUSIBILITY SCORE (EPS):
  When signal = STRONG:
    helpful + matches expected    -> EPS = 1.0
    helpful + contradicts         -> EPS = 0.2  (suspicious)
    ineffective + every session   -> EPS = 0.0  (adversarial pattern)
  When signal = AMBIGUOUS or WEAK:
    EPS = 0.5 always (cannot penalize uncertain signal)

FEEDBACK ALIGNMENT SCORE (FAS) = 0.60 * RMS + 0.40 * EPS
DELTA SCORE (DS) = FAS

TRUST SCORE (FRS) — Feedback Reliability Score:
  Initial: 0.50
  FRS(t) = EMA(session_reliability_score(t), alpha)
  alpha = 0.15 normal | 0.45 adversarial | 0.10 recovery | 0.0 misclick

Parent type classification after N sessions:
  RELIABLE:    mean(DS) > 0.70, variance low
  CONFUSED:    mean(DS) ≈ 0.50, high variance
  LAZY:        near-zero variance, same answer always
  UNINFORMED:  mean(DS) < 0.40, moderate variance
  ADVERSARIAL: mean(DS) < 0.15 on STRONG signals, very low variance
```

**Step 4 — Final Combined Intent Score:**
```
effective_feedback_weight = w_feedback * FRS * DS

freed = w_feedback - effective_feedback_weight
acoustic_adjusted = w_acoustic + (freed * 0.80)
research_adjusted = w_research + (freed * 0.20)

P_final(intent) =
    acoustic_adjusted  * P_acoustic(intent)
  + research_adjusted  * P_research(intent)
  + effective_feedback_weight * P_feedback(intent)

confidence = acoustic_signal_strength
           * context_adjustment_factor
           * session_calibration_factor   [min(sessions/20, 1.0)]
           * cluster_maturity_factor      [min(cluster_freq/10, 1.0)]
           * semantic_factor              [word-pattern bonus]
           * source_agreement_factor      [1.0/0.75/0.45 per agreement level]
           * trust_credibility_factor     [0.60 + FRS*0.40]

CAPS: confidence CAPPED at 0.40 for first 5 sessions
      confidence CAPPED at 0.92 always (never claim certainty)
      confidence CAPPED at 0.35 for WEAK acoustic signal
```

**Insight Quality Score:**
```json
{
  "insight_quality_score": 0.89,
  "data_quality_flag": "HIGH | MEDIUM | LOW | ACOUSTIC_ONLY | INSUFFICIENT",
  "population_model_eligible": true,
  "parent_type_classification": "RELIABLE",
  "reliability_flags": []
}
```

---

### Layer 6: Dyadic Interaction Analysis

**Input:** Diarized segments (infant + adult labels from Layer 2), feature vectors for all speaker segments.

**Processing:**
```
TURN-TAKING ANALYSIS:
  infant_turn_end = end of infant vocalization segment
  adult_response_onset = beginning of next adult vocalization segment
  response_latency_ms = adult_response_onset - infant_turn_end

  Typical contingent response: < 2000ms
  Delayed: 2000-5000ms
  Absent: > 5000ms or adult vocalization before infant finishes (overlap)

CONTINGENT RESPONSIVENESS:
  After adult response, does infant vocalization change?
  acoustic_change = cosine_distance(infant_pre_response_features, infant_post_response_features)
  HIGH change: infant is responsive to caregiver (positive dyadic signal)
  LOW change: infant is not acoustically responsive

ACOUSTIC IMITATION TRACKING:
  Does infant F0 trajectory approximate adult F0 trajectory within the same exchange?
  F0_convergence = 1 - normalized_distance(infant_F0_contour, adult_F0_contour_scaled)
  Track over sessions: increasing convergence = imitation learning progressing

PARENTESE/MOTHERESE DETECTION:
  Adult F0 when speaking to infant vs. background baseline:
  parentese_indicators:
    F0_mean elevated > 20% above adult's normal baseline
    F0_range expanded > 1.5x normal
    slower_speaking_rate (duration per syllable increased > 30%)
    simpler_vocabulary (type-token ratio reduced)
  parentese_score = weighted composite of above indicators
```

**Output Schema:**
```json
{
  "dyadic_analysis": {
    "mean_response_latency_ms": 1240,
    "contingent_responsiveness_score": 0.72,
    "acoustic_convergence_score": 0.41,
    "parentese_detected": true,
    "parentese_score": 0.83,
    "dyadic_synchrony_index": 0.68,
    "interaction_quality_label": "HIGH | MODERATE | LOW | ABSENT"
  }
}
```

---

### Layer 7: Longitudinal Developmental Tracking

**Input:** Feature vector from Layer 4 + developmental stage from Layer 2 + session history (DynamoDB lookup).

**Processing:**

*Stage-Aware Adaptive EMA Baseline:*
```
alpha(t) = alpha_base + alpha_stage_modifier

alpha_base = 0.30
alpha_stage_modifier:
  same_stage_as_previous: 0.0
  stage_transition_detected: +0.50  (reset toward current — old baseline less relevant)
  regression_detected: -0.10        (slow down — may be temporary)

Stage transition detection:
  CBR changes > 0.15 between rolling 5-session windows
  OR syllable_structure_complexity jumps a tier
  OR F0_mean drops > 30Hz across 3 consecutive sessions (vocal tract growth)

new_baseline = alpha * current_features + (1-alpha) * previous_baseline
deviation_score = mahalanobis_distance(current_features, baseline, covariance_matrix)
```

*VTL Growth Curve:*
```
Per session: VTL_cm from Layer 1
Fit: VTL(age_months) = a * log(b * age_months + 1) + c
     (logarithmic growth model, parameters fit from population data)
Store VTL per session with session date -> growth curve per baby
Compare to population norms at each stage
```

*CBR Trend Analysis:*
```
Rolling 5-session mean CBR
CBR_velocity = (CBR_current_window - CBR_previous_window) / sessions_elapsed
Developmental norms:
  CBR < 0.15 before 10 months: NORMAL (pre-canonical)
  CBR < 0.15 after 10 months: DEVELOPMENTAL_FLAG (delayed canonical babbling)
  CBR 0.15-0.50: EMERGING_CANONICAL
  CBR > 0.50: CANONICAL_ESTABLISHED
```

*Milestone Logging:*
```
Milestones tracked with first-occurrence date:
  FIRST_FULLY_RESONANT_VOWEL
  FIRST_CANONICAL_BABBLE (CBR first crosses 0.20)
  FIRST_PROTO_WORD_CANDIDATE
  FIRST_CONFIRMED_PROTO_WORD
  CONCEPT_GRAPH_50_NODES
  CONCEPT_GRAPH_100_NODES
  FIRST_WORD_COMBINATION
  LINGUISTIC_MODE_TRANSITION
  FIRST_COMPLETE_SENTENCE
```

---

### Layer 8: Private Language Extraction

**Input:** All previous layer outputs + Personal Concept Graph (DynamoDB) + session history.

**Stream Decoder:**
```
STEP 1: Stream segmentation
  Continuous audio segmented into acoustic cluster sequences
  Cluster boundaries = significant feature vector discontinuities
  Per segment: assign to nearest existing cluster (cosine similarity)
  New segment type: create candidate cluster, flag for parent input

STEP 2: Concept graph lookup per cluster
  For each cluster c in session stream:
    PCG lookup: concept_nodes where acoustic_clusters contains c
    Sort by: confidence * context_match_score
    Return: top 3 matching concepts with confidence

STEP 3: Context integration
  P(concept_k | cluster_c, context) ∝
    P(cluster_c | concept_k) * P(context | concept_k) * P(concept_k | stage, PCG)

STEP 4: Sequence inference
  For stream [c1, c2, c3, ...]:
    Infer most probable concept sequence
    Handle: repetition (meh meh = emphasizing, not two separate concepts)
    Handle: combination (wawa + reaching_kitchen = want water)

STEP 5: Proto-word crystallization check
  For each cluster, evaluate all 5 crystallization criteria:
    1. Stable across >= N_min sessions
    2. Feature variance < threshold
    3. Context co-occurrence >= 0.70
    4. Response effectiveness >= 0.65
    5. Parent word confirmation >= 1
  If all criteria met: promote to PROTO_WORD_CANDIDATE
  If confidence >= 0.85: promote to ESTABLISHED_SIGNAL
```

**φ Order Parameter:**
```
phi(t) = 0.30 * CBR(t)
       + 0.25 * proto_word_cluster_stability(t)
       + 0.20 * F2_slope_diversity(t)
       + 0.15 * cross_situational_consistency(t)
       + 0.10 * parent_word_confirmation_rate(t)

All components normalized to [0, 1] range

phi_velocity = d(phi)/dt over rolling 4-week window
PHASE_TRANSITION_INDICATOR if phi_velocity > threshold
```

---

### Layer 9: Parent Interface and Progressive Disclosure

**Output JSON structure for mobile rendering:**

```json
{
  "session_view": {
    "validation_status": "CONFIRMED: Your baby's voice",
    "confidence": 0.74,
    "confidence_context": "Session 23 — model is well-calibrated",
    "intent_primary": {
      "label": "wanting food or drink",
      "arousal": 0.72,
      "valence": -0.31,
      "probability": 0.74
    },
    "intent_alternatives": [
      { "label": "general discomfort", "probability": 0.18 },
      { "label": "attention seeking", "probability": 0.08 }
    ],
    "what_we_heard": "Clear, rhythmic vocalization with rising pitch",
    "context_acknowledgment": "3 hours since last feeding — this is consistent",
    "health_flag": null,
    "source_agreement": "HIGH",
    "suggested_response": "Offer feeding or drink",
    "established_signal_used": "wawa-sound (confirmed 31 times)",
    "feedback_form_type": "PERSONAL_GRAPH_OPTIONS"
  },
  "developmental_view": {
    "current_stage": "OLDER_INFANT",
    "stage_description": "Building personal vocabulary of sounds",
    "cbr": 0.61,
    "cbr_trend": "RISING",
    "concept_graph_size": 94,
    "phi_indicator": "Language signals forming",
    "milestones_this_week": []
  }
}
```

---

## 4. Component Correlation Map

The following directed dependency graph shows which components feed into which other components. An arrow A -> B means A must complete before B can run.

```
COMPONENT DEPENDENCY GRAPH
============================================================

[Audio Input]
    |
    v
[L0: Audio Quality]
    |
    +-----> [L1: Biological Validation]
    |               |
    |               +-----> [L2: Speaker Identity]
    |               |               |
    |               |               +-----> [L3: Context Collection]
    |               |               |               |
    |               |               |               +-----> [L4: Feature Extraction]
    |               |               |               |               |
    |               |               |               |               +-----> [L5: Insight / TSE]
    |               |               |               |               |               |
    |               |               |               |               |               +-----> [L9: Parent UI]
    |               |               |               |               |
    |               |               |               |               +-----> [L6: Dyadic Analysis]
    |               |               |               |               |               |
    |               |               |               |               |               +-----> [L9]
    |               |               |               |               |
    |               |               |               |               +-----> [L7: Dev. Tracking]
    |               |               |               |               |               |
    |               |               |               |               |               +-----> [L8: Private Lang]
    |               |               |               |               |                               |
    |               |               |               |               |                               +-----> [L9]
    |               |               |               |               |
    |               |               |               |               +-----> [FIVL: Population Model]
    |               |               |                                           |
    |               |               |                                           +-----> [L5 research prior update]
    |               |               |
    |               |               +-----> [Developmental Mode Detection]
    |               |                               |
    |               |                               +-----> [routes: Stage A | B | C pipeline]
    |               |
    |               +-----> [VTL estimation -> feeds L2 and L7 VTL growth curve]
    |
    +-----> [Lombard correction -> feeds L4 feature extraction]
    +-----> [c_corrected -> feeds L1 VTL]

CROSS-SESSION DEPENDENCIES:
  [Session N features] -> [Session N+1 baseline computation]  (L7 EMA)
  [Session N cluster assignments] -> [Session N+1 proto-word tracking]  (L8)
  [Session N trust score] -> [Session N+1 feedback weight]  (L5 TSE)
  [Session N VTL] -> [VTL growth curve update]  (L7)

EXTERNAL FEED-INS:
  [Old Research Dataset] -------> [L5 research prior] (permanent, floor 0.10)
  [Population Model (FIVL)] ----> [L5 research prior supplement]
  [Personal Concept Graph] -----> [L8 stream decoder]
  [Weather API] ----------------> [L3 context bundle]
  [Parent Feedback] ------------> [L5 TSE after session completes]
```

---

## 5. Dataset Ecosystem Architecture

Four distinct data stores form the backbone of the system's intelligence. Each has a different nature, lifecycle, and privacy model.

### 5.1 Dataset 1: Old Research Dataset (Static Prior Base)

**Nature:** Fixed, read-only, never modified at runtime. Encodes population-level knowledge from the developmental psychology literature (Wolff 1969, Wasz-Hockert 1968, dimensional model, modern developmental research).

**Content:**
```
- Prior probability distributions: P(intent | acoustic_category)
- Acoustic templates for: cry types, babbling stages, pre-linguistic vocalizations
- Developmental stage acoustic norms
- CBR developmental norms
- VTL-age growth tables
- Research literature acoustic correlates
```

**Access pattern:** Read-only at system initialization and when computing research prior component of TSE. Never written to.

**Storage:** AWS S3 (JSON/Parquet files), loaded into Lambda memory at cold start. Size: ~500MB.

**Privacy:** No personal data. No individual audio. Population statistics only.

### 5.2 Dataset 2: Living Population Dataset (Federated, Growing)

**Nature:** Continuously updated aggregate statistics from all babies using the system, constructed via federated learning. No raw audio, no individual identifiable data.

**Content:**
```
- Model weights from FIVL aggregation (federated average of local model weights)
- Session quality distribution metrics per developmental stage
- Acoustic cluster frequency distributions per stage
- CBR distribution at each age (real data, not literature values)
- Context-intent correlation matrices
- Stage transition timing distributions
- Parent confirmation rates per intent category
```

**Update frequency:** Nightly aggregation job when > 100 new quality sessions contributed.

**Storage:** AWS S3 (model weights) + DynamoDB (statistical summaries). Size: grows with user base, ~10GB at maturity.

**Privacy:** Differential privacy (ε ≤ 1.0, δ ≤ 10^-5) applied to all gradient contributions before aggregation. No individual session data stored at population level.

### 5.3 Dataset 3: Individual Baby Model (Personalized)

**Nature:** The core personalization layer. One record per enrolled baby, growing with every session.

**Schema:**
```
baby_record {
  baby_id: str (non-guessable UUID)
  enrollment_date: ISO8601
  session_history: [session_record]  // see below
  acoustic_clusters: [cluster_record]  // per-cluster statistics
  embedding_history: [embedding, timestamp]  // for verification
  vtl_growth_curve: [(session_id, vtl_cm, age_days)]
  developmental_stage_history: [(stage, date)]
  cbr_trend: [float]  // per session
  baseline_vector: float[]  // current EMA baseline
  baseline_covariance: float[][]  // for Mahalanobis deviation
  trust_score: float  // FRS - current trust
  trust_history: [(session_id, delta_score, trust_at_session)]
  parent_type_classification: str
  reliability_flags: [str]
  milestone_log: [(milestone_id, date, session_id)]
}

session_record {
  session_id: str
  timestamp: ISO8601
  pipeline_outputs: {L0 through L9 outputs}
  feature_vector: float[56]
  intent_distribution: {intent: probability}
  final_confidence: float
  context_bundle: {...}
  feedback_raw: {...}
  delta_score: float
  insight_quality_score: float
  data_quality_flag: str
  population_model_eligible: bool
}
```

**Storage:** AWS DynamoDB (per-baby tables with partition key = baby_id). Audio features stored in DynamoDB; raw audio in S3 with configurable retention (default: 30-day deletion after feature extraction).

**Access:** Single-baby access only. No cross-baby queries from this dataset.

### 5.4 Dataset 4: Private Language Model (Per-Baby Concept Graph)

**Nature:** The Personal Concept Graph — the baby's known world, linked to their acoustic patterns. The most individualized dataset in the system.

**Schema:**
```
concept_node {
  concept_id: str
  label: str  // human-readable
  category: str  // physiological | social | object | person | place | routine | activity
  layer: str  // universal | personal | developmental
  first_appeared_date: ISO8601
  first_appeared_session_id: str
  acoustic_clusters: [str]  // cluster IDs linked to this concept
  context_signatures: [str]  // context patterns associated
  confidence: float  // 0.0 to 1.0
  confirmation_count: int
  last_confirmed_session_id: str
  parent_descriptions: [str]  // raw text fragments that introduced this concept
  crystallization_status: str  // UNCONFIRMED | CANDIDATE | PROTO_WORD | ESTABLISHED
}

concept_graph {
  baby_id: str
  created_date: ISO8601
  total_concepts: int
  universal_layer: [concept_node]
  personal_layer: [concept_node]
  edges: [(concept_id_a, edge_type, concept_id_b, weight)]
  proto_word_candidates: [concept_id]
  established_signals: [concept_id]
  phi_order_parameter_history: [(date, phi_value)]
}
```

**Storage:** AWS DynamoDB (adjacency list pattern) or AWS Neptune (property graph) for richer graph queries. DynamoDB is preferred at scale for cost; Neptune for research analysis.

**Data flows between datasets:**

```
OLD RESEARCH DATASET (static)
    |
    | (read, permanent floor contribution)
    v
POPULATION MODEL (living aggregate)
    |
    | (updated via FIVL, provides improved population prior)
    v
INDIVIDUAL BABY MODEL (personalized)
    |
    | (per-baby features, context, confirmed intents)
    v
PRIVATE LANGUAGE MODEL (concept graph)
    ^
    |
    | (parent free text -> NLP -> new concept nodes)
    | (acoustic clusters -> concept graph updates)
    | (temporal outcome consistency -> retrospective updates)
```

---

## 6. Cold Start Solution

The cold start problem: on Day 1, the system has zero individual data. How does it provide useful, honest output?

### 6.1 Hierarchical Bayesian Prior Construction (CSHP)

```
Level 1: Universal Acoustic Prior (applies to ALL infants, all time)
  Source: developmental biology literature
  Content: P(intent | sound_type, age_group)
    - Newborn cry -> P(discomfort) = 0.70, P(hunger) = 0.20, P(unknown) = 0.10
    - High-pitched sustained cry -> P(pain) elevated
    - Low-energy whimper -> P(fatigue) elevated
  This prior is never wrong in the sense that it represents evolutionary biology
  Weight in cold start: alpha_U = 0.30

Level 2: Population Stage Prior (from living population dataset)
  Source: aggregate statistics from babies at same developmental stage
  Content: P(intent | acoustic_features, developmental_stage)
    - Filled in from FIVL population model as it matures
    - Initially identical to Old Research Dataset
    - Transitions to data-driven as user base grows
  Weight in cold start: alpha_S = 0.35

Level 3: Contextual Prior (from current session context)
  Source: current session context_bundle
  Content: P(intent | time_of_day, feeding_time, health_state, sleep_state)
    - feeding_time > 4h: P(hunger) elevated by factor 2.5
    - time = NIGHT + brief waking: P(fatigue) elevated
    - health_state = fever: P(discomfort) elevated
  This is information about THIS specific session — not about the baby in general
  Weight in cold start: alpha_C = 0.25

Level 4: Developmental Norms Prior
  Source: literature developmental trajectories (Oller CBR norms, etc.)
  Content: P(stage | age_days) — what stage should a baby this age be at?
  Constrains interpretation appropriately: a 2-month-old cannot have proto-words
  Weight in cold start: alpha_N = 0.10
```

### 6.2 Confidence Growth Session by Session

```
Session 0 (Day 1, no data):
  P_prior = CSHP (all four levels)
  session_calibration_factor = 0.05
  confidence CAPPED at 0.25
  Parent-facing: "Day 1 — We're learning your baby's patterns. This is our best
                  estimate based on developmental research."

Sessions 1-5:
  P_posterior = (1 - lambda_n) * P_prior + lambda_n * P_individual
  lambda_n = 1 - exp(-n/tau), tau = 10 sessions (characteristic learning timescale)
  session_calibration_factor = n/20 (increases from 0.05 to 0.25)
  confidence CAPPED at 0.40

Sessions 6-20:
  Individual data dominates increasingly
  lambda_n approaching 0.60-0.85
  session_calibration_factor increases to 1.0
  confidence cap removes at session 20

Sessions 20+:
  Individual model fully active
  CSHP prior contributes only through research floor (0.10 of w_research)
  Full confidence range available (0.10 to 0.92)

Information gain per session:
  IG(n) = KL(P_posterior(n) || P_prior)
  Expected: rapid gain in sessions 1-10, diminishing returns after 30
```

### 6.3 Parent Messaging During Cold Start

```
Session 1-3:   "Still learning your baby's unique patterns.
                These early insights are based on developmental research,
                not yet on your specific baby."

Session 4-10:  "Our understanding of your baby is growing.
                Your feedback is helping us calibrate."

Session 11-20: "We now have a good sense of your baby's patterns.
                Confidence in our insights is increasing."

Session 20+:   Standard confidence display. No cold-start message.
```

---

## 7. Concept Graph Technical Design

### 7.1 Schema and Storage (DynamoDB)

```
Table: qleam_concept_graph
Primary Key: baby_id (partition key) + concept_id (sort key)

NODE record:
{
  "PK": "BABY#abc123",
  "SK": "CONCEPT#purple_bunny",
  "type": "CONCEPT_NODE",
  "label": "Purple bunny toy",
  "category": "object/toy",
  "layer": "personal",
  "first_appeared": "2024-06-15",
  "first_session": "sess_xyz",
  "acoustic_clusters": ["cluster_F", "cluster_K"],
  "context_signatures": ["toy_shelf_visible", "morning_play"],
  "confidence": 0.82,
  "confirmation_count": 34,
  "last_confirmed": "sess_abc789",
  "parent_descriptions": ["purple bunny", "her bunny", "soft toy"],
  "crystallization_status": "ESTABLISHED",
  "crystallization_date": "2024-08-01",
  "GSI1PK": "BABY#abc123#ESTABLISHED"  // GSI for querying by status
}

EDGE record:
{
  "PK": "BABY#abc123",
  "SK": "EDGE#purple_bunny#morning_play",
  "type": "CONTEXT_ASSOCIATION",
  "from_concept": "purple_bunny",
  "to_context": "morning_play",
  "co_occurrence_count": 18,
  "confidence": 0.71
}

CLUSTER_LINK record:
{
  "PK": "BABY#abc123",
  "SK": "CLUSTER#cluster_F",
  "type": "ACOUSTIC_CLUSTER",
  "linked_concepts": ["purple_bunny", "toy_request"],
  "primary_concept": "purple_bunny",
  "primary_concept_confidence": 0.82,
  "total_observations": 52,
  "first_observed": "2024-05-10"
}
```

### 7.2 Graph Operations

*Add Concept Node:*
```python
def add_concept_node(baby_id, label, category, layer, session_id, parent_text):
    concept_id = generate_concept_id(label, baby_id)
    node = {
        "PK": f"BABY#{baby_id}",
        "SK": f"CONCEPT#{concept_id}",
        "type": "CONCEPT_NODE",
        "label": label,
        "category": category,
        "layer": layer,
        "first_appeared": today(),
        "first_session": session_id,
        "acoustic_clusters": [],
        "confidence": 0.10,  // just appeared, unconfirmed
        "confirmation_count": 0,
        "crystallization_status": "UNCONFIRMED"
    }
    dynamodb.put_item(node)
    return concept_id
```

*Link Cluster to Concept:*
```python
def link_cluster_to_concept(baby_id, cluster_id, concept_id, context_match_score):
    # Retrieve cluster record; update linked_concepts list
    # Retrieve concept node; append cluster_id to acoustic_clusters if not present
    # Confidence increment:
    confidence_increment = 0.05 * context_match_score  // small per-observation increment
    new_confidence = min(current_confidence + confidence_increment, 1.0)
    dynamodb.update_item(concept_update)
    dynamodb.update_item(cluster_update)
```

*Update Concept Confidence (Bayesian update):*
```python
def update_concept_confidence(baby_id, concept_id, confirmed, parent_certainty=1.0):
    """
    confirmed: True if parent confirmed, False if disconfirmed
    parent_certainty: derived from NLP uncertainty language (0.5 for "I think", 1.0 for "definitely")
    """
    current = get_confidence(baby_id, concept_id)
    confirmation_count = get_count(baby_id, concept_id)

    // Beta-Binomial update (Beta(alpha, beta) posterior)
    alpha = confirmation_count * current + 1  // successes
    beta = confirmation_count * (1 - current) + 1  // failures

    if confirmed:
        alpha += parent_certainty
    else:
        beta += parent_certainty

    new_confidence = alpha / (alpha + beta)  // posterior mean
    check_crystallization_criteria(baby_id, concept_id)
```

### 7.3 NLP Pipeline for Free Text Extraction

```
Input: "she kept reaching for the new bunny toy I gave her"

Pipeline:
  Step 1: SpaCy NLP parse
    Entities: [bunny toy]
    Actions: [reaching, gave]
    Temporal markers: [new — first introduction]
    Uncertainty markers: none found -> certainty = 1.0

  Step 2: Intent extraction
    reaching = gesture -> intent: want/request
    new = first introduction flag

  Step 3: Concept resolution
    "bunny toy" -> concept lookup in PCG -> NOT FOUND
    -> create new concept node: id="bunny_toy", label="bunny toy", category="object/toy"
    -> link to current acoustic session's dominant cluster

  Step 4: Confidence assignment
    Certainty from NLP: 1.0 (no uncertainty markers)
    Initial confidence: 0.15 (new concept, unconfirmed)
    Link weight: 0.15 * 1.0 = 0.15

  Step 5: Context signature extraction
    "toy shelf visible" not mentioned; context_bundle says "HOME_QUIET"
    Add context signature: "reaching_gesture"

Uncertainty language detection examples:
  "I think" -> certainty = 0.70
  "maybe" -> certainty = 0.65
  "she said very clearly" -> certainty = 1.20 (bonus)
  "she definitely wanted" -> certainty = 1.15
  "not sure but possibly" -> certainty = 0.50
```

---

## 8. Stream Decoder Design

The stream decoder operates on continuous audio when the baby is producing a connected multi-cluster vocalization stream.

```
REAL-TIME SEGMENTATION:
  sliding window: 100ms hop, 500ms window
  segment boundary: cosine_distance(prev_embedding, curr_embedding) > 0.40
  minimum segment duration: 200ms
  maximum segment duration: 3000ms before forced split

PER-SEGMENT PROCESSING:
  1. Extract feature vector (abbreviated: MFCCs + F0 + formants only for speed)
  2. Assign to nearest cluster (cosine similarity, k-NN from cluster centroids)
  3. Concept graph lookup: P(concept | cluster, context)
  4. Accumulate: stream = [(cluster_id, concept_probs, timestamp)]

SEQUENCE INFERENCE:
  Given stream = [c1, c2, c3, c4]:

  Handle repetition: if c_i == c_{i-1} and gap < 500ms:
    merge: single emphasized instance, not two separate

  Handle combination: if P(combined_meaning | c_i, c_j) > threshold:
    infer compound intent (e.g., "want" + "water" = "want water")

  Context integration: multiply concept probabilities by context coherence
    P(final_concept | stream, context) normalized over personal concept space

  Output: ranked list of (concept_label, probability, evidence_count)

UNKNOWN CLUSTER HANDLING:
  New cluster with < 5 observations:
    confidence = 0.0 -> do not infer concept
    FLAG: "New sound detected at T=17.3s — what were they doing?"
    Prompt parent for free text description
    When parent responds -> NLP -> new concept candidate
```

---

## 9. Federated Learning Architecture (FIVL)

### 9.1 Federated Averaging with Quality Filtering

```
ELIGIBLE PARTICIPANT CRITERIA (per session):
  FRS > 0.60
  delta_score > 0.65
  reliability_flags = []
  data_quality_flag IN ["HIGH", "MEDIUM"]
  session_count > 5 (participant must have baseline)

GRADIENT COMPUTATION (per eligible session):
  local_model = baby's current personalized model weights
  local_loss = cross_entropy(predicted_intent, confirmed_intent)
  gradient_update = backprop(local_loss, local_model)

  DIFFERENTIAL PRIVACY NOISE ADDITION:
    sensitivity S = max norm of gradient (clipped at S=1.0)
    noise = Normal(0, sigma^2 * S^2 * I)
    noisy_gradient = gradient_update + noise
    privacy guarantee: (epsilon=1.0, delta=1e-5)-DP

  Send: noisy_gradient (NOT raw audio, NOT raw features, NOT individual labels)

CENTRAL AGGREGATION (FIVL server, nightly):
  eligible_sessions = filter(all_sessions, quality_criteria)

  Stage-stratified aggregation:
    For each developmental stage s in [NEWBORN, YOUNG_INFANT, OLDER_INFANT, TODDLER]:
      stage_sessions = filter(eligible_sessions, stage == s)
      w_stage = weighted_average(gradients, weights=n_sessions_per_baby)
      population_model[s] = population_model[s] - learning_rate * w_stage

  Broadcast: updated population_model to all clients (differential weights only)

CLIENT UPDATE:
  Download: population_model_update
  Personal model update:
    personal_weight = (1 - beta) * population_model + beta * personal_model
    beta = min(local_sessions / 30, 0.80)  // individual contribution increases with data
```

### 9.2 Privacy Guarantees

```
What leaves the device: noisy_gradient (vector of same dimension as model parameters)
What does NOT leave: raw audio, feature vectors, individual intent labels, session metadata

Reconstruction attack resistance:
  With ε=1.0, δ=1e-5 differential privacy:
  Probability that any individual session's data can be inferred from gradient: < δ + (e^ε - 1)
  = 1e-5 + (e - 1) ≈ 1.72
  -> Bounded privacy loss per session

  With composition over T sessions:
  Total privacy loss: ε_total = T * ε (naive) or O(sqrt(T) * ε) (moments accountant)
  -> User controls total privacy exposure via session count and consent
```

---

## 10. AWS Infrastructure

### 10.1 Core Services

```
COMPUTE:
  AWS Lambda (Python 3.11):
    - qleam-layer0-audio-quality  (512MB, 15s timeout)
    - qleam-layer1-bio-validation (1024MB, 30s timeout — formant extraction is heavy)
    - qleam-layer2-speaker-id     (512MB, 15s timeout)
    - qleam-layer3-context        (256MB, 5s timeout)
    - qleam-layer4-features       (2048MB, 60s timeout — librosa, parselmouth)
    - qleam-layer5-insight        (512MB, 15s timeout)
    - qleam-layer6-dyadic         (512MB, 15s timeout)
    - qleam-layer7-longitudinal   (256MB, 10s timeout)
    - qleam-layer8-privatelang    (512MB, 20s timeout)
    - qleam-layer9-output         (256MB, 5s timeout)
    - qleam-nlp-freetext          (1024MB, 30s timeout — spaCy / transformer NLP)
    - qleam-fivl-aggregator       (2048MB, 300s timeout — nightly, Step Functions)

ORCHESTRATION:
  AWS Step Functions (Standard Workflows):
    - Pipeline execution state machine
    - Error handling per layer (REJECT state, UNCERTAIN state, retry logic)
    - Parallel execution where possible (L6, L7 can run in parallel after L5)

STORAGE:
  AWS S3:
    - qleam-audio-raw (raw audio, 30-day lifecycle delete)
    - qleam-audio-processed (normalized audio, 7-day lifecycle)
    - qleam-population-model (FIVL model weights, versioned)
    - qleam-research-dataset (static prior data, lifecycle: permanent)

  AWS DynamoDB:
    - qleam-baby-records (baby profiles, session records)
    - qleam-concept-graphs (personal concept graphs, one record per node/edge)
    - qleam-population-stats (aggregated population statistics summaries)

LLM GENERATION:
  AWS Bedrock (Claude 3 Haiku):
    - Role: natural language output generation ONLY
    - Input: structured JSON from Layer 9
    - Output: parent-friendly text interpretation
    - NOT used for classification, NOT used for analysis decisions

ANALYTICS AND MONITORING:
  AWS CloudWatch: Lambda execution metrics, pipeline latency per layer
  AWS X-Ray: distributed tracing for full pipeline per session
  AWS Glue + Athena: population-level analysis queries on S3 data (research use)
```

### 10.2 Step Functions Pipeline Definition (Simplified)

```json
{
  "Comment": "Qleam Processing Pipeline",
  "StartAt": "Layer0_AudioQuality",
  "States": {
    "Layer0_AudioQuality": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:region:account:function:qleam-layer0-audio-quality",
      "Next": "CheckQualityGate"
    },
    "CheckQualityGate": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.quality_gate", "StringEquals": "PASS", "Next": "Layer1_BioValidation" }
      ],
      "Default": "RejectWithReason"
    },
    "Layer1_BioValidation": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:region:account:function:qleam-layer1-bio-validation",
      "Next": "CheckBioGate"
    },
    "CheckBioGate": {
      "Type": "Choice",
      "Choices": [
        { "Variable": "$.biological_gate", "StringEquals": "INFANT_CONFIRMED", "Next": "Layer2_SpeakerIdentity" },
        { "Variable": "$.biological_gate", "StringEquals": "UNCERTAIN", "Next": "Layer2_SpeakerIdentity" }
      ],
      "Default": "RejectWithReason"
    }
  }
}
```

### 10.3 Cost Model

```
Per session (typical 45-second recording):
  Lambda compute: ~$0.0003 (all layers combined)
  S3 storage (audio, 30-day): ~$0.0001
  DynamoDB: ~$0.0002 (read/write units)
  Bedrock (output generation): ~$0.0005 (Claude 3 Haiku per request)
  Weather API: ~$0.00001 (OpenMeteo, free tier sufficient early)
  Total per session: ~$0.0011

At scale (1M sessions/month): ~$1,100/month
At 100K active babies (avg 3 sessions/week): ~700K sessions/month -> ~$770/month
```

---

## 11. Missing Data Points and Identified Gaps from Audio Science Discussion

The following technical capabilities were identified as present in the academic audio science literature but not yet incorporated into the core pipeline description. Each is recommended for phased inclusion.

### 11.1 Transfer Learning from wav2vec 2.0 / HuBERT

**Gap:** Classical MFCC-based features, while well-characterized, discard information available in raw waveform representations. Self-supervised pre-trained models (wav2vec 2.0 — Baevski et al., 2020; HuBERT — Hsu et al., 2021) learn richer acoustic representations from large-scale unlabeled audio. These models produce contextualized embeddings that capture subtle acoustic patterns that MFCCs miss.

**Recommendation:** Phase 3 enhancement. Fine-tune wav2vec 2.0 (base model, 95M parameters) on accumulated Qleam infant audio data (targeting 50,000+ labeled sessions). Use 768-dimensional embeddings as supplementary feature block alongside classical features. Expected to improve proto-word discrimination and developmental stage classification.

**Implementation:** Hosted on AWS SageMaker, invoked from Layer 4 Lambda via SageMaker endpoint. Adds ~200ms latency per session (acceptable for non-real-time analysis path).

### 11.2 Bark Scale vs Mel Scale Consideration

**Gap:** Current feature extraction uses Mel scale filterbanks (standard in speech processing). The Bark scale (Zwicker & Terhardt, 1980) more accurately models human auditory critical band resolution, particularly at low frequencies where infant vocalizations are prominent.

**Technical detail:** Mel scale: 1 Mel = 1000 log(1 + f/700) / log(2); Bark scale: z = 13 arctan(0.76 f/1000) + 3.5 arctan(f/7500). The two scales diverge below 500 Hz where Bark provides finer resolution — relevant for infant F0 (250–600 Hz range).

**Recommendation:** Implement both Mel and Bark filterbank MFCCs in Layer 4 and A/B test prediction accuracy. Likely to improve F0-related features for infants. Low implementation cost (replace filterbank in existing librosa pipeline).

### 11.3 Glottal Source Filtering

**Gap:** Current system estimates glottal source characteristics from spectral analysis but does not perform true glottal inverse filtering to separate glottal source from vocal tract filter. Complete source-filter separation would improve formant extraction accuracy in distressed cries (where glottal irregularity corrupts standard LPC-based formant estimation).

**Method:** Iterative Adaptive Inverse Filtering (IAIF — Alku, 1992) or Glottal Closure Instant detection (GCI-based methods). Separates the composite signal into glottal pulse train (source) and vocal tract transfer function (filter), enabling cleaner formant analysis.

**Recommendation:** Priority enhancement for Layer 1 (biological validation) and Layer 4 (formant features). Particularly important for pain cry analysis where standard LPC fails. Implement via parselmouth/Praat IAIF implementation.

### 11.4 Respiratory Pattern Extraction

**Gap:** Pre-phonatory and post-phonatory breath sounds contain clinically relevant information: respiratory rate, breath depth, wheeze or stridor indicators, and cough pattern analysis. These are currently not extracted.

**Method:** Identify breath-phase segments from energy envelope and spectral analysis. Extract: inhalation/exhalation ratio, respiratory rate (breaths per minute from energy cycles), wheeze detection (harmonic wheeze pattern in spectral envelope), and gasp detection (sudden high-energy non-voiced onset).

**Recommendation:** Phase 2 enhancement. Add to Layer 4 as respiratory feature block (5–8 features). Particularly valuable for health deviation flagging in Layer 5. Enables correlation with health_state parent input for model validation.

### 11.5 Contrastive Learning for Acoustic Embeddings

**Gap:** Current cluster-based acoustic indexing uses cosine similarity on MFCC embeddings, which were not trained to maximize intent-discriminative information. Contrastive learning (SimCLR — Chen et al., 2020; SupCon — Khosla et al., 2020) trains an encoder so that sessions with the same parent-confirmed intent produce similar embeddings and sessions with different intents produce dissimilar embeddings.

**Method:** Given a batch of sessions with confirmed intent labels, apply contrastive loss: $L = -\log \frac{\exp(z_i \cdot z_j / \tau)}{\sum_{k \neq i} \exp(z_i \cdot z_k / \tau)}$ where $z_i$ and $z_j$ are embeddings of sessions with the same intent label, and $\tau$ is temperature parameter.

**Recommendation:** Phase 3, after sufficient labeled data accumulates (targeting 10,000+ confirmed sessions per developmental stage). Expected to substantially improve cluster quality for proto-word detection. Can be trained on population data and deployed as a shared encoder across all individual models.

### 11.6 Graph Neural Networks for Concept Graph

**Gap:** Current concept graph traversal for concept inference uses simple lookup and co-occurrence statistics. Graph Neural Networks (GNNs — Kipf & Welling, 2017; message passing neural networks) can propagate information through the concept graph structure, enabling richer inferences: if "water" and "thirsty" are strongly linked concepts, and "water" is inferred from acoustics, GNN propagation would increase the confidence of hunger/thirst-related concepts.

**Method:** GraphSAGE or Graph Attention Network (GAT) operating over the Personal Concept Graph. Node features: concept embedding + confidence + confirmation count. Edge features: co-occurrence count + semantic relation type. Output: updated node importance scores conditioned on current acoustic evidence.

**Recommendation:** Phase 4 enhancement, applicable when concept graphs are sufficiently rich (>100 nodes per baby) to benefit from graph-based reasoning. Computationally expensive; GPU inference on SageMaker endpoint. Most valuable in 18–24 month period when concept graphs are dense.

### 11.7 Active Learning for Parent Question Selection

**Gap:** Parent questions (e.g., "What were they doing when they made this sound?") are currently triggered by a simple rule: new acoustic cluster appears. Active learning approaches could optimize the selection of questions to maximize information gain — asking about clusters that, if confirmed, would most reduce uncertainty in the concept graph.

**Method:** Information gain criterion for question selection: ask about cluster $c$ that maximizes $IG(PCG; \text{answer}(c)) = H(PCG) - \mathbb{E}[H(PCG | \text{answer}(c))]$. This selects the question whose answer would most reduce uncertainty in the concept graph, making each parent interaction maximally informative.

**Practical application:** Rather than asking about every new cluster (which could overwhelm parents), rank clusters by expected information gain and ask about at most 1–2 per session, selecting the most informative.

**Recommendation:** Phase 2 enhancement — low implementation cost, high UX benefit (reduces parent question fatigue). Implement as ranking function over candidate clusters with information gain proxy (variance in current concept probability distribution as proxy for expected information gain).

---

---

## 12. Baby Profile — Foundational Inputs

### 12.1 Required Fields at Registration

Baby profile is stored in DynamoDB `baby_profiles` table. **All fields marked REQUIRED must be collected before the first session can be processed.**

```json
{
  "child_id":    "uuid",
  "baby_name":   "Emma",
  "birth_date":  "2024-06-15",
  "parent_id":   "parent_uuid",
  "enrolled_at": "2024-06-15T09:00:00Z",
  "profile_complete": true
}
```

**`baby_name`** — Required. Used in every piece of parent-facing text. The system must never output "your baby" when the name is known. Every Lambda generating insight text receives baby_name and uses it.

**`birth_date`** — Required. The cornerstone. Every session computes `age_months = (session_date - birth_date) / 30.44`. This drives the developmental stage classifier, which routes the session through the correct pipeline version.

### 12.2 Developmental Age Computation (Every Session)

```python
def compute_developmental_context(birth_date, session_date, acoustic_features):
    age_days   = (session_date - birth_date).days
    age_months = age_days / 30.44

    # Acoustic confirmation adjusts age-based classification
    acoustic_stage = classify_from_acoustics(acoustic_features)
    age_stage      = classify_from_age(age_months)

    # Take more advanced of the two (acoustics can lead age)
    stage = max(acoustic_stage, age_stage, key=stage_ordinal)

    return {
        "age_months": round(age_months, 1),
        "age_days":   age_days,
        "stage":      stage,         # NEWBORN / YOUNG_INFANT / ... / PRESCHOOL
        "pipeline":   stage_to_pipeline(stage),  # PRE_LINGUISTIC / TRANSITION / LINGUISTIC
        "feedback_schema_version": stage_to_schema(stage)
    }
```

---

## 13. Age-Wise Feedback Schema — Stage-Aware Data Model

This section documents the complete evolution of the feedback system as the baby develops. This is critical: a single feedback form does not work across 0–36 months.

### 13.1 The Core Problem

- **3 months:** baby cannot want a specific toy — feeding/comfort/sleep covers everything
- **15 months:** baby has 80+ concepts in personal graph — fixed 6 options miss 95% of what they want
- **30 months:** baby is speaking full sentences — asking "did it help?" is meaningless

### 13.2 Stage-by-Stage Feedback Schema

All stages stored in `feedback` DynamoDB table. `developmental_stage` + `stage_version` fields declare which schema applies to the `feedback_payload` JSON attribute.

**PRE_LINGUISTIC — 0 to 6 months**
```json
{
  "developmental_stage": "PRE_LINGUISTIC",
  "stage_version": "0-6m",
  "feedback_payload": {
    "response_type": "feeding | comfort | sleep_routine | discomfort_check | reduce_stimulation | vocal_play",
    "effectiveness": "helpful | neutral | ineffective",
    "word_token": "optional string — did you hear a repeated sound? e.g. baba, dada, meh"
  }
}
```

**YOUNG_INFANT — 6 to 12 months**
```json
{
  "developmental_stage": "YOUNG_INFANT",
  "stage_version": "6-12m",
  "feedback_payload": {
    "response_type": "feeding | comfort | sleep_routine | discomfort_check | reduce_stimulation | vocal_play",
    "effectiveness": "helpful | neutral | ineffective",
    "free_text": "optional — what do you think they wanted? what happened?",
    "sound_description": "optional — what sound did they make?"
  }
}
```

**TODDLER_EARLY — 12 to 18 months**
```json
{
  "developmental_stage": "TODDLER_EARLY",
  "stage_version": "12-18m",
  "feedback_payload": {
    "concept_selected": "concept_node_id or null",
    "fixed_fallback": "feeding | comfort | sleep | null",
    "free_text": "what did they want? describe if not in list",
    "effectiveness": "helpful | neutral | ineffective",
    "sound_description": "what sound did they make?"
  }
}
```
Note: `concept_selected` options are dynamically generated from this baby's personal concept graph — not a fixed list.

**TODDLER_MID — 18 to 24 months**
```json
{
  "developmental_stage": "TODDLER_MID",
  "stage_version": "18-24m",
  "feedback_payload": {
    "concept_selected": "concept_node_id or null",
    "free_text": "primary — what did they say or want?",
    "partial_transcription": "optional — what sounds did they make?",
    "effectiveness": "helpful | neutral | ineffective",
    "understood": "fully | partially | not_at_all"
  }
}
```

**TODDLER_LATE — 24 to 36 months**
```json
{
  "developmental_stage": "TODDLER_LATE",
  "stage_version": "24-36m",
  "feedback_payload": {
    "transcription": "what did they say — full sentence attempt",
    "concept_selected": "concept_node_id or null",
    "free_text": "what did they want?",
    "understood": "yes | mostly | no",
    "language_quality": "full_sentence | word_combination | sounds_only"
  }
}
```
Note: **No `effectiveness` field.** When a child speaks a complete sentence, there is no "did it help?" — the child communicated. The insight at this stage is language development, not need interpretation.

**PRESCHOOL — 36 months+**
```json
{
  "developmental_stage": "PRESCHOOL",
  "stage_version": "36m+",
  "feedback_payload": {
    "transcription": "what did they say",
    "understood": "yes | mostly | no",
    "language_quality": "complex_sentence | simple_sentence | word_combination",
    "emotional_tone": "calm | excited | distressed | frustrated | happy"
  }
}
```

### 13.3 Stage-Aware UI Rendering Rules

| Stage | "baba/dada" hint | Concept list | Free text | Effectiveness Q | Transcription |
|---|---|---|---|---|---|
| 0–6m | Yes | No | No | Yes | No |
| 6–12m | No — "what sound?" | No | Optional | Yes | No |
| 12–18m | No | Yes — from graph | Prominent | Yes | No |
| 18–24m | No | Quick taps | Primary | Yes | No |
| 24–36m | No | Tap or type | Primary | **No** | Yes |
| 36m+ | No | No | Primary | **No** | Yes |

### 13.4 Insight Title by Stage

| Stage | Insight Page Title |
|---|---|
| 0–18m | "[Name]'s Vocalization Analysis" |
| 18–24m | "[Name]'s Communication Session" |
| 24m+ | "[Name]'s Language Session" |

### 13.5 Concept List Generation

The concept list shown in TODDLER_EARLY and TODDLER_MID stages is generated dynamically per session from the child's personal concept graph:

```python
def get_feedback_concept_options(child_id, max_options=8):
    concepts = query_concept_graph(child_id)
    # Sort by: recently confirmed > high frequency > high confidence
    ranked = sort_concepts(concepts, by=["last_confirmed", "frequency", "confidence"])
    top = ranked[:max_options]
    return [{"id": c.id, "label": c.label} for c in top] + [{"id": "other", "label": "Something else"}]
```

The list is different for every baby and changes as their concept graph grows. "Something else → describe below" always appears at the end, and free text from that feeds the NLP pipeline to potentially create a new concept node.

---

*End of TECHNICAL_PIPELINE.md*
