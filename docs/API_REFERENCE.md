# Qleam MVP — API Reference

> Complete REST API documentation for the Qleam backend.  
> Base URL: `https://{api-id}.execute-api.us-east-1.amazonaws.com/{env}`

---

## Authentication

All endpoints require a valid **Cognito JWT ID Token** in the `Authorization` header.

```
Authorization: Bearer <cognito-id-token>
```

### Get a Token (CLI)

```bash
aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id YOUR_CLIENT_ID \
  --auth-parameters USERNAME=user@example.com,PASSWORD=YourPass123!
```

### Token Expiry

- ID Token expires in **1 hour**
- Use the Refresh Token to get a new ID Token via Amplify Auth or `initiate-auth` with `REFRESH_TOKEN_AUTH`

---

## Endpoints

### 1. Create Child Profile

```
POST /child
```

Creates a new child profile for the authenticated parent.

**Request Body**

```json
{
  "name": "Baby Emma"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Child's name (1–50 chars) |

**Response `201 Created`**

```json
{
  "child_id": "c_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Child profile created"
}
```

**Error Responses**

| Code | Reason |
|------|--------|
| `400` | Missing or invalid `name` field |
| `401` | Missing or invalid JWT token |
| `500` | Internal server error |

---

### 2. Delete Child Profile

```
DELETE /child/{child_id}
```

Deletes a child profile and all associated sessions, clusters, and feedback.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `child_id` | string | Child profile ID |

**Response `200 OK`**

```json
{
  "message": "Child profile deleted"
}
```

**Error Responses**

| Code | Reason |
|------|--------|
| `403` | Child does not belong to authenticated parent |
| `404` | Child not found |

---

### 3. List Sessions

```
GET /child/{child_id}/sessions
```

Returns all sessions for a child, sorted by timestamp descending.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `child_id` | string | Child profile ID |

**Query Parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | integer | 20 | Max sessions to return (1–100) |
| `last_key` | string | — | Pagination token from previous response |

**Response `200 OK`**

```json
{
  "sessions": [
    {
      "session_id": "s_abc123",
      "child_id": "c_abc123",
      "timestamp": "2026-02-18T15:30:00Z",
      "duration_seconds": 12.5,
      "processed": true,
      "deviation_level": "low",
      "deviation_flag": false,
      "feature_scores": {
        "rhythm": 0.72,
        "repetition": 0.58,
        "emotional_intensity": 0.45,
        "expressive_flow": 0.63
      },
      "insight_summary": {
        "probable_intent": {
          "key": "hunger",
          "label": "Hunger",
          "confidence": 0.68
        }
      }
    }
  ],
  "count": 1,
  "last_evaluated_key": null
}
```

---

### 4. Get Upload URL

```
POST /session/upload
```

Generates a presigned S3 URL for direct audio upload from the browser.

**Request Body**

```json
{
  "child_id": "c_abc123"
}
```

**Response `200 OK`**

```json
{
  "session_id": "s_xyz789",
  "upload_url": "https://qleam-dev-audio-storage.s3.amazonaws.com/audio/c_abc123/s_xyz789.wav?X-Amz-Signature=...",
  "expires_in": 300
}
```

**Upload the Audio**

```bash
curl -X PUT \
  -H "Content-Type: audio/wav" \
  --data-binary @recording.wav \
  "https://qleam-dev-audio-storage.s3.amazonaws.com/audio/..."
```

> ⚠️ The presigned URL expires in **5 minutes**. Upload immediately after receiving it.

---

### 5. Start Processing Pipeline

```
POST /session/{session_id}/start
```

Triggers the Step Functions audio processing pipeline for an uploaded session.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID from upload response |

**Request Body**

```json
{}
```

**Response `200 OK`**

```json
{
  "status": "processing",
  "execution_arn": "arn:aws:states:us-east-1:123456789:execution:qleam-dev-audio-pipeline:s_xyz789"
}
```

**Error Responses**

| Code | Reason |
|------|--------|
| `400` | Audio not yet uploaded to S3 |
| `409` | Session already processing or processed |

---

### 6. Get Session Insight

```
GET /session/{session_id}/insight
```

Returns the processing status and insight for a session.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID |

**Response `200 OK` — Processing**

```json
{
  "session_id": "s_xyz789",
  "status": "processing",
  "processed": false
}
```

**Response `200 OK` — Complete**

```json
{
  "session_id": "s_xyz789",
  "status": "complete",
  "processed": true,
  "timestamp": "2026-02-18T15:30:00Z",
  "duration_seconds": 12.5,
  "feature_scores": {
    "rhythm": 0.72,
    "repetition": 0.58,
    "emotional_intensity": 0.45,
    "expressive_flow": 0.63
  },
  "deviation_level": "low",
  "deviation_flag": false,
  "deviation_score": 0.18,
  "cluster_id": "cl_def456",
  "cluster_action": "attached",
  "insight": {
    "probable_intent": {
      "key": "hunger",
      "label": "Hunger",
      "confidence": 0.68
    },
    "suggested_response": "Your baby may be signaling hunger. Try offering a feeding and observe if the vocalization pattern settles.",
    "cluster_stability": "emerging",
    "readiness_score": 0.61,
    "language_maturity_level": "pre-linguistic",
    "semantic_alignment": 0.0,
    "disclaimer": "This is a behavioral pattern observation, not a medical diagnosis. Always consult a healthcare professional for medical concerns."
  }
}
```

**Insight Object Fields**

| Field | Type | Description |
|-------|------|-------------|
| `probable_intent.key` | string | Intent key: `hunger`, `connection`, `discomfort`, `overstimulation`, `fatigue`, `exploration`, `unknown` |
| `probable_intent.label` | string | Human-readable intent label |
| `probable_intent.confidence` | float | Confidence score 0.0–0.95 |
| `suggested_response` | string | Actionable suggestion for parent |
| `cluster_stability` | string | `forming` (1–2 sessions), `emerging` (3–9), `stable` (10+) |
| `readiness_score` | float | Language readiness composite 0.0–1.0 |
| `language_maturity_level` | string | `pre-linguistic`, `proto-linguistic`, `early-linguistic` |
| `semantic_alignment` | float | Word co-occurrence alignment score |
| `disclaimer` | string | Always present — non-diagnostic notice |

---

### 7. Submit Feedback

```
POST /session/{session_id}/feedback
```

Submits parent feedback on the suggested response. Triggers async reinforcement learning update.

**Path Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `session_id` | string | Session ID |

**Request Body**

```json
{
  "response_type": "hunger",
  "effectiveness": "helpful",
  "word_token": "mama"
}
```

| Field | Type | Required | Values |
|-------|------|----------|--------|
| `response_type` | string | ✅ | `hunger`, `connection`, `discomfort`, `overstimulation`, `fatigue`, `exploration` |
| `effectiveness` | string | ✅ | `helpful`, `neutral`, `ineffective` |
| `word_token` | string | ❌ | Any word the parent heard (lowercase) |

**Response `200 OK`**

```json
{
  "status": "feedback_processed",
  "feedback_id": "fb_ghi012",
  "reinforcement_triggered": true
}
```

**Reinforcement Effect**

| Effectiveness | Weight Change | Intent Change |
|--------------|---------------|---------------|
| `helpful` | +0.10 (max 1.0) | +0.10 for response_type |
| `neutral` | -0.02 (min 0.0) | No change |
| `ineffective` | -0.05 (min 0.0) | -0.05 for response_type |

---

## Error Response Format

All errors return a consistent JSON structure:

```json
{
  "error": "Error type",
  "message": "Human-readable description",
  "request_id": "abc123-def456"
}
```

**Standard HTTP Status Codes**

| Code | Meaning |
|------|---------|
| `200` | Success |
| `201` | Created |
| `400` | Bad Request — invalid input |
| `401` | Unauthorized — missing/invalid JWT |
| `403` | Forbidden — resource belongs to another user |
| `404` | Not Found |
| `409` | Conflict — duplicate or invalid state |
| `429` | Too Many Requests — rate limited |
| `500` | Internal Server Error |

---

## Rate Limits

| Endpoint | Limit |
|----------|-------|
| All endpoints | 100 req/min per user |
| `POST /session/upload` | 10 req/min per user |
| `POST /session/{id}/start` | 10 req/min per user |

---

## Data Types Reference

### Intent Keys

| Key | Label | Description |
|-----|-------|-------------|
| `hunger` | Hunger | Rhythmic, repetitive pattern — feeding signal |
| `connection` | Connection | Soft, melodic — seeking comfort or interaction |
| `discomfort` | Discomfort | High intensity, irregular — pain or discomfort |
| `overstimulation` | Overstimulation | Rapid, high-pitch — sensory overload |
| `fatigue` | Fatigue | Low energy, trailing — tiredness |
| `exploration` | Exploration | Varied, playful — vocal experimentation |
| `unknown` | Unknown | Insufficient data to classify |

### Deviation Levels

| Level | Threshold | Meaning |
|-------|-----------|---------|
| `none` | < 10% from baseline | Normal variation |
| `low` | 10–25% from baseline | Slight change |
| `moderate` | 25–50% from baseline | Notable change |
| `high` | > 50% from baseline | Significant deviation |

### Language Maturity Levels

| Level | Readiness Score | Description |
|-------|----------------|-------------|
| `pre-linguistic` | 0.0–0.4 | Early vocalization, no clear patterns |
| `proto-linguistic` | 0.4–0.7 | Emerging patterns, proto-words |
| `early-linguistic` | 0.7–1.0 | Clear patterns, possible word emergence |

---

## SDK / Client Usage Examples

### JavaScript (Fetch)

```javascript
const API_URL = process.env.REACT_APP_API_URL;

async function apiCall(path, options = {}) {
  const session = await Auth.currentSession();
  const token = session.getIdToken().getJwtToken();

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    },
  });

  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.message || `HTTP ${res.status}`);
  }
  return res.json();
}

// Create child
const { child_id } = await apiCall('/child', {
  method: 'POST',
  body: JSON.stringify({ name: 'Baby Emma' }),
});

// Get upload URL
const { session_id, upload_url } = await apiCall('/session/upload', {
  method: 'POST',
  body: JSON.stringify({ child_id }),
});

// Upload audio
await fetch(upload_url, {
  method: 'PUT',
  body: audioBlob,
  headers: { 'Content-Type': 'audio/wav' },
});

// Start pipeline
await apiCall(`/session/${session_id}/start`, { method: 'POST', body: '{}' });

// Poll for insight
const poll = async () => {
  const data = await apiCall(`/session/${session_id}/insight`);
  if (data.processed) return data;
  await new Promise(r => setTimeout(r, 3000));
  return poll();
};
const insight = await poll();
```

### Python (boto3 / requests)

```python
import requests
import boto3

def get_token(client_id, username, password):
    client = boto3.client('cognito-idp', region_name='us-east-1')
    resp = client.initiate_auth(
        AuthFlow='USER_PASSWORD_AUTH',
        ClientId=client_id,
        AuthParameters={'USERNAME': username, 'PASSWORD': password}
    )
    return resp['AuthenticationResult']['IdToken']

API_URL = 'https://xxx.execute-api.us-east-1.amazonaws.com/dev'
token = get_token(CLIENT_ID, 'user@example.com', 'Pass123!')
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Create child
r = requests.post(f'{API_URL}/child', json={'name': 'Baby Emma'}, headers=headers)
child_id = r.json()['child_id']

# Get upload URL
r = requests.post(f'{API_URL}/session/upload', json={'child_id': child_id}, headers=headers)
session_id = r.json()['session_id']
upload_url = r.json()['upload_url']

# Upload audio
with open('recording.wav', 'rb') as f:
    requests.put(upload_url, data=f, headers={'Content-Type': 'audio/wav'})

# Start pipeline
requests.post(f'{API_URL}/session/{session_id}/start', json={}, headers=headers)

# Poll for insight
import time
while True:
    r = requests.get(f'{API_URL}/session/{session_id}/insight', headers=headers)
    data = r.json()
    if data.get('processed'):
        print(data['insight'])
        break
    time.sleep(3)
```

---

## Postman Collection

Import this JSON into Postman to test all endpoints:

```json
{
  "info": { "name": "Qleam API", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json" },
  "variable": [
    { "key": "base_url", "value": "https://YOUR_API_ID.execute-api.us-east-1.amazonaws.com/dev" },
    { "key": "token", "value": "YOUR_JWT_TOKEN" },
    { "key": "child_id", "value": "" },
    { "key": "session_id", "value": "" }
  ],
  "item": [
    {
      "name": "Create Child",
      "request": {
        "method": "POST", "url": "{{base_url}}/child",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }],
        "body": { "mode": "raw", "raw": "{\"name\": \"Baby Emma\"}", "options": { "raw": { "language": "json" } } }
      }
    },
    {
      "name": "Get Upload URL",
      "request": {
        "method": "POST", "url": "{{base_url}}/session/upload",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }],
        "body": { "mode": "raw", "raw": "{\"child_id\": \"{{child_id}}\"}", "options": { "raw": { "language": "json" } } }
      }
    },
    {
      "name": "Start Processing",
      "request": {
        "method": "POST", "url": "{{base_url}}/session/{{session_id}}/start",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }],
        "body": { "mode": "raw", "raw": "{}", "options": { "raw": { "language": "json" } } }
      }
    },
    {
      "name": "Get Insight",
      "request": {
        "method": "GET", "url": "{{base_url}}/session/{{session_id}}/insight",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }]
      }
    },
    {
      "name": "Submit Feedback",
      "request": {
        "method": "POST", "url": "{{base_url}}/session/{{session_id}}/feedback",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }],
        "body": { "mode": "raw", "raw": "{\"response_type\": \"hunger\", \"effectiveness\": \"helpful\", \"word_token\": \"\"}", "options": { "raw": { "language": "json" } } }
      }
    },
    {
      "name": "List Sessions",
      "request": {
        "method": "GET", "url": "{{base_url}}/child/{{child_id}}/sessions",
        "header": [{ "key": "Authorization", "value": "Bearer {{token}}" }]
      }
    }
  ]
}
```

---

*API Reference version: MVP 1.0 — February 2026*
