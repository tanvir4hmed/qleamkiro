# Phase 5 Complete: Individual Baby Trajectory

**Status**: ✅ COMPLETE  
**Date**: Continued from Phase 4  
**Duration**: ~2.5 hours

## Overview

Phase 5 implements the BabyTrajectory system that tracks each baby's personal acoustic history and baseline patterns. This enables detecting deviations from the baby's own norm, not just population norms.

## What Was Implemented

### 1. Trajectory Tracker Module (shared/trajectory_tracker.py)

New module with complete trajectory tracking functionality:

**Core Functions:**
- `update_baby_trajectory()` - Stores acoustic snapshot for each session
- `get_personal_context()` - Compares current session to baby's baseline
- `get_trajectory_summary()` - Gets full history for visualization

**Key Features:**
- Personal baseline calculation from last 20 sessions
- Deviation detection (how different from baby's usual patterns)
- Trend analysis (improving/stable/regressing)
- Regression alerts (> 2 std devs from personal baseline)
- Personal vs population comparison
- Requires 3+ sessions to establish baseline

**BabyTrajectory Schema:**
```python
{
  "child_id": "abc123",                    # PK
  "session_date": "2026-03-26T15:30:22Z",  # SK (ISO format for sorting)
  "age_days": 45,
  "communication_stage": "A",
  "sound_type": "cry",
  "acoustic_snapshot": {
    "f0_mean": 385.0,
    "rms_mean": 0.075,
    "spectral_centroid": 2800.0,
    ...
  },
  "created_at": "2026-03-26T15:30:22Z"
}
```

### 2. Personal Baseline Calculation

Calculates baby's typical values from recent history:

```python
def _calculate_personal_baseline(history_items):
    # Collect last 20 sessions
    # Calculate mean, std, min, max per feature
    
    baseline = {
        "f0_mean": {
            "mean": 385.0,      # Baby's typical pitch
            "std": 12.5,        # Baby's pitch variability
            "min": 360.0,
            "max": 410.0,
            "count": 15
        },
        ...
    }
    return baseline
```

### 3. Deviation Detection

Compares current session to personal baseline:

```python
# Current session: f0_mean = 420.0
# Personal baseline: mean = 385.0, std = 12.5

deviation_z = (420.0 - 385.0) / 12.5 = 2.8

# Thresholds:
# > 1.5 std devs = significant deviation
# > 2.0 std devs = regression flag (potential issue)
```

### 4. Trend Analysis

Determines developmental trend from recent history:

```python
def _determine_trend(history_items, current_age):
    # Look at last 10 sessions
    # f0_instability should decrease with age (improving)
    # voiced_fraction should increase with age (improving)
    
    # Calculate correlation with age
    instability_corr = -0.45  # Negative = good (decreasing)
    voiced_corr = 0.38        # Positive = good (increasing)
    
    trend_score = -instability_corr + voiced_corr = 0.83
    
    if trend_score > 0.3:
        return "improving"
    elif trend_score < -0.3:
        return "regressing"
    else:
        return "stable"
```

### 5. Feature Extraction Update (lambdas/feature_extraction/handler.py)

Added trajectory update call after atlas update:

```python
# --- Phase 5: Update individual baby trajectory ---
if child_id and age_days is not None and not is_adult and sound_type in ("cry", "speech", "laugh", "mixed"):
    try:
        from trajectory_tracker import update_baby_trajectory
        from constants import DEVELOPMENTAL_STAGE_MAP
        
        communication_stage = DEVELOPMENTAL_STAGE_MAP.get(age_days, "A")
        
        update_baby_trajectory(
            child_id=child_id,
            age_days=age_days,
            sound_features=sound_features_for_trajectory,
            sound_type=sound_type,
            communication_stage=communication_stage,
        )
    except Exception as e:
        logger.warning(f"Trajectory update failed (non-fatal): {e}")
```

### 6. Insight Generator Update (lambdas/insight_generator/handler.py)

Added personal context to insights:

```python
# --- Phase 5: Add personal context ---
if event.get("child_id") and age_days is not None and not is_adult and sound_type in ("cry", "mixed"):
    try:
        from trajectory_tracker import get_personal_context
        personal_context = get_personal_context(
            child_id=event["child_id"],
            age_days=age_days,
            sound_features=sound_features,
            population_context=population_context,
        )
        if personal_context.get("has_personal_history"):
            insight["personal_context"] = personal_context
            logger.info(f"Added personal context for child {event['child_id']}")
    except Exception as e:
        logger.warning(f"Failed to get personal context: {e}")
```

## Personal Context Output

**Example 1: Normal Session (Within Baseline)**
```json
{
  "personal_context": {
    "has_personal_history": true,
    "sessions_count": 15,
    "baseline": {
      "f0_mean": {"mean": 385.0, "std": 12.5, "count": 15},
      "rms_mean": {"mean": 0.075, "std": 0.008, "count": 15}
    },
    "deviations": {
      "f0_mean": {
        "current": 390.0,
        "baseline_mean": 385.0,
        "baseline_std": 12.5,
        "deviation_z": 0.4,
        "is_significant": false,
        "direction": "typical"
      }
    },
    "significant_deviations": [],
    "regression_flags": [],
    "trend": "stable",
    "personal_vs_population": {
      "f0_mean": {
        "personal_mean": 385.0,
        "population_mean": 380.5,
        "personal_percentile": 58,
        "interpretation": "slightly_above_average"
      }
    }
  }
}
```

**Example 2: Significant Deviation (Unusual for This Baby)**
```json
{
  "personal_context": {
    "has_personal_history": true,
    "sessions_count": 15,
    "deviations": {
      "f0_mean": {
        "current": 450.0,
        "baseline_mean": 385.0,
        "baseline_std": 12.5,
        "deviation_z": 5.2,
        "is_significant": true,
        "direction": "higher"
      },
      "rms_mean": {
        "current": 0.12,
        "baseline_mean": 0.075,
        "baseline_std": 0.008,
        "deviation_z": 5.6,
        "is_significant": true,
        "direction": "higher"
      }
    },
    "significant_deviations": ["f0_mean", "rms_mean"],
    "regression_flags": [
      {
        "feature": "f0_mean",
        "deviation_z": 5.2,
        "message": "f0_mean is 5.2 std devs from personal baseline"
      },
      {
        "feature": "rms_mean",
        "deviation_z": 5.6,
        "message": "rms_mean is 5.6 std devs from personal baseline"
      }
    ],
    "trend": "regressing"
  }
}
```

**Example 3: Insufficient History (Building Baseline)**
```json
{
  "personal_context": {
    "has_personal_history": false,
    "sessions_count": 2,
    "message": "Building personal baseline (need 3+ sessions)"
  }
}
```

## Frontend Integration

The personal context enables powerful parent-facing features:

**1. Personal Deviation Alerts:**
```
⚠️ Unusual Pattern for Your Baby

Your baby's pitch (450 Hz) is much higher than their usual (385 Hz).

This is unusual for your baby specifically, even though it's within 
normal range for 45-day-olds in general.

Possible reasons:
- Increased distress or discomfort
- Illness or pain
- Environmental changes
- Growth spurt

Monitor for other changes and consult your pediatrician if concerned.
```

**2. Personal vs Population Comparison:**
```
Your Baby's Profile (Day 45)

Pitch:        385 Hz
  Personal:   Typical for your baby
  Population: 58th percentile (slightly above average)

Energy:       0.075
  Personal:   Typical for your baby
  Population: 48th percentile (average)

Your baby tends to have a slightly higher-pitched cry than average,
but this is normal for them.
```

**3. Developmental Trend:**
```
📈 Your Baby's Progress

Trend: Improving ✓

Over the last 15 sessions:
- Cry stability improving (less erratic)
- Voiced sounds increasing (more controlled)
- Duration patterns stabilizing

Your baby's vocal development is progressing well!
```

**4. Regression Detection:**
```
⚠️ Change Detected

Your baby's cry patterns have changed significantly from their 
usual baseline over the last 3 sessions.

Changes detected:
- Pitch: 15% higher than usual
- Energy: 20% higher than usual
- Stability: More erratic than usual

This could indicate:
- Discomfort or illness
- Teething
- Growth spurt
- Environmental stress

Recommendation: Monitor closely and consult your pediatrician if 
the pattern persists or worsens.
```

**5. Timeline Visualization:**
```
Your Baby's Acoustic Timeline

Day 30  ●────────────────────────────────
        Pitch: 375 Hz (typical)

Day 35  ●────────────────────────────────
        Pitch: 380 Hz (typical)

Day 40  ●────────────────────────────────
        Pitch: 385 Hz (typical)

Day 45  ●────────────────────────────────
        Pitch: 390 Hz (typical)

Day 50  ●────────────────────────────────⚠️
        Pitch: 450 Hz (UNUSUAL - 5.2σ above baseline)
```

## Use Cases

### Use Case 1: Illness Detection
```python
# Baby's baseline: f0_mean = 385 Hz, std = 12 Hz
# During illness: f0_mean = 460 Hz

deviation_z = (460 - 385) / 12 = 6.25

# Regression flag triggered
# Alert parent: "Your baby's cry is very different from usual"
# Suggest: "This could indicate illness or discomfort"
```

### Use Case 2: Normal Variation
```python
# Baby's baseline: f0_mean = 385 Hz, std = 12 Hz
# Current session: f0_mean = 395 Hz

deviation_z = (395 - 385) / 12 = 0.83

# No alert (within 1.5 std devs)
# Display: "Your baby's cry is typical for them today"
```

### Use Case 3: Developmental Progress
```python
# Sessions over 30 days:
# f0_instability: 0.25 → 0.22 → 0.20 → 0.18 → 0.16 (decreasing)
# voiced_fraction: 0.45 → 0.50 → 0.55 → 0.58 → 0.62 (increasing)

# Trend: "improving"
# Display: "Your baby's vocal control is improving!"
```

### Use Case 4: Personal vs Population
```python
# Baby's baseline: f0_mean = 420 Hz (personal 85th percentile)
# Population mean: 380 Hz

# Display: "Your baby naturally has a higher-pitched cry than most 
# babies this age, but this is normal for them."
```

## Performance Characteristics

**Trajectory Update:**
- Time: ~20-30ms per session (1 DynamoDB write)
- Cost: $0.0000125 per session (1 write × $1.25/million)
- Non-blocking: Runs after session save

**Personal Context Query:**
- Time: ~40-60ms (1 DynamoDB query for last 20 sessions)
- Cost: $0.000025 per query (1 query × $0.25/million)
- Cached: Could cache per child for 5 minutes

**Storage:**
- Per session: ~500 bytes
- 100 sessions per baby = 50KB
- 10,000 babies × 100 sessions = 500MB
- Cost: $0.125/month ($0.25/GB-month)

## Data Quality Considerations

**Minimum History Threshold:**
- Requires 3+ sessions to establish baseline
- More sessions = more accurate baseline
- Recommends 10+ sessions for reliable trend analysis

**Outlier Handling:**
- Outliers included in baseline calculation
- Helps detect true personal variance vs measurement errors
- Regression flags help identify sudden changes

**Privacy:**
- Trajectory data linked to child_id (not anonymous)
- Only accessible by parent account
- Can be deleted on account deletion

## Testing Scenarios

### Test 1: First session (no history)
```python
update_baby_trajectory("child123", 45, features, "cry", "A")
# Creates first trajectory record

get_personal_context("child123", 45, features)
# Returns: {"has_personal_history": False, "sessions_count": 1}
```

### Test 2: Third session (baseline established)
```python
# After 3 sessions
get_personal_context("child123", 45, features)
# Returns baseline with mean/std for each feature
```

### Test 3: Normal session (within baseline)
```python
# Session 15: f0_mean = 390 (baseline: 385 ± 12)
get_personal_context("child123", 45, {"f0_mean": 390})
# Returns: deviation_z = 0.4, is_significant = False
```

### Test 4: Unusual session (deviation detected)
```python
# Session 16: f0_mean = 450 (baseline: 385 ± 12)
get_personal_context("child123", 45, {"f0_mean": 450})
# Returns: deviation_z = 5.4, is_significant = True, regression_flag
```

### Test 5: Trend analysis
```python
# After 10 sessions with improving patterns
get_personal_context("child123", 55, features)
# Returns: trend = "improving"
```

## Files Modified

1. `shared/trajectory_tracker.py` - NEW: Complete trajectory tracking
2. `lambdas/feature_extraction/handler.py` - Added trajectory update call
3. `lambdas/insight_generator/handler.py` - Added personal context to insights

## Next Steps: Phase 6

Phase 6 will implement Stage-Aware Routing & Babble Analysis:
1. Create `shared/stage_router.py` - Define 6 developmental stages
2. Create `shared/babble_analyzer.py` - Analyze babble types (canonical, vowel play, proto-words)
3. Update `lambdas/insight_generator/handler.py` - Stage-based routing
4. Update `lambdas/feedback_processor/handler.py` - Stage-aware feedback schemas
5. Add multi-signal headlines for cry+babble sessions

## Critical Insights

**Personal vs Population:**
- Population context: "Where does this baby sit among all babies?"
- Personal context: "Is this normal for THIS baby?"
- Both are valuable and complementary

**Example:**
```
Baby A: f0_mean = 420 Hz
  Population: 85th percentile (high)
  Personal: Typical (this baby is naturally high-pitched)
  
Baby B: f0_mean = 420 Hz
  Population: 85th percentile (high)
  Personal: 5.2σ above baseline (UNUSUAL for this baby)
  → Alert: Something changed!
```

**Regression Detection:**
- Sudden changes from personal baseline may indicate:
  - Illness or pain
  - Developmental regression
  - Environmental stress
  - Teething
  - Growth spurts

**Trend Analysis:**
- "Improving" = vocal control developing normally
- "Stable" = consistent patterns (normal)
- "Regressing" = patterns becoming less controlled (investigate)

## Critical Preservation

✅ **Privacy maintained**: Trajectory linked to child_id, parent-accessible only  
✅ **Non-blocking**: Trajectory updates don't delay session processing  
✅ **Graceful degradation**: Missing trajectory data doesn't break insights  
✅ **Minimum threshold**: Requires 3+ sessions before showing personal context

---

**Phase 5 Duration**: ~2.5 hours  
**Phase 5 Status**: ✅ COMPLETE  
**Ready for**: Phase 6 (Stage-Aware Routing & Babble Analysis)

**Total Progress**: 5/11 phases complete (~45% done)
