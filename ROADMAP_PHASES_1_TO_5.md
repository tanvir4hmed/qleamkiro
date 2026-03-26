# QLEAM Implementation Roadmap - Phases 1-5

## PHASE 1: Schema Foundation (1-2 hours)

### Goal
Add all new database fields and tables. Populate new fields in code. No logic changes.

### Database Changes

#### 1.1 ChildProfile Table - Add Fields
```
- language_region (String) - default: "en"
- trust_score (Number) - default: 0.5
```

#### 1.2 TrainingFeatures Table - Add Fields
```
- age_day_bucket (Number) - exact age in days
- age_week_bucket (Number) - week number (age_days // 7 + 1)
- age_slot_bucket (String) - "A" through "F"
- communication_stage (String) - "cry", "babble", "word", "laugh"
- language_region (String) - from parent profile
- flagged_for_training (Boolean) - explicit flag
```

#### 1.3 TrainingFeatures - Add GSI
```
Name: age_day_bucket-stage-index
Partition Key: age_day_bucket (Number)
Sort Key: communication_stage (String)
Projection: ALL
```

#### 1.4 Create BabyDailyAtlas Table
```
Table Name: {environment}-BabyDailyAtlas
Partition Key: age_day (Number)
Sort Key: feature_key (String)

Attributes:
- centroid (Number)
- std_dev (Number)
- min_observed (Number)
- max_observed (Number)
- p10 (Number)
- p90 (Number)
- sample_count (Number)
- last_updated (String)
```


#### 1.5 Create BabyTrajectory Table
```
Table Name: {environment}-BabyTrajectory
Partition Key: child_id (String)
Sort Key: session_date (String, ISO format)

Attributes:
- age_days (Number)
- acoustic_snapshot (Map) - feature_key → value
- deviation_from_population (Map) - feature_key → z_score
- communication_stage (String)
- proto_words (List) - [{sound_pattern, parent_label, first_seen, count}]
- personal_baseline (Map) - feature_key → rolling_mean
```

#### 1.6 ModelVersions Table - Add Fields
```
- age_bucket_type (String) - "day", "week", "slot", "global"
- age_bucket_value (String) - "31", "5", "A", "global"
- communication_stage (String) - "cry", "babble", "word"
- language_region (String) - "universal", "en", "zh", etc.

Composite key pattern: model_type#age_bucket_type#age_bucket_value#stage#language
```

### Code Changes

#### File: shared/constants.py
Add table name constants:
```python
BABY_DAILY_ATLAS_TABLE = os.environ.get("BABY_DAILY_ATLAS_TABLE", "qleam-dev-BabyDailyAtlas")
BABY_TRAJECTORY_TABLE = os.environ.get("BABY_TRAJECTORY_TABLE", "qleam-dev-BabyTrajectory")
```

