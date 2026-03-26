# Phase 3 Complete: Age-Bucket Training Pipeline

**Status**: ✅ COMPLETE  
**Date**: Continued from Phase 2  
**Duration**: ~3.5 hours

## Overview

Phase 3 implements per-age-bucket training where each age-day/week/slot trains separately. This is the core of the daily-age precision system - day 31 trains only on day-31 samples, never mixed with other ages.

## What Was Implemented

### 1. Training Check Lambda - Per-Bucket Logic (lambdas/training_check/handler.py)

Complete rewrite to support bucket-specific training:

**New Functions:**
- `_count_samples_per_bucket()` - Groups confirmed samples by age buckets (day/week/slot)
- `_check_buckets_for_training()` - Checks training conditions per bucket independently
- `_get_last_training_date_for_bucket()` - Gets last training date for specific bucket
- `_start_training_for_bucket()` - Starts Step Function with bucket parameters

**Key Changes:**
- Scans all confirmed samples and groups by age_day_bucket, age_week_bucket, age_slot_bucket
- Each bucket checked independently against thresholds (50 batch / 10 weekly)
- Multiple training runs triggered per check (one per bucket ready for training)
- Passes bucket parameters to Step Function: bucket_type, bucket_value, communication_stage

**Example Output:**
```json
{
  "triggered": true,
  "training_runs": [
    {"bucket_type": "day", "bucket_value": "45", "run_id": "retrain-day-45-20260326-143022"},
    {"bucket_type": "week", "bucket_value": "12", "run_id": "retrain-week-12-20260326-143023"}
  ],
  "total_buckets_checked": 47
}
```

### 2. Model Trainer Lambda - Bucket-Specific Training (lambdas/model_trainer/handler.py)

Updated all training steps to handle bucket parameters:

**_step_load() Changes:**
- Accepts bucket_type, bucket_value, communication_stage from event
- Filters samples by specific bucket using DynamoDB scan with FilterExpression
- Backward compatible: if no bucket params, trains globally (all samples)
- Passes bucket params through to next steps

**_step_promote() Changes:**
- S3 path now includes bucket hierarchy: `models/{stage}/{bucket_type}/{bucket_value}/v{N}/model_weights.npz`
- ModelVersions record includes: age_bucket_type, age_bucket_value, communication_stage
- Deactivates previous model for same bucket only (not all models)
- Example paths:
  - `models/A/day/45/v1/model_weights.npz`
  - `models/B/week/12/v2/model_weights.npz`
  - `models/C/slot/181_365/v1/model_weights.npz`

**_get_active_model_version() Changes:**
- Now accepts bucket_type and bucket_value parameters
- Queries ModelVersions filtered by bucket (not just active flag)
- Returns version number for specific bucket

**ModelVersions Schema Update:**
```python
{
  "model_type": "emotion_classifier",
  "version": 1,
  "age_bucket_type": "day",        # NEW
  "age_bucket_value": "45",        # NEW
  "communication_stage": "A",      # NEW
  "s3_path": "models/A/day/45/v1/model_weights.npz",
  "accuracy": 0.67,
  "active": True,
  "trained_at": "2026-03-26T14:30:22Z"
}
```

### 3. Emotion Classifier - Model Degradation Chain (shared/emotion_classifier.py)

Added graceful degradation logic to find the most specific model available:

**New Functions:**
- `load_best_model_for_age(age_days, communication_stage)` - Main degradation chain entry point
- `_get_age_slot(age_days)` - Calculates slot bucket (0_90, 91_180, 181_365, 366_730)
- `_try_load_bucket_model(bucket_type, bucket_value, stage)` - Attempts to load specific bucket model

**Degradation Chain:**
```
1. Day model (age_day_bucket=45)
   ↓ not found
2. Week model (age_week_bucket=6)
   ↓ not found
3. Slot model (age_slot_bucket="0_90")
   ↓ not found
4. Global model (bucket_type="global", bucket_value="all")
   ↓ not found
5. Basic mode (rule-based fallback in cry_rules.py)
```

**Example Usage:**
```python
# For a 45-day-old baby
load_best_model_for_age(age_days=45, communication_stage="A")
# Tries: day_45 → week_6 → slot_0_90 → global → Basic mode

# For a 200-day-old baby
load_best_model_for_age(age_days=200, communication_stage="C")
# Tries: day_200 → week_28 → slot_181_365 → global → Basic mode
```

## Architecture Changes

### Training Flow (Before Phase 3):
```
EventBridge → training_check → Step Function (single run)
                                    ↓
                              Load ALL samples
                                    ↓
                              Train ONE model
                                    ↓
                              Store at models/emotion_classifier/v{N}/
```

### Training Flow (After Phase 3):
```
EventBridge → training_check → Check ALL buckets
                                    ↓
                              Trigger MULTIPLE Step Functions
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
              Bucket: day_45   Bucket: week_12  Bucket: slot_0_90
                    ↓               ↓               ↓
              Load day_45      Load week_12     Load slot_0_90
              samples only     samples only     samples only
                    ↓               ↓               ↓
              Train day_45     Train week_12    Train slot_0_90
              model            model            model
                    ↓               ↓               ↓
              Store at:        Store at:        Store at:
              models/A/        models/B/        models/C/
              day/45/v1/       week/12/v2/      slot/181_365/v1/
```

### Inference Flow (Phase 3):
```
Baby age: 45 days, Stage A

1. Try load: models/A/day/45/v*/model_weights.npz
   → Found! Use day-45 model

Baby age: 200 days, Stage C (no day-200 model trained yet)

1. Try load: models/C/day/200/v*/model_weights.npz → Not found
2. Try load: models/C/week/28/v*/model_weights.npz → Not found
3. Try load: models/C/slot/181_365/v*/model_weights.npz → Found! Use slot model
4. (If not found) → Try global model
5. (If not found) → Use Basic mode (age-adjusted rules from Phase 2)
```

## Backward Compatibility

✅ **Global training still works:**
- If bucket params not provided, trains on all samples
- Stores at `models/global/all/v{N}/`

✅ **Existing models still load:**
- Old models without bucket params treated as global
- Degradation chain falls back to global before Basic mode

✅ **Phase 2 Basic mode preserved:**
- If no models available, uses age-adjusted rule-based scoring
- Zero external dependencies

## Critical Preservation

✅ **Age-bucket separation enforced**: Day 31 trains only on day-31 samples  
✅ **Graceful degradation**: Always finds best available model or falls back to Basic  
✅ **0-3 month quality preserved**: Day 45 model trained only on day-45 babies  
✅ **Independent deployment**: Each bucket trains and deploys independently

## Testing Scenarios

### Test 1: First training for day 45
```python
# training_check finds 50 confirmed samples for day_45
# Triggers: retrain-day-45-20260326-143022
# Loads: 50 samples where age_day_bucket=45
# Trains: day-45 specific model
# Stores: models/A/day/45/v1/model_weights.npz
# ModelVersions: {bucket_type: "day", bucket_value: "45", version: 1, active: True}
```

### Test 2: Inference for 45-day baby
```python
load_best_model_for_age(age_days=45, communication_stage="A")
# Tries: models/A/day/45/v1/model_weights.npz → Found!
# Uses: day-45 model
```

### Test 3: Inference for 46-day baby (no day-46 model yet)
```python
load_best_model_for_age(age_days=46, communication_stage="A")
# Tries: models/A/day/46/v*/model_weights.npz → Not found
# Tries: models/A/week/6/v*/model_weights.npz → Found!
# Uses: week-6 model (covers days 42-48)
```

### Test 4: Multiple buckets ready
```python
# training_check finds:
# - day_45: 50 new samples
# - week_12: 55 new samples
# - slot_181_365: 60 new samples
# Triggers 3 independent Step Functions
# Each trains on its own bucket samples only
```

## Files Modified

1. `lambdas/training_check/handler.py` - Complete rewrite for per-bucket logic
2. `lambdas/model_trainer/handler.py` - Updated load/promote for bucket parameters
3. `shared/emotion_classifier.py` - Added degradation chain logic
4. `infrastructure/phase1_new_tables.tf` - Fixed Terraform variables (bug fix)

## Next Steps: Phase 4

Phase 4 will implement the Population Atlas:
1. Create `shared/atlas_builder.py` - Update daily atlas with each session
2. Update `lambdas/feature_extraction/handler.py` - Call atlas builder
3. Update `lambdas/insight_generator/handler.py` - Add population context to insights
4. Show parents where their baby sits in population distribution

## Performance Implications

**Training:**
- More frequent training runs (one per bucket vs one global)
- Each run smaller and faster (bucket samples only vs all samples)
- Parallel execution possible (independent buckets)

**Inference:**
- Slightly slower first call (tries multiple S3 paths)
- Cached after first load (same model for same age)
- More accurate predictions (age-specific models)

**Storage:**
- More model files (one per bucket vs one global)
- Each file smaller (~2MB per model)
- S3 costs minimal (pay per GB-month)

---

**Phase 3 Duration**: ~3.5 hours  
**Phase 3 Status**: ✅ COMPLETE  
**Ready for**: Phase 4 (Population Atlas)
