# Dead Code Inventory

Modules and code that are never called from the active pipeline and should be removed in Phase 1.

## Fully Dead Modules (delete entirely)

### 1. shared/evidence_model.py (~870 lines)
- **What it does**: Three-source evidence blending (acoustic 60%, research 15%, feedback 25%)
- **Why dead**: Never called from insight_generator or any Lambda handler
- **Contains**: `determine_probable_intent_v2()`, hunger_discomfort_overlap resolver (135 lines for one pair), acoustic tiebreaker patches
- **Note**: Different intent taxonomy than cry_analyzer — was an abandoned parallel approach

### 2. shared/training_model.py
- **What it does**: Old training model (pre-cry_training_model.py)
- **Why dead**: Replaced by cry_training_model.py, never imported

### 3. shared/federated_learning.py
- **What it does**: Federated learning aggregation concept
- **Why dead**: Never implemented beyond skeleton, never called

### 4. shared/intent_taxonomy.py
- **What it does**: Intent label taxonomy mapping
- **Why dead**: constants.py has INTENT_LABELS, this is unused duplicate

### 5. shared/speaker_identity.py
- **What it does**: Speaker identification/voiceprint concept
- **Why dead**: Never integrated into pipeline, never called

## Dead Lambda Handlers (evaluate for removal)

### 6. lambdas/federated_aggregator/handler.py
- **What it does**: Federated learning aggregation Lambda
- **Why dead**: federated_learning.py is dead, this handler has no trigger

### 7. lambdas/cluster_engine/handler.py
- **Investigate**: Check if called from any Step Function or EventBridge rule

### 8. lambdas/reinforcement_engine/handler.py
- **Investigate**: Check if called from any Step Function or EventBridge rule

## Dead Frontend Components

### 9. frontend/src/components/FeatureChart.js (39 lines)
- **What it does**: Radar chart with 4 axes (Rhythm, Repetition, Intensity, Flow)
- **Why dead**: These 4 scores come from evidence_model.py which is never called
- **Shows**: Meaningless data — the features it displays are never populated
- **Action**: Remove component, replace with new meaningful charts in Phase 5

## Redundant Computation (fix in Phase 1)

### F0 (Fundamental Frequency) — computed 5 times:
1. `shared/audio_utils.py` — extract_all_features_from_array()
2. `shared/rich_features.py` — extract_rich_features() via YIN
3. `shared/diarization.py` — per-segment F0 classification
4. `shared/sound_classifier.py` — classify_sound()
5. `shared/age_classifier.py` — uses F0 from rich_features

**Fix**: Compute F0 once in feature_extraction Lambda, pass to all consumers.

### RMS (Root Mean Square Energy) — computed 4 times:
1. `shared/audio_utils.py`
2. `shared/rich_features.py`
3. `shared/sound_classifier.py`
4. `shared/diarization.py`

**Fix**: Compute once, pass through.

### Adult Detection — 3 mechanisms:
1. `shared/age_classifier.py` — probabilistic classification
2. `shared/diarization.py` — F0-based speaker labeling
3. `shared/sound_classifier.py` — adult voice scoring

**Fix**: Single adult detection pass using age_classifier, remove others.

## Summary

| Category | Lines to Remove | Files to Delete |
|---|---|---|
| Dead shared modules | ~2,500 | 5 files |
| Dead Lambda handlers | ~300-500 | 2-3 files |
| Dead frontend component | 39 | 1 file |
| **Total** | **~2,800-3,000** | **8-9 files** |
