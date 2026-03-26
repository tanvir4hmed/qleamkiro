# Phase 1: Complete Data Schema Reference

## ChildProfile Table

### Primary Key
- `child_id` (String) - Partition Key

### Attributes
```
child_id (String) - UUID
parent_id (String) - Cognito user ID [GSI]
name (String)
birth_date (String) - YYYY-MM-DD format
gender (String) - "boy", "girl", "other", or ""
language_region (String) - NEW: "en", "zh", "ar", "fr", "de", "es", "pt", "hi", "ko", "ja", "multilingual", "other"
trust_score (Number) - NEW: 0.0-1.0, default 0.5
baseline_features (Map)
readiness_score (Number)
session_count (Number)
created_at (String) - ISO timestamp
updated_at (String) - ISO timestamp
```

### GSI
- `parent_id-index`: PK=parent_id

---

## TrainingFeatures Table

### Primary Key
- `feature_id` (String) - Partition Key

### Attributes
```
feature_id (String) - UUID
session_id (String) - Links to Session [GSI: session_id-index]
s3_embeddings_path (String) - S3 key for HuBERT embeddings
sound_type (String) - cry, babble, speech, laugh, mixed, etc.
predicted_emotion (String)
predicted_confidence (Number)
model_version (String)
age_days (Number)
duration_s (Number)
created_at (String)

# Phase 1: New Fields
age_day_bucket (Number) - Exact age in days [GSI]
age_week_bucket (Number) - Week number (age_days // 7 + 1)
age_slot_bucket (String) - "A", "B", "C", "D", "E", "F"
communication_stage (String) - "cry", "babble", "word", "laugh" [GSI]
language_region (String) - From parent profile
flagged_for_training (Boolean) - Explicit training flag

# Confirmation fields (added by feedback processor)
is_confirmed (Boolean)
confirmed_emotion (String)
confirmation_source (String) - "parent_confirm" or "parent_correct"
confirmed_at (String)
model_confidence_at_time (Number)
audio_quality_snr (Number)

# Trust gate fields
quarantined (Boolean)
quarantine_reason (String)

# Training lifecycle
included_in_training (Boolean)
trained_at (String)
```

### GSI
- `session_id-index`: PK=session_id
- `age_day_bucket-stage-index`: PK=age_day_bucket, SK=communication_stage (NEW)

---

## BabyDailyAtlas Table (NEW)

### Primary Key
- `age_day` (Number) - Partition Key
- `feature_key` (String) - Sort Key

### Attributes
```
age_day (Number) - Age in days (1-730)
feature_key (String) - Feature name (e.g., "f0_mean", "rms_mean", "spectral_centroid")
centroid (Number) - Population mean for this feature at this age
std_dev (Number) - Standard deviation
min_observed (Number) - Minimum value observed
max_observed (Number) - Maximum value observed
p10 (Number) - 10th percentile
p90 (Number) - 90th percentile
sample_count (Number) - Number of samples contributing to this distribution
last_updated (String) - ISO timestamp
```

### Purpose
Population reference distribution per age-day per acoustic feature.
Used to show parents where their baby sits relative to the population.

### Example Records
```
{age_day: 31, feature_key: "f0_mean", centroid: 425.3, std_dev: 45.2, min: 280, max: 620, p10: 360, p90: 490, sample_count: 847}
{age_day: 31, feature_key: "rms_mean", centroid: 0.082, std_dev: 0.024, min: 0.03, max: 0.18, p10: 0.055, p90: 0.11, sample_count: 847}
```

---

## BabyTrajectory Table (NEW)

### Primary Key
- `child_id` (String) - Partition Key
- `session_date` (String) - Sort Key (ISO format)

### Attributes
```
child_id (String) - Links to ChildProfile
session_date (String) - ISO timestamp (YYYY-MM-DDTHH:MM:SS)
age_days (Number) - Age at this session
acoustic_snapshot (Map) - {feature_key: value} for this session
deviation_from_population (Map) - {feature_key: z_score} vs BabyDailyAtlas
communication_stage (String) - "cry", "babble", "word"
proto_words (List) - [{sound_pattern, parent_label, first_seen, count}]
personal_baseline (Map) - {feature_key: rolling_mean} over last 20 sessions
```

### Purpose
Per-baby acoustic history for individual trajectory and deviation detection.
Enables "unusual for YOUR baby" signals and proto-word tracking.

### Example Record
```json
{
  "child_id": "abc-123",
  "session_date": "2026-03-26T10:30:00Z",
  "age_days": 45,
  "acoustic_snapshot": {
    "f0_mean": 438.2,
    "rms_mean": 0.095,
    "spectral_centroid": 2150.0
  },
  "deviation_from_population": {
    "f0_mean": 0.28,
    "rms_mean": 0.54,
    "spectral_centroid": -0.12
  },
  "communication_stage": "cry",
  "proto_words": [],
  "personal_baseline": {
    "f0_mean": 432.5,
    "rms_mean": 0.088
  }
}
```

---

## ModelVersions Table

### Primary Key
- `model_type` (String) - Partition Key
- `version` (Number) - Sort Key

### Attributes (Updated)
```
model_type (String) - "emotion_classifier", "babble_classifier"
version (Number)
s3_path (String)
s3_bucket (String)
accuracy (Number)
train_samples (Number)
val_samples (Number)
active (Boolean)
trained_at (String)
train_id (String)
trigger_reason (String)
label_counts (Map)
model_architecture (String)

# Phase 1: New Fields
age_bucket_type (String) - "day", "week", "slot", "global"
age_bucket_value (String) - "31", "5", "A", "global"
communication_stage (String) - "cry", "babble", "word"
language_region (String) - "universal", "en", "zh", etc.
```

### Composite Key Pattern
For age-bucket scoped models, use composite sort key:
```
model_type: "emotion_classifier"
version: 1
composite_key: "cry#day#31#universal"
```

### Example Records
```
# Day-31 cry model
{model_type: "emotion_classifier", version: 5, age_bucket_type: "day", age_bucket_value: "31", communication_stage: "cry", language_region: "universal", s3_path: "models/cry/day/31/v5/model_weights.npz"}

# Week-5 cry model
{model_type: "emotion_classifier", version: 3, age_bucket_type: "week", age_bucket_value: "5", communication_stage: "cry", language_region: "universal", s3_path: "models/cry/week/5/v3/model_weights.npz"}

# Slot-A cry model (current working model)
{model_type: "emotion_classifier", version: 12, age_bucket_type: "slot", age_bucket_value: "A", communication_stage: "cry", language_region: "universal", s3_path: "models/cry/slot/A/v12/model_weights.npz"}
```

---

## Counter Items in TrainingFeatures Table

### Special Records for Atomic Counting
```
{feature_id: "COUNTER#total_confirmed", counter_value: 1250}
{feature_id: "COUNTER#new_since_training", counter_value: 45}
```

These are updated atomically using DynamoDB's ADD operation.
Reset "new_since_training" to 0 after each training run.

---

## Migration Notes

### Existing Records
- All existing ChildProfile records need language_region and trust_score added
- All existing TrainingFeatures records need age buckets added (Phase 11 backfill)
- Existing ModelVersions records work as-is (treated as slot-A models)

### Backward Compatibility
- New fields are optional in queries
- Old code continues to work
- New code gracefully handles missing fields with defaults
