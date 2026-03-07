# Phase 6: Child Deletion & Data Privacy

## Goal
Full GDPR/COPPA compliance. When parent deletes a child, all PII-linked data is removed. Anonymized training data stays.

## Data Map

| Data | Where Stored | Contains PII | On Child Delete |
|---|---|---|---|
| Child profile | DynamoDB Children table | Yes (name, birth_date) | DELETE |
| Session records | DynamoDB Sessions table | Yes (child_id) | DELETE |
| Raw audio files | S3 audio bucket | Yes (child voice = biometric) | DELETE |
| Feedback records | DynamoDB Feedback table | Yes (child_id, session_id) | DELETE |
| Training candidates | DynamoDB TrainingCandidate | Yes (child_id) | DELETE |
| Per-child embeddings | DynamoDB ChildEmbeddings | Yes (child_id) | DELETE |
| Session HuBERT embeddings | S3 (linked to session_id) | Yes (session_id) | DELETE |
| Anonymized training features | DynamoDB training_features + S3 | No (stripped at ingest) | KEEP |
| Trained model | S3 models/ | No (aggregated weights) | KEEP |

## Deletion Flow

```
Parent taps "Delete Child"
        |
  [Confirmation dialog]
  "This will permanently delete all of [name]'s
   recordings and analysis history. This cannot
   be undone. Your child's data has already been
   anonymized for model improvement — no personal
   information is retained in training data."
        |
  [API: DELETE /child/{child_id}]
        |
  [api_handler Lambda]
        |
  Step 1: Query all session_ids for child_id
  Step 2: For each session:
    - Delete S3 audio file (s3://bucket/audio/{session_id}.*)
    - Delete S3 per-child embeddings (if any)
    - Delete DynamoDB session record
    - Delete DynamoDB feedback records
    - Delete DynamoDB training_candidate records
  Step 3: Delete child profile from Children table
  Step 4: Delete per-child embeddings from ChildEmbeddings table
  Step 5: Clear localStorage cache on frontend (qleam_children)
  Step 6: Return success
        |
  [Frontend navigates to dashboard]
```

## Implementation

### Backend: api_handler Lambda

```python
def delete_child(child_id, user_id):
    """Delete all PII-linked data for a child."""
    # Verify ownership
    child = children_table.get_item(Key={"child_id": child_id})
    if child["user_id"] != user_id:
        raise PermissionError("Not your child")

    # Get all sessions
    sessions = sessions_table.query(
        IndexName="child_id-index",
        KeyConditionExpression=Key("child_id").eq(child_id)
    )

    for session in sessions["Items"]:
        sid = session["session_id"]
        # Delete audio from S3
        s3.delete_object(Bucket=AUDIO_BUCKET, Key=f"audio/{sid}.wav")
        s3.delete_object(Bucket=AUDIO_BUCKET, Key=f"audio/{sid}.m4a")
        # Delete session record
        sessions_table.delete_item(Key={"session_id": sid})
        # Delete feedback
        feedback_table.delete_item(Key={"session_id": sid})
        # Delete training candidates (PII-linked)
        training_candidates_table.delete_item(Key={"session_id": sid})

    # Delete per-child embeddings
    child_embeddings = embeddings_table.query(
        KeyConditionExpression=Key("child_id").eq(child_id)
    )
    for emb in child_embeddings["Items"]:
        embeddings_table.delete_item(Key={"child_id": child_id, "embedding_id": emb["embedding_id"]})

    # Delete child profile
    children_table.delete_item(Key={"child_id": child_id})

    return {"deleted": True, "sessions_removed": len(sessions["Items"])}
```

### Frontend: Delete Child UI

In child profile / settings:
```
[Delete Child Profile]
  -> Modal: "Delete [name]'s profile?"
  -> "This permanently removes all recordings, analysis history,
      and session data for [name]. Anonymized training data
      (which contains no personal information) will be retained
      to improve the service."
  -> [Cancel] [Delete Permanently]
  -> On confirm: call API, clear localStorage, navigate to dashboard
```

### S3 Lifecycle (Belt + Suspenders)
Even without explicit deletion, set S3 lifecycle rules:
- Audio files older than 90 days -> move to Glacier
- Audio files older than 365 days -> delete
- This catches any missed deletions

## Tasks

### 6.1 Add DELETE /child/{child_id} API Endpoint
- Verify ownership (user_id matches)
- Cascade delete all linked data
- Return count of deleted items

### 6.2 Frontend Delete Child UI
- Add delete button to child profile page
- Confirmation modal with clear messaging
- Clear localStorage after deletion
- Navigate to dashboard

### 6.3 S3 Lifecycle Rules
- Terraform: add lifecycle rules to audio bucket
- 90 days -> Glacier transition
- 365 days -> expiration

### 6.4 Audit Trail
- Log deletion events to CloudWatch
- Include: user_id, child_id, sessions_deleted count, timestamp
- Do NOT log child name or any PII in logs

### 6.5 Test Deletion Completeness
- Create test child with sessions, feedback, training candidates
- Delete child
- Verify: no S3 objects, no DynamoDB records, no orphaned data
- Verify: anonymized training_features table unchanged

## Infrastructure (Terraform)

```hcl
# S3 lifecycle rules
resource "aws_s3_bucket_lifecycle_configuration" "audio_lifecycle" {
  bucket = aws_s3_bucket.audio.id

  rule {
    id     = "archive-old-audio"
    status = "Enabled"
    filter {
      prefix = "audio/"
    }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
    expiration {
      days = 365
    }
  }
}
```

## Success Criteria
- Deleting a child removes ALL PII-linked data (audio, sessions, feedback, candidates, embeddings)
- Anonymized training_features table is untouched by deletion
- S3 lifecycle provides safety net for missed deletions
- Frontend shows clear, honest messaging about what's deleted vs retained
- Deletion is logged (without PII) for audit

## Deploy
- Workflows: `1-infra-deploy` (S3 lifecycle) then `2-lambda-deploy` (API endpoint) then `3-frontend-deploy` (delete UI)
