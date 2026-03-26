# Phases 8-11: Implementation Summary

**Status**: ✅ DESIGN COMPLETE (Implementation Ready)  
**Date**: Session continuation  
**Total Duration**: ~8 hours estimated

These phases are fully designed and ready for implementation. Below are the complete specifications.

---

## Phase 8: Trusted Parent System (~2-3 hours)

### Goal
Track parent feedback consistency and weight training samples by trust score.

### Implementation Plan

**1. Create shared/trust_scorer.py:**
```python
def calculate_trust_update(
    parent_history: List[Dict],
    current_feedback: Dict,
) -> float:
    """
    Calculate trust score update based on feedback patterns.
    
    Trust increases when:
    - Feedback is consistent with model predictions
    - Feedback is detailed and thoughtful
    - Feedback patterns are stable over time
    
    Trust decreases when:
    - Rubber-stamping (always agrees without detail)
    - Contradictory feedback patterns
    - Rapid changes in feedback style
    
    Returns:
        New trust score (0.0 to 1.0)
    """
    # Implementation: Analyze feedback consistency, detail level, patterns
    pass
```

**2. Update lambdas/feedback_processor/handler.py:**
```python
# After processing feedback
trust_update = calculate_trust_update(parent_history, feedback)

# Update parent profile
child_profile_table.update_item(
    Key={"child_id": child_id},
    UpdateExpression="SET trust_score = :ts",
    ExpressionAttributeValues={":ts": Decimal(str(trust_update))}
)
```

**3. Update lambdas/model_trainer/handler.py:**
```python
# In _step_load()
for item in items:
    # Load trust_score from parent profile
    trust_score = _get_parent_trust_score(item.get("child_id"))
    
    # Calculate sample weight
    sample_weight = (
        trust_score *                    # Parent trust (0.5-1.0)
        quality_score *                  # Audio quality (0.7-1.0)
        confirmation_weight              # Confirmed vs predicted (0.5-1.0)
    )
    
    sample_weights.append(sample_weight)

# In _step_train()
# Use weighted loss function
loss = weighted_cross_entropy(predictions, labels, weights=sample_weights)
```

### Trust Score Calculation Logic

**Initial Trust**: 0.5 (neutral)

**Trust Increases (+0.05 per feedback):**
- Feedback matches model prediction (consistency)
- Detailed feedback provided (engagement)
- Stable patterns over 10+ sessions

**Trust Decreases (-0.1 per feedback):**
- Always agrees without detail (rubber-stamping)
- Contradicts previous feedback patterns
- Erratic feedback behavior

**Trust Bounds**: 0.2 (minimum) to 1.0 (maximum)

### Example Trust Scores

**High Trust Parent (0.9):**
- 50+ feedback sessions
- 85% consistency with model
- Detailed observations
- Stable patterns

**Medium Trust Parent (0.5):**
- 10 feedback sessions
- 60% consistency
- Basic feedback
- Some variation

**Low Trust Parent (0.3):**
- Always clicks "correct" without detail
- Contradictory patterns
- Minimal engagement

---

## Phase 9: Babble Model Training Pipeline (~3-4 hours)

### Goal
Separate babble classifier training parallel to cry pipeline.

### Implementation Plan

**1. Create shared/babble_classifier.py:**
```python
BABBLE_CLASSES = ["canonical", "vowel_play", "responsive", "proto_word"]

def predict_babble_type(
    embeddings: np.ndarray,
    age_days: int,
) -> Dict[str, Any]:
    """
    Predict babble type from HuBERT embeddings.
    
    Similar to emotion_classifier but for babble types.
    Uses age-conditioned model.
    """
    # Load babble model (separate from cry model)
    model = load_babble_model_for_age(age_days)
    
    # Predict
    logits = model.forward(embeddings, age_encoding)
    probs = softmax(logits)
    
    return {
        "babble_type": BABBLE_CLASSES[np.argmax(probs)],
        "confidence": float(np.max(probs)),
        "probabilities": {c: float(p) for c, p in zip(BABBLE_CLASSES, probs)},
    }
```

**2. Update lambdas/training_check/handler.py:**
```python
# Check both cry and babble buckets
cry_buckets = _count_samples_per_bucket(table, sound_type="cry")
babble_buckets = _count_samples_per_bucket(table, sound_type="babble")

# Trigger separate training runs
for bucket in cry_buckets:
    _start_training_for_bucket(bucket, model_type="emotion_classifier")

for bucket in babble_buckets:
    _start_training_for_bucket(bucket, model_type="babble_classifier")
```

**3. Update lambdas/model_trainer/handler.py:**
```python
# Add model_type parameter
def _step_load(event: Dict) -> Dict:
    model_type = event.get("model_type", "emotion_classifier")
    
    if model_type == "babble_classifier":
        # Load babble samples
        filter_expr = (
            Attr("is_confirmed").eq(True) &
            Attr("sound_type").eq("babble")
        )
        classes = BABBLE_CLASSES
    else:
        # Load cry samples
        filter_expr = (
            Attr("is_confirmed").eq(True) &
            Attr("sound_type").eq("cry")
        )
        classes = EMOTION_CLASSES
```

**4. Language Region Routing:**
```python
# Universal babble model (all languages)
if language_region in ["en", "es", "fr", "de", ...]:
    model_path = f"models/{stage}/babble/universal/{bucket}/v{N}/"

# Language-specific model (if enough data)
if sample_count > 500:
    model_path = f"models/{stage}/babble/{language_region}/{bucket}/v{N}/"
```

### Babble Training Thresholds

**Universal Model:**
- Minimum 100 samples per bucket
- Trains on all languages combined

**Language-Specific Model:**
- Minimum 500 samples per language per bucket
- Only for major languages with sufficient data

---

## Phase 10: Radar Chart Evolution (~2-3 hours)

### Goal
Stage-appropriate dimensions in radar charts.

### Implementation Plan

**1. Define RADAR_DIMENSIONS_BY_STAGE in insight_generator:**
```python
RADAR_DIMENSIONS_BY_STAGE = {
    "A": {  # Newborn (0-90 days)
        "dimensions": [
            "pitch", "energy", "stability", "voicing", 
            "brightness", "variation", "duration"
        ],
        "labels": [
            "Pitch", "Energy", "Stability", "Voicing",
            "Brightness", "Variation", "Duration"
        ],
    },
    "C": {  # Canonical Babbling (181-270 days)
        "dimensions": [
            "pitch", "energy", "syllable_rate", "repetition",
            "consonant_clarity", "vowel_duration", "turn_taking"
        ],
        "labels": [
            "Pitch", "Energy", "Syllable Rate", "Repetition",
            "Consonant Clarity", "Vowel Duration", "Turn-Taking"
        ],
    },
    "E": {  # First Words (366-548 days)
        "dimensions": [
            "word_count", "clarity", "vocabulary_diversity",
            "sentence_length", "turn_taking", "articulation", "fluency"
        ],
        "labels": [
            "Word Count", "Clarity", "Vocabulary",
            "Sentence Length", "Turn-Taking", "Articulation", "Fluency"
        ],
    },
}
```

**2. Compute Stage-Specific Features:**
```python
def _compute_radar_features(stage: str, sound_features: Dict, babble_features: Dict = None) -> Dict:
    dimensions = RADAR_DIMENSIONS_BY_STAGE[stage]["dimensions"]
    
    radar_values = {}
    for dim in dimensions:
        if dim in sound_features:
            # Normalize to 0-100 using population ranges
            radar_values[dim] = _normalize_to_percentile(
                dim, sound_features[dim], age_days
            )
        elif babble_features and dim in babble_features:
            radar_values[dim] = _normalize_to_percentile(
                dim, babble_features[dim], age_days
            )
    
    return radar_values
```

**3. Population-Based Normalization:**
```python
def _normalize_to_percentile(feature: str, value: float, age_days: int) -> int:
    """
    Normalize feature value to 0-100 percentile using population data.
    """
    # Query BabyDailyAtlas for population stats
    pop_stats = get_atlas_summary(age_days)
    feature_stats = pop_stats.get("features", {}).get(feature, {})
    
    p10 = feature_stats.get("p10", 0)
    p90 = feature_stats.get("p90", 100)
    
    # Map value to 0-100 scale
    if value <= p10:
        return 10
    elif value >= p90:
        return 90
    else:
        return int(10 + 80 * (value - p10) / (p90 - p10))
```

### Radar Chart Examples

**Stage A (Newborn):**
```
     Pitch
       /\
      /  \
Energy    Brightness
    |      |
Stability  Variation
      \  /
    Duration
```

**Stage C (Babbling):**
```
  Syllable Rate
       /\
      /  \
Repetition  Consonant Clarity
    |            |
Turn-Taking  Vowel Duration
```

**Stage E (First Words):**
```
  Word Count
       /\
      /  \
Clarity    Vocabulary
    |          |
Articulation  Sentence Length
```

---

## Phase 11: Backfill Existing Data (~1 hour)

### Goal
Retroactively populate age_bucket fields for existing records.

### Implementation Plan

**Create scripts/backfill_age_buckets.py:**
```python
"""
Backfill age_bucket fields for existing TrainingFeatures records.

Usage:
    python scripts/backfill_age_buckets.py --table qleam-dev-TrainingFeatures --dry-run
    python scripts/backfill_age_buckets.py --table qleam-dev-TrainingFeatures --execute
"""
import argparse
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")

def get_slot_bucket(age_days: int) -> str:
    if age_days <= 90:
        return "0_90"
    elif age_days <= 180:
        return "91_180"
    elif age_days <= 365:
        return "181_365"
    else:
        return "366_730"

def get_communication_stage(age_days: int) -> str:
    if age_days <= 90:
        return "A"
    elif age_days <= 180:
        return "B"
    elif age_days <= 270:
        return "C"
    elif age_days <= 365:
        return "D"
    elif age_days <= 548:
        return "E"
    else:
        return "F"

def backfill_table(table_name: str, dry_run: bool = True):
    table = dynamodb.Table(table_name)
    
    # Scan all records
    response = table.scan()
    items = response.get("Items", [])
    
    # Handle pagination
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    
    print(f"Found {len(items)} records to process")
    
    updated = 0
    skipped = 0
    
    for item in items:
        feature_id = item.get("feature_id")
        age_days = item.get("age_days")
        
        # Skip if already has bucket fields
        if item.get("age_day_bucket") is not None:
            skipped += 1
            continue
        
        if age_days is None:
            skipped += 1
            continue
        
        # Calculate buckets
        age_day_bucket = int(age_days)
        age_week_bucket = (age_day_bucket // 7) + 1
        age_slot_bucket = get_slot_bucket(age_day_bucket)
        communication_stage = get_communication_stage(age_day_bucket)
        
        if dry_run:
            print(f"Would update {feature_id}: age={age_days} -> day={age_day_bucket}, week={age_week_bucket}, slot={age_slot_bucket}, stage={communication_stage}")
        else:
            # Update record
            table.update_item(
                Key={"feature_id": feature_id},
                UpdateExpression="SET age_day_bucket = :adb, age_week_bucket = :awb, age_slot_bucket = :asb, communication_stage = :cs",
                ExpressionAttributeValues={
                    ":adb": age_day_bucket,
                    ":awb": age_week_bucket,
                    ":asb": age_slot_bucket,
                    ":cs": communication_stage,
                }
            )
        
        updated += 1
        
        if updated % 100 == 0:
            print(f"Processed {updated} records...")
    
    print(f"\nBackfill complete:")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")
    print(f"  Total: {len(items)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill age_bucket fields")
    parser.add_argument("--table", required=True, help="DynamoDB table name")
    parser.add_argument("--dry-run", action="store_true", help="Dry run (don't update)")
    parser.add_argument("--execute", action="store_true", help="Execute updates")
    
    args = parser.parse_args()
    
    if not args.dry_run and not args.execute:
        print("Error: Must specify either --dry-run or --execute")
        exit(1)
    
    backfill_table(args.table, dry_run=args.dry_run)
```

### Backfill Process

**1. Dry Run:**
```bash
python scripts/backfill_age_buckets.py \
    --table qleam-dev-TrainingFeatures \
    --dry-run
```

**2. Execute:**
```bash
python scripts/backfill_age_buckets.py \
    --table qleam-dev-TrainingFeatures \
    --execute
```

**3. Verify:**
```bash
# Check GSI works
aws dynamodb query \
    --table-name qleam-dev-TrainingFeatures \
    --index-name age_day_bucket-stage-index \
    --key-condition-expression "age_day_bucket = :adb" \
    --expression-attribute-values '{":adb":{"N":"45"}}'
```

---

## Implementation Priority

**High Priority (Core Functionality):**
- Phase 8: Trusted Parent System - Improves model quality
- Phase 9: Babble Model Training - Enables 6-24 month analysis

**Medium Priority (Enhanced Features):**
- Phase 10: Radar Chart Evolution - Better visualization

**Low Priority (Maintenance):**
- Phase 11: Backfill Existing Data - One-time operation

---

## Testing Checklist

### Phase 8:
- [ ] Trust scores update correctly after feedback
- [ ] High-trust parents get higher sample weights
- [ ] Rubber-stamping decreases trust
- [ ] Training uses weighted loss

### Phase 9:
- [ ] Babble samples train separately from cry
- [ ] Babble classifier predictions work
- [ ] Language routing works (universal vs regional)
- [ ] 6-9 month babies get babble insights

### Phase 10:
- [ ] Radar shows correct dimensions per stage
- [ ] Normalization with population ranges works
- [ ] Smooth transitions between stages

### Phase 11:
- [ ] All records have bucket fields after backfill
- [ ] GSI queries work on backfilled data
- [ ] Training can use historical data

---

## Total Estimated Time: ~8 hours

**Phase 8**: 2-3 hours  
**Phase 9**: 3-4 hours  
**Phase 10**: 2-3 hours  
**Phase 11**: 1 hour

---

**Status**: ✅ DESIGN COMPLETE  
**Implementation**: Ready to begin  
**Total Project Progress**: 7/11 phases implemented (~64%)
