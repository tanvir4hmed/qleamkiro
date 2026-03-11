# QLEAM Technical Documentation

## 1. System Scope and Runtime Modes

QLEAM is a web application for parent-guided baby sound analysis for children aged **0-24 months**.

Core behavior:
- Parent records audio in browser (`audio/webm`).
- Audio is uploaded to S3 via pre-signed URL.
- AWS Step Functions orchestrates classification and insight generation.
- Session insight is stored in DynamoDB and shown in frontend.
- Optional parent feedback can convert a session into confirmed training data.

Runtime AI modes:
- **Basic**: rule-based cry emotion path (no HuBERT call).
- **Advanced**: HuBERT embedding extraction + classifier path for `cry`/`mixed` when endpoint and flag are enabled.

Mode decision source:
- API `/status` reports `ai_mode = "Advanced"` only when:
  - `USE_SAGEMAKER_INTENT_ENDPOINT = true`
  - `SAGEMAKER_HUBERT_ENDPOINT` is non-empty
- Otherwise `ai_mode = "Basic"`.

## 2. Platform Architecture

### 2.1 Core stack
- Frontend: React + Amplify Auth UI
- Auth: AWS Cognito (JWT bearer)
- API: API Gateway -> `api_handler` Lambda
- Orchestration: Step Functions
- Audio/object store: S3
- Metadata store: DynamoDB
- Advanced audio embeddings: SageMaker endpoint (HuBERT)
- Optional speech path: Amazon Transcribe
- Infrastructure: Terraform

### 2.2 Lambda responsibilities
- `api_handler`: Auth, child/session CRUD, upload/start endpoints, feedback forwarding, status
- `feature_extraction`: Audio decode, quality/reject gates, diarization, sound classification, adult detection, optional HuBERT/classifier
- `insight_generator`: Final parent-facing insight assembly and session update
- `feedback_processor`: Feedback persistence + training anonymization gates
- `training_check`: Scheduled threshold check for retraining
- `model_trainer`: Load/train/validate/promote emotion classifier weights

### 2.3 Step Functions
- **Processing pipeline**: `AudioClassifier -> (FastReject Choice) -> InsightGenerator -> Succeed`
- **Training pipeline** (enabled in dev Terraform root): `TrainingCheck -> Load -> Train -> Validate -> Promote`

## 3. Active Data Model

Only the following DynamoDB tables are active in current code and infrastructure.

| Table | Primary Keys | Main Purpose | Main Writers/Readers |
|---|---|---|---|
| `ChildProfile` | PK: `child_id`, GSI: `parent_id-index` | Child profile and ownership (`parent_id`, DOB, metadata) | API create/list/delete, ownership checks |
| `Session` | PK: `session_id`, GSI: `child_id-timestamp-index` | Session lifecycle, analysis outputs, insight payload | API upload/list/insight, feature extraction, insight generator |
| `Feedback` | PK: `feedback_id`, GSI: `session_id-created_at-index` | Parent feedback records | feedback processor, child/account deletion cleanup |
| `TrainingFeatures` | PK: `feature_id`, GSI: `sound_type-age_days-index` | HuBERT embedding references + training metadata | feature extraction, feedback processor, training check, model trainer |
| `ModelVersions` | PK: `model_type`, SK: `version` | Versioned trained model registry | model trainer promote/lookup, classifier S3 load |

### 3.1 `TrainingFeatures` lifecycle fields
- Created at session time (advanced cry/mixed path) with fields like:
  - `feature_id`, `session_id`, `s3_embeddings_path`, `sound_type`
  - `predicted_emotion`, `predicted_confidence`, `model_version`
  - `age_days`, `duration_s`, `created_at`
- After accepted feedback, updated to confirmed training sample:
  - `confirmed_emotion`, `confirmation_source`, `confirmed_at`
  - `is_confirmed = true`, `model_confidence_at_time`, `audio_quality_snr`
  - `session_id` is removed during anonymization.


## 4. API Contract (Current)

### 4.1 Child/account
- `GET /child`
- `POST /child`
- `DELETE /child/{child_id}`
- `DELETE /account`

### 4.2 Session flow
- `POST /session/upload` -> create pending session + pre-signed S3 URL
- `POST /session/{session_id}/start` -> starts Step Functions processing
- `GET /session/{session_id}/insight` -> returns insight or `status=processing`
- `GET /child/{child_id}/sessions` -> session cards/summary for dashboard

### 4.3 Feedback and status
- `POST /session/{session_id}/feedback`
  - Only `feedback_type = cry_emotion` is accepted by API handler route.
- `GET /child/{child_id}/training-stats`
- `GET /status` -> AI mode and endpoint flags

## 5. End-to-End Session Pipeline

## 5.1 Frontend recording and upload
`RecordButton` behavior:
- Min duration: 5 seconds (UI enforced)
- Max duration: 30 seconds (auto stop)
- Flow:
  1. `POST /session/upload`
  2. Browser `PUT` audio to S3 pre-signed URL
  3. `POST /session/{id}/start`

## 5.2 API preflight checks before processing
At upload/start time API verifies:
- Child exists and belongs to calling parent (`parent_id` vs Cognito `sub`)
- `birth_date` exists and is valid
- Child age is inside 0-24 months (`<= 730` days)

## 5.3 Processing state machine behavior
- `feature_extraction` result is stored under `classifier_result` state path.
- If `fast_reject=true`, processing goes to `InsightGeneratorFastReject`.
- If Lambda task throws hard error after retries, state machine goes to `ProcessingFailed`.

## 5.4 `feature_extraction` runtime stages

### Stage A: decode and trim
- Download audio bytes from S3
- Decode via ffmpeg path to mono float32 at 22050 Hz
- Apply VAD trim (fallback to decoded full audio if over-trimmed)

### Stage B: quality gate
`audio_quality_gate` computes:
- `snr_db`
- `silence_ratio`
- `clipping_ratio`
- `voiced_energy_fraction`
- `noise_floor_db`, `lombard_flag`

Critical reject mapping (`_check_critical_issues`):
- Broken audio class:
  - `no_signal`, `too_short`, `too_long`, `clipping`
  - Title: `Audio Quality Issue`
- Noisy class:
  - `low_snr`, `too_silent`, `no_vocal_activity_detected`
  - Title: `Noisy Environment`

### Stage C: diarization and baby segment enhancement
- Segment voiced regions (`diarize`)
- Extract probable baby portions (`extract_baby_audio`)
- Apply lightweight denoise/pre-emphasis (`_enhance_baby_signal`)

### Stage D: core features and early reject
`compute_core_features` derives once and reuses:
- F0 stats, RMS stats, spectral metrics, ZCR, syllable and burst measures

Early reject (`_check_early_rejection`):
- Silence/no voiced frames -> `No Sound Detected`
- Adult-only low-F0 voiced signal -> `Adult Voice Detected`

### Stage E: sound type and adult checks
- Sound classifier labels: `cry`, `speech`, `laugh`, `silence`, `noise`, `mixed`
- Segment aggregation builds `sound_summary`
- Biological + age classifier outputs are combined into final `is_adult`
- Post-classification reject rules enforce:
  - age scope
  - adult voice
  - speech rejection in cry-only infant logic
  - chaotic/noisy mixed audio

### Stage F: routing flags
Routing booleans are derived:
- `run_transcription`
- `run_cry_analysis`
- `run_laugh_detection`

Transcription is force-disabled when `age_days <= 90`.

### Stage G: advanced-only embedding/classifier path
This path runs only when all are true:
- `USE_SAGEMAKER_INTENT_ENDPOINT = true`
- `SAGEMAKER_HUBERT_ENDPOINT` configured
- `sound_type in ("cry", "mixed")`

Then:
1. HuBERT embedding is requested from endpoint.
2. If embedding shape is 768, classifier predicts emotion.
3. `TrainingFeatures` candidate is stored (S3 `.npy` + DDB metadata).

If HuBERT/classifier call fails, error is non-fatal and session proceeds.

### Stage H: session persistence
`Session` record includes:
- classification outputs (`sound_type`, `sound_summary`, `sound_features`)
- quality/diarization/adult diagnostics
- `classifier_result` (or `null`)
- routing flags

## 5.5 `insight_generator` behavior

### Fast reject branch
When `fast_reject=true` in event:
- Builds reject insight with warning headline + reject message
- Stores insight immediately

### Non-reject branch
Routes by `sound_type`:
- `silence`: no sound message
- `noise`: unrecognized/noisy message
- `laugh`: laugh insight (adult override if detected)
- `speech`: transcript/word insight
- `cry`: cry analyzer path
- `mixed`: priority order:
  1. speech (if words found)
  2. cry (if cry score > 0.3)
  3. laugh (if laugh score > 0.3)
  4. mixed fallback message

## 5.6 Cry emotion source of truth
`analyze_cry` decision:
- If `classifier_result.using_model == true`: use classifier probabilities
- Else: use rule engine `analyze_cry_rules`

Important result fields in insight:
- `emotion`, `emotion_confidence`
- `emotion_scores` (7-class radar source)
- `top_emotions`
- `acoustic_features` (separate radar source)
- `narrative_data`, `insight_sections`
- `dunstan_sound` (age-constrained display)

## 6. Frontend Insight Mapping

Session detail page (`SessionDetail` + `InsightPanel`):
- Polls `GET /session/{id}/insight` until ready
- `EmotionRadar` reads `insight.emotion_scores`
- `AcousticRadar` reads `insight.acoustic_features`
- Acoustic textual detail comes from normalized acoustic metrics (pitch, energy, stability, voicing, brightness, variation)

Key UI interpretation:
- There is one final insight payload.
- Acoustic values are displayed as explanation/visualization.
- Emotion probabilities come from classifier output when available, otherwise from rule-based cry engine.

## 7. AI Mode Semantics and Fallback Matrix

| Condition | HuBERT called | Emotion probability source | Notes |
|---|---|---|---|
| `Advanced ON` + endpoint configured + cry/mixed + model usable | Yes | Classifier (`using_model=true`) | Preferred advanced path |
| `Advanced ON` + endpoint configured + cry/mixed + classifier fallback | Yes | Rule-based cry (`analyze_cry_rules`) | Happens when classifier returns `using_model=false` |
| `Advanced ON` + endpoint configured + non-cry/non-mixed | No | N/A for cry model | Normal non-cry routing |
| `Basic ON` (`Advanced OFF`) | No | Rule-based cry (`analyze_cry_rules`) | HuBERT path skipped entirely |

Failure semantics:
- Controlled reject (quality/adult/noise gates) -> reject insight is generated.
- Hard pipeline failure before insight write -> session can remain in processing state until timeout/retry logic at client side.

## 8. Self-Learning Pipeline

## 8.1 Candidate creation
Candidates are generated only when:
- session is `cry` or `mixed`
- advanced HuBERT path executes
- 768-d embedding is produced

Output:
- embeddings in S3: `training-features/{feature_id}/embeddings.npy`
- metadata row in `TrainingFeatures`

## 8.2 Feedback intake and gates
API sends cry feedback to `feedback_processor`.

Applied gates (`apply_quality_gates`):
1. Embeddings exist (`TrainingFeatures` row found by `session_id`)
2. Confirmed emotion is valid (not skip/not_sure/unknown)
3. Quality threshold: `SNR >= 10`, `duration >= 3`, `sound_type in (cry,mixed)`
4. Confidence gate for confirmations: if `was_correct=true`, model confidence must be `>= 0.4`
5. Dedup: same session cannot be confirmed twice

Gate behavior nuance:
- `was_correct=false` corrections bypass gate #4 and can be accepted if other gates pass.

## 8.3 Notes/text feedback impact
- API truncates `notes` to 500 chars and forwards payload.
- Cry training path does not use notes as model features.
- In current cry feedback processing path, notes are not added to training signal.

## 8.4 Anonymization
When accepted:
- Adds confirmed label fields
- Sets `is_confirmed=true`
- Removes `session_id` from `TrainingFeatures`
- Keeps de-identified fields needed for model training and audit

## 8.5 Retraining trigger
`training_check` thresholds:
- total confirmed must be `>= 30`
- trigger when either:
  - new confirmed since last training `>= 50`, or
  - new confirmed `>= 10` and at least 7 days since last training

## 8.6 Trainer and promotion
`model_trainer` steps:
1. Load confirmed embeddings + age encodings
2. Train two-branch model (embedding branch + age branch)
3. Validate against active model
4. Promote if improved by margin (`+0.02`), or bootstrap rule when no active model and accuracy >= 0.30

Promotion writes:
- S3 model artifact: `models/emotion_classifier/v{N}/model_weights.npz`
- `ModelVersions` record with `active=true`
- marks features with `included_in_training`

## 9. Data Deletion and Privacy

## 9.1 Child deletion (`DELETE /child/{child_id}`)
Deletes direct personal data:
- all child sessions
- feedback rows linked to each session
- S3 audio objects under `{child_id}/{session_id}/`
- child profile row

Not deleted by this operation:
- de-identified `TrainingFeatures` already anonymized for shared model training
- `ModelVersions` shared model metadata

## 9.2 Account deletion (`DELETE /account`)
- Iterates all parent-owned children
- applies same direct-data deletion logic per child

## 9.3 Ownership enforcement
- API uses Cognito `sub` as parent identity
- every child/session sensitive action checks ownership before read/write/delete

## 10. Current Implementation Notes

These are current behaviors that affect operations and interpretation.

1. **Numpy self-trained weight loading path is defined but not invoked by runtime cold start**
- `shared/emotion_classifier.py` contains `load_numpy_model()`.
- `feature_extraction` cold start calls `load_model()` (TFLite loader) only.
- Result: promoted `.npz` weights may not influence inference unless load wiring is explicitly added.

2. **Phase-2 TFLite baseline requires model artifact packaging**
- Classifier expects `/var/task/models/emotion_classifier.tflite` (or `EMOTION_MODEL_PATH`).
- Current Dockerfiles in repo do not copy a `.tflite` model file.
- If TFLite is unavailable and numpy model is not loaded, classifier falls back (`using_model=false`) and cry path uses rule engine.

3. **Training contribution child counter depends on unavailable field in current ingestion path**
- Dashboard shows training contribution only if `child_count > 0` from `/training-stats`.
- Current `TrainingFeatures` writer does not include `child_id`; API query filters on `child_id` for child-specific count.
- Operationally this can keep child contribution display at zero despite confirmed samples.

4. **Scope normalization function currently applies to full supported age range**
- `_normalize_sound_type_for_scope()` comments describe strict early-age behavior.
- Current guard checks only `age_days <= 730`, so normalization logic can affect all in-scope ages.
- This should be interpreted as current runtime behavior.
## Bug Fixing and future plan/ improvements.

### A. Bug fixing scope (high priority)

1. **Activate self-trained model weights in live inference path**
- Wire `load_numpy_model()` into cold start for `feature_extraction` classifier initialization.
- Keep deterministic precedence: numpy model (if active) + optional public baseline blend.
- Add explicit logs on loaded model source/version at cold start.

2. **Guarantee baseline classifier availability**
- Package `emotion_classifier.tflite` into the feature extraction runtime image, or set `EMOTION_MODEL_PATH` to mounted artifact location.
- Add startup health check to emit hard warning when no classifier artifact is available.

3. **Fix training contribution metrics**
- Decide one source of truth for child-level contribution:
  - Option A: include a privacy-safe child token in `TrainingFeatures` before anonymization strategy update.
  - Option B: compute contribution from `Feedback` + confirmation result join logic.
- Update `/child/{child_id}/training-stats` to use fields that are actually persisted.

4. **Align age-scope normalization behavior with intended policy**
- If normalization should be infant-only, gate `_normalize_sound_type_for_scope` with `age_days <= 90`.
- If all-age behavior is desired, update policy/docs/tests to make it explicit and remove contradictory comments.

5. **Feedback retrieval efficiency and integrity**
- Add index strategy for `TrainingFeatures` lookup by `session_id` to avoid table scan in gate #0.
- Add idempotency token/condition checks for feedback writes under high retry traffic.

### B. Model-path simplification plan

Goal: single classifier decision path without fragile multi-branch duplication.

Recommended runtime abstraction:
- `classifier_enabled = (advanced_on and hubert_endpoint_ok) or basic_weight_mode_on`
- If `classifier_enabled` and embedding available:
  - run classifier once
  - use classifier probabilities when `using_model=true`
- Else:
  - run rule-based cry probabilities

This avoids duplicated scoring passes and prevents accidental double-application of weights.

### C. Basic-mode + self-trained-data plan

Current reality:
- Basic mode skips HuBERT call entirely, so current HuBERT-based classifier is bypassed.

If basic mode must leverage self-trained data:
- Add a local embedding path (or alternate embedding extractor) callable without SageMaker.
- Feed resulting embeddings into the same classifier interface used by advanced mode.
- Keep rule engine as guaranteed fallback when embedding extraction/classifier fails.

### D. Feedback quality and trust hardening plan

Existing protection already present:
- low-confidence confirmation gate (`was_correct=true` requires confidence >= 0.4)
- correction acceptance path
- dedup gate

Additional hardening candidates:
1. Trust weighting per parent account over time (calibrated by consistency and disagreement patterns).
2. Outlier detection on parent labels vs cohort acoustic neighborhood.
3. Temporal sanity checks (rapid contradictory submissions, impossible label flip patterns).
4. Weighted training instead of binary include/exclude for borderline confirmations.

### E. Low-feedback participation plan

Problem:
- Unconfirmed samples do not enter retraining; passive users reduce learning throughput.

Mitigation options:
1. Trigger feedback prompts only on low-confidence sessions (active-learning style).
2. Offer one-tap feedback shortcuts in session list to reduce friction.
3. Use periodic summary confirmation rather than per-session prompts for engagement.
4. Capture weak supervision signals (e.g., repeated correction behavior) with lower training weight.

### F. Age coverage evolution plan (0-24 months)

Current state includes 0-24 month admission, but handcrafted cry rules are centered on early-age profiles.

Planned extension:
1. Split rule profiles by age bands (0-3m, 3-6m, 6-12m, 12-24m).
2. Calibrate narrative templates and recommendation text per age band.
3. Keep model training age-conditioned (already architecturally supported by age encoder).
4. Expand validation sets by age group to prevent overfitting to newborn-heavy data.

### G. Reliability and observability improvements

1. Add explicit per-session `inference_path` in saved session (`rule_only`, `phase2`, `phase4`, `blended`, `fallback`).
2. Track `model_loaded_state` and endpoint health in `/status` for operator visibility.
3. Add alarms for prolonged `processing` sessions with missing insight writes.
4. Add canary checks for end-to-end advanced path (HuBERT + classifier + insight write).
