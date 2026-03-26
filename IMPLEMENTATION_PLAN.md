# QLEAM Evolution - Implementation Plan

## Overview
This document tracks the complete implementation of the QLEAM evolution plan.
Each phase is independently deployable and testable.

---

## PHASE 0: Bug Fixes ✓ READY TO START

**Goal:** Fix 10 critical bugs without changing functionality. Verify 0-3 month output unchanged.

**Estimated Time:** 2-3 hours

### Bugs to Fix:

1. **DEVELOPMENTAL_STAGE_MAP** - `shared/constants.py`
   - Problem: All 91+ days map to NEWBORN
   - Fix: Add proper 6-stage boundaries (A-F)

2. **Training gate sound filter** - `shared/training_anonymizer.py` ~line 200
   - Problem: Rejects non-cry sound types
   - Fix: Accept all, route by communication_stage

3. **Training feature scan fallback** - `shared/training_anonymizer.py` → `_find_training_feature()`
   - Problem: Full table scan on GSI failure
   - Fix: Remove scan, log error, return None

4. **Confirmed samples counter** - `shared/training_anonymizer.py`
   - Problem: Full table scan every 5 minutes
   - Fix: Use atomic DynamoDB counter

5. **Age encoder cliff** - `shared/age_encoder.py`
   - Problem: Hard 0→1 flip at day 90
   - Fix: Smooth sigmoid decay (60→120 days)

6. **CORS fallback** - `lambdas/api_handler/handler.py` → `get_allowed_origin()`
   - Problem: Returns request origin if no match
   - Fix: Reject unknown origins in production

7. **Anonymous user fallback** - `lambdas/api_handler/handler.py` → `get_user_id()`
   - Problem: Returns "anonymous" for no auth
   - Fix: Raise exception, return 401

8. **Blend weights global** - `shared/training_anonymizer.py` → `get_blend_weights()`
   - Problem: Uses global count, not per-bucket
   - Fix: Accept age_bucket parameter

9. **Model promotion threshold** - `lambdas/model_trainer/handler.py` → `_step_validate()`
   - Problem: Promotes at 30% accuracy
   - Fix: Minimum 55% accuracy

10. **Chaotic mixed rejection** - `lambdas/api_handler/handler.py` → `_is_chaotic_mixed()`
    - Problem: Rejects valid older baby babbling
    - Fix: Age-aware threshold (0.35 → 0.15 for 90+ days)

### Testing Checklist:
- [ ] All existing tests pass
- [ ] 0-3 month session produces identical insight
- [ ] 6-month session no longer maps to NEWBORN
- [ ] Training counter increments correctly
- [ ] CORS rejects unknown origins
- [ ] Unauthenticated requests return 401

---

## PHASE 1: Schema Foundation

**Goal:** Add all new database fields and tables. Populate in code. No logic changes.

**Estimated Time:** 1-2 hours

### Database Changes:

#### 1.1 ChildProfile Table - Add Fields
- `language_region` (String) - default: "en"
- `trust_score` (Number) - default: 0.5

#### 1.2 TrainingFeatures Table - Add Fields
- `age_day_bucket` (Number)
- `age_week_bucket` (Number)
- `age_slot_bucket` (String)
- `communication_stage` (String)
- `language_region` (String)
- `flagged_for_training` (Boolean)

#### 1.3 TrainingFeatures - Add GSI
- Name: `age_day_bucket-stage-index`
- PK: `age_day_bucket` (Number)
- SK: `communication_stage` (String)

#### 1.4 Create BabyDailyAtlas Table
```
PK: age_day (Number)
SK: feature_key (String)
Attributes: centroid, std_dev, min_observed, max_observed, p10, p90, sample_count, last_updated
```

#### 1.5 Create BabyTrajectory Table
```
PK: child_id (String)
SK: session_date (String)
Attributes: age_days, acoustic_snapshot, deviation_from_population, communication_stage, proto_words, personal_baseline
```

#### 1.6 ModelVersions Table - Add Fields
- `age_bucket_type` (String)
- `age_bucket_value` (String)
- `communication_stage` (String)
- `language_region` (String)

### Code Changes:

**Files to modify:**
- `shared/constants.py` - Add table name constants
- `lambdas/api_handler/handler.py` - Populate language_region, trust_score on profile creation
- `lambdas/feature_extraction/handler.py` - Populate age buckets in TrainingFeatures

### Testing Checklist:
- [ ] New fields populate on new sessions
- [ ] GSI queries work
- [ ] language_region reads from parent profile
- [ ] No functional changes to insights

---

## PHASE 2: Day-Adjusted Basic Mode

**Goal:** Extend Basic mode to all ages 0-730 with age-interpolated thresholds.

**Estimated Time:** 2-3 hours

### Changes:

**File:** `shared/cry_rules.py`
- Add `AGE_ANCHOR_POINTS` dict with developmental curves
- Add `interpolate_threshold()` function
- Add `get_age_adjusted_profiles(age_days)` function
- Update `analyze_cry_rules()` to accept age_days parameter

**Files to update callers:**
- `shared/cry_analyzer.py` - Pass age_days to analyze_cry_rules()
- `lambdas/insight_generator/handler.py` - Pass age_days to cry analysis

### Testing Checklist:
- [ ] Day 45 baby - output identical to before
- [ ] Day 120 baby - gets age-adjusted thresholds
- [ ] Day 400 baby - interpolation works
- [ ] 0-90 range completely unchanged

---

## PHASE 3: Age-Bucket Training Pipeline

**Goal:** Per-age-bucket training. Each age-day/week/slot trains separately.

**Estimated Time:** 3-4 hours

### Changes:

**File:** `lambdas/training_check/handler.py`
- Rewrite `_count_samples_per_bucket()` - group by age buckets
- Add `_check_buckets_for_training()` - check thresholds per bucket
- Update `lambda_handler()` - trigger multiple independent training runs
- Add `_start_training_for_bucket()` - pass bucket parameters

**File:** `lambdas/model_trainer/handler.py`
- Update `_step_load()` - query by age bucket using GSI
- Update `_step_train()` - train only on bucket samples
- Update `_step_promote()` - store with composite key including bucket
- Update S3 paths: `models/{stage}/{bucket_type}/{bucket_value}/v{N}/`

**File:** `shared/emotion_classifier.py`
- Add `load_best_model_for_age()` - degradation chain (day→week→slot→global)
- Update `predict_emotion()` - use age-specific model

### Testing Checklist:
- [ ] Per-bucket training triggers correctly
- [ ] Models store with correct composite keys
- [ ] Inference uses most specific model available
- [ ] Degradation chain works (day→week→slot→basic)

---

## PHASE 4: Population Atlas

**Goal:** Build BabyDailyAtlas from all sessions. Add population context to insights.

**Estimated Time:** 2-3 hours

### Changes:

**New file:** `shared/atlas_builder.py`
- `update_daily_atlas()` - update centroid, std_dev, percentiles per age-day

**File:** `lambdas/feature_extraction/handler.py`
- Call `update_daily_atlas()` after computing features

**File:** `lambdas/insight_generator/handler.py`
- Add `_get_population_context()` - query atlas, calculate percentiles
- Add `population_context` to insight output

### Testing Checklist:
- [ ] Atlas updates with each session
- [ ] Population context appears in insights
- [ ] Percentile calculations correct
- [ ] Works with sparse data (few samples per age-day)

---

## PHASE 5: Individual Baby Trajectory

**Goal:** Track each baby's personal history. Detect deviations from baseline.

**Estimated Time:** 2-3 hours

### Changes:

**New file:** `shared/trajectory_tracker.py`
- `update_baby_trajectory()` - update personal baseline, detect deviations

**File:** `lambdas/feature_extraction/handler.py`
- Call `update_baby_trajectory()` after atlas update

**File:** `lambdas/insight_generator/handler.py`
- Add `_get_personal_context()` - compare to personal baseline
- Add `personal_context` to insight output

### Testing Checklist:
- [ ] Trajectory updates after each session
- [ ] Personal deviation detection works
- [ ] New babies (no history) handled gracefully
- [ ] Regression detection works

---

## PHASE 6: Stage-Aware Routing & Babble Analysis

**Goal:** Full 6-stage developmental routing. Different feedback per stage.

**Estimated Time:** 4-5 hours

### Changes:

**New file:** `shared/stage_router.py`
- Define 6 stages (A-F) with age ranges
- `get_stage_for_age()` function

**New file:** `shared/babble_analyzer.py`
- `BABBLE_TYPES` dict (canonical, vowel_play, responsive, proto_word)
- `analyze_babble()` function

**File:** `lambdas/insight_generator/handler.py`
- Add stage-based routing logic
- Call babble analyzer for Stage C-D

**File:** `lambdas/feedback_processor/handler.py`
- Add `_get_feedback_schema_for_stage()`
- Stage-aware feedback validation

**File:** `shared/cry_analyzer.py`
- Add `MULTI_SIGNAL_HEADLINES` dict

### Testing Checklist:
- [ ] All 6 stages route correctly
- [ ] Babble insights appear for 6-12 month babies
- [ ] Multi-signal sessions (cry+babble) handled
- [ ] Feedback forms match stage

---

## PHASE 7: Age Variants in Display Text

**Goal:** Age-appropriate display text for each emotion across all stages.

**Estimated Time:** 2-3 hours

### Changes:

**File:** `shared/cry_analyzer.py`
- Extend `EMOTIONS` dict with `variants` sub-dict
- Add variants: 0_90, 91_180, 181_365, 366_730
- Update `analyze_cry()` to pick age-appropriate variant

### Testing Checklist:
- [ ] Each age range gets correct text variant
- [ ] 0-90 day text unchanged
- [ ] Dunstan labels fade after day 90
- [ ] All 7 emotions have all 4 variants

---

## PHASE 8: Trusted Parent System

**Goal:** Track parent feedback consistency. Weight training samples by trust.

**Estimated Time:** 2-3 hours

### Changes:

**New file:** `shared/trust_scorer.py`
- `calculate_trust_update()` function

**File:** `lambdas/feedback_processor/handler.py`
- Calculate trust update after feedback
- Update parent profile trust_score

**File:** `lambdas/model_trainer/handler.py`
- Load trust_score for each sample
- Calculate sample_weight = trust × quality × confirmation_weight
- Use weighted loss in training

### Testing Checklist:
- [ ] Trust scores update correctly
- [ ] High-trust parents get higher weight
- [ ] Rubber-stamping decreases trust
- [ ] Training uses weights

---

## PHASE 9: Babble Model Training Pipeline

**Goal:** Separate babble classifier training parallel to cry pipeline.

**Estimated Time:** 3-4 hours

### Changes:

**New file:** `shared/babble_classifier.py`
- `BABBLE_CLASSES` = ["canonical", "vowel_play", "responsive", "proto_word"]
- `predict_babble_type()` function

**File:** `lambdas/model_trainer/handler.py`
- Add communication_stage parameter handling
- Train babble models separately from cry models

**File:** `lambdas/training_check/handler.py`
- Check both cry and babble buckets
- Trigger separate training runs

### Testing Checklist:
- [ ] Babble samples train separately from cry
- [ ] Babble classifier predictions work
- [ ] Language_region routing (universal vs regional)
- [ ] 6-9 month babies get babble insights

---

## PHASE 10: Radar Chart Evolution

**Goal:** Stage-appropriate dimensions in radar charts.

**Estimated Time:** 2-3 hours

### Changes:

**File:** `lambdas/insight_generator/handler.py`
- Define `RADAR_DIMENSIONS_BY_STAGE` dict
- Compute new dimensions: canonical_babble_ratio, vowel_diversity, turn_taking, proto_word_count
- Update radar normalization with age-appropriate ranges

### Testing Checklist:
- [ ] Radar shows correct dimensions per stage
- [ ] Normalization with population ranges works
- [ ] Smooth transitions between stages

---

## PHASE 11: Backfill Existing Data

**Goal:** Retroactively populate age_bucket fields for existing records.

**Estimated Time:** 1 hour

### Changes:

**New file:** `scripts/backfill_age_buckets.py`
- Scan all TrainingFeatures records
- Calculate and add age buckets
- Update records in batches

### Testing Checklist:
- [ ] All records have bucket fields
- [ ] GSI queries work on backfilled data
- [ ] Training can use historical data

---

## Total Estimated Time: ~37 hours across 11 phases

## Current Status: Phase 0 - Ready to Begin

## Next Steps:
1. Start with Bug 1: DEVELOPMENTAL_STAGE_MAP
2. Fix bugs sequentially
3. Test after each bug fix
4. Verify 0-3 month output unchanged after all fixes
5. Move to Phase 1

---

## Notes:
- Each phase is independently deployable
- No phase breaks previous phases
- 0-3 month quality preserved throughout
- All changes are backward compatible
