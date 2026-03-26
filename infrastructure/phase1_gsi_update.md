# Phase 1: TrainingFeatures Table GSI Update

## New GSI Required

### GSI Name: `age_day_bucket-stage-index`

**Purpose:** Enable efficient per-age-day per-stage training queries

**Configuration:**
- Partition Key: `age_day_bucket` (Number)
- Sort Key: `communication_stage` (String)
- Projection Type: ALL
- Billing Mode: PAY_PER_REQUEST (same as base table)

### Terraform Configuration

Add to existing TrainingFeatures table resource:

```hcl
resource "aws_dynamodb_table" "training_features" {
  # ... existing configuration ...

  # Add new attributes for GSI
  attribute {
    name = "age_day_bucket"
    type = "N"
  }

  attribute {
    name = "communication_stage"
    type = "S"
  }

  # Add new GSI
  global_secondary_index {
    name            = "age_day_bucket-stage-index"
    hash_key        = "age_day_bucket"
    range_key       = "communication_stage"
    projection_type = "ALL"
  }
}
```

### Query Examples

**Query all cry samples for day 31:**
```python
response = table.query(
    IndexName="age_day_bucket-stage-index",
    KeyConditionExpression=Key("age_day_bucket").eq(31) & Key("communication_stage").eq("cry")
)
```

**Query all babble samples for day 200:**
```python
response = table.query(
    IndexName="age_day_bucket-stage-index",
    KeyConditionExpression=Key("age_day_bucket").eq(200) & Key("communication_stage").eq("babble")
)
```

### Migration Notes

1. GSI creation is non-blocking but takes time to backfill
2. Existing records without age_day_bucket will not appear in GSI until updated
3. New records will automatically populate the GSI
4. Phase 11 backfill script will update all existing records

### Cost Impact

- GSI uses same billing mode as base table (PAY_PER_REQUEST)
- No additional cost for storage (ALL projection)
- Query cost same as base table queries
- Backfill is one-time operation
