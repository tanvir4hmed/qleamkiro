# Phase 1: Pipeline Cleanup & Early Rejection (GATE)

## Goal
Fast, clean pipeline. Remove ~3000 lines of dead code. Early reject non-baby sounds in <2s. This phase touches NO ML — just cleaning and gating.

## Current Flow (slow, redundant)
```
Audio Upload -> feature_extraction Lambda (13-25s for everything)
  -> download audio
  -> quality gate
  -> diarization (F0 computed)
  -> sound classification (F0 computed again)
  -> rich features (F0 computed again)
  -> age classification (F0 from rich_features)
  -> biological validation
  -> adult detection (3 separate mechanisms)
  -> ALL results passed to insight_generator
  -> Even silence takes 13-25 seconds
```

## Target Flow (fast, gated)
```
Audio Upload -> feature_extraction Lambda
  -> download audio
  -> quality gate (duration, SNR) -----> REJECT if bad quality (<1s)
  -> quick classify (lightweight)  -----> REJECT if silence/noise (<2s)
  -> adult detection (single pass) -----> REJECT if adult only (<2s)
  -> [ONLY for baby sounds]:
     -> full feature extraction (F0 once, RMS once)
     -> sound type classification
     -> pass to insight_generator (temporary — replaced by HuBERT in Phase 2)
```

Note: After Phase 1, the pipeline still uses the current rule-based scoring for cry analysis. Phase 2+ replaces that with HuBERT + trained classifier. Phase 1 is purely about cleaning and speed.

## Tasks

### 1.1 Delete Dead Code
- Delete `shared/evidence_model.py` (~870 lines)
- Delete `shared/training_model.py`
- Delete `shared/federated_learning.py`
- Delete `shared/intent_taxonomy.py`
- Delete `shared/speaker_identity.py`
- Delete `lambdas/federated_aggregator/` (entire directory)
- Investigate & potentially delete `lambdas/cluster_engine/`, `lambdas/reinforcement_engine/`
- Delete `frontend/src/components/FeatureChart.js`
- Remove any imports of deleted modules
- Remove FeatureChart from any parent components
- Update Terraform to remove Lambda definitions for deleted handlers

### 1.2 Consolidate Redundant Computation
- Create single `compute_core_features(y, sr)` function that computes F0, RMS, spectral features ONCE
- All downstream consumers (sound_classifier, age_classifier, cry_analyzer) receive pre-computed features
- Remove duplicate F0/RMS computation from diarization.py, sound_classifier.py, rich_features.py

### 1.3 Implement Early Rejection Gate
- After quality_gate passes, run lightweight energy-based check:
  - If RMS < silence threshold across 80%+ of frames -> return `{status: "silence", fast_reject: true}`
  - If no voiced frames detected -> return `{status: "noise", fast_reject: true}`
- Quick adult check using F0 range (computed once):
  - If F0 median < 200Hz and no high-F0 segments -> flag as adult-only
- These checks should complete in <2s
- Only proceed to full analysis if baby sound likely

### 1.4 Simplify feature_extraction Lambda
- Restructure handler.py flow:
  1. Download & load audio
  2. Quality gate -> fast fail
  3. Core features (F0, RMS, spectral) -> compute ONCE
  4. Quick reject check (silence/noise/adult-only) -> fast fail
  5. Full classification + baby-specific features -> pass to insight_generator
- Remove MAX_SUPPORTED_CHILD_AGE_DAYS = 90 hard cap (we support 0-24m now)

### 1.5 Clean Up Constants
- Remove unused constants from `shared/constants.py`
- Remove evidence_model related constants
- Remove federated learning constants
- Keep active pipeline constants

## Files Changed
- DELETE: 5 shared modules, 1-3 Lambda dirs, 1 frontend component
- MODIFY: feature_extraction/handler.py, sound_classifier.py, constants.py
- CREATE: shared/core_features.py (single computation point)

## Infrastructure Changes (Terraform)
- Remove Lambda definitions for deleted handlers (federated_aggregator, cluster_engine, reinforcement_engine)
- No new AWS resources needed

## Success Criteria
- Silence/noise/adult rejected in <2s
- No dead imports or unused modules
- F0 computed exactly 1 time per session
- RMS computed exactly 1 time per session
- All existing tests still pass (after updating imports)
- Pipeline still works end-to-end (using old rule-based scoring temporarily)

## Deploy
- Workflows: `2-lambda-deploy` (shared + lambdas changed)
- Frontend: `3-frontend-deploy` (FeatureChart removed)
- If Terraform Lambda definitions removed: `1-infra-deploy` first
