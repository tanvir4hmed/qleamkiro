# Qleam MVP — Complete Infrastructure & Application

> **Baby vocalization pattern analysis platform** — Serverless AWS, Terraform modular architecture, React frontend, Python ML pipeline.

---

## 🏗️ Architecture Overview

```
Parent App (React + Amplify)
        │
        ▼
API Gateway (REST) ──► Cognito JWT Auth
        │
        ▼
API Handler Lambda
   ├── POST /child                    → Create child profile
   ├── DELETE /child/{id}             → Delete child + all data
   ├── GET /child/{id}/sessions       → List sessions
   ├── POST /session/upload           → Presigned S3 URL
   ├── POST /session/{id}/start       → Trigger Step Function
   ├── GET /session/{id}/insight      → Get insight
   └── POST /session/{id}/feedback    → Submit feedback
        │
        ▼
Step Functions (Audio Processing Pipeline)
   State 1: Feature Extraction Lambda
        │  ├── Download audio from S3
        │  ├── Extract MFCC features (rhythm, repetition, intensity, flow)
        │  ├── Update EMA baseline (α=0.3)
        │  └── Compute deviation level
        │
   State 2: Cluster Engine Lambda
        │  ├── Cosine similarity vs existing clusters (threshold=0.85)
        │  ├── Attach to existing cluster OR create new
        │  └── Update centroid (incremental mean)
        │
   State 3: Insight Generator Lambda
           ├── Determine probable intent (weighted confidence)
           ├── Generate suggested response (rule-based or Bedrock)
           └── Save insight to Session record

Feedback Loop (async):
   POST /feedback → Feedback Processor → Reinforcement Engine
        ├── Update reinforcement weight (+0.1 helpful / -0.05 ineffective)
        ├── Update probable intent distribution
        └── Update semantic bridge (word co-occurrence)
```

---

## 📁 Project Structure

```
qleam/
├── .github/
│   └── workflows/
│       ├── bootstrap.yml          # One-time: create Terraform remote state
│       └── deploy.yml             # CI/CD: test → build → plan → deploy
│
├── infrastructure/
│   ├── global/                    # Bootstrap: S3 state bucket + DynamoDB lock
│   ├── modules/
│   │   ├── vpc/                   # VPC, subnets, NAT gateway, security groups
│   │   ├── iam/                   # Lambda execution role, Step Functions role
│   │   ├── s3/                    # Audio storage bucket (encrypted, lifecycle)
│   │   ├── dynamodb/              # 5 tables: ChildProfile, Session, SoundCluster,
│   │   │                          #           SemanticBridge, Feedback
│   │   ├── cognito/               # User Pool + App Client (email auth)
│   │   ├── lambda/                # All 6 Lambda functions + 2 layers
│   │   ├── step_functions/        # Audio processing state machine
│   │   ├── api_gateway/           # REST API + Cognito authorizer
│   │   ├── cloudwatch/            # Alarms, dashboards, log groups
│   │   └── frontend/              # S3 + CloudFront for React app
│   └── environments/
│       ├── dev/                   # Dev environment root (main.tf + tfvars)
│       └── prod/                  # Prod environment root (main.tf + tfvars)
│
├── lambdas/
│   ├── feature_extraction/        # MFCC extraction, EMA baseline, deviation
│   ├── cluster_engine/            # Cosine similarity clustering
│   ├── reinforcement_engine/      # Weight updates, semantic bridges
│   ├── insight_generator/         # Intent inference, Bedrock integration
│   ├── feedback_processor/        # Feedback storage + async reinforcement
│   └── api_handler/               # REST API router
│
├── shared/
│   ├── constants.py               # All configuration constants
│   ├── normalization.py           # EMA, deviation, readiness score
│   ├── similarity.py              # Cosine similarity, centroid update
│   └── audio_utils.py             # librosa feature extraction pipeline
│
├── frontend/
│   ├── public/index.html
│   └── src/
│       ├── App.js                 # Amplify Authenticator + Router
│       ├── aws-config.js          # Cognito + API config
│       ├── pages/
│       │   ├── Dashboard.js       # Child selector, record, session list
│       │   └── SessionDetail.js   # Insight view + feedback form
│       └── components/
│           ├── RecordButton.js    # MediaRecorder + S3 upload
│           ├── InsightPanel.js    # Intent badge + confidence bar
│           ├── SessionCard.js     # Session summary card
│           ├── FeedbackForm.js    # Response type + effectiveness
│           └── FeatureChart.js    # Recharts radar chart
│
└── tests/
    ├── conftest.py                # Moto fixtures, DynamoDB tables
    ├── test_normalization.py      # EMA, deviation, readiness tests
    └── test_similarity.py         # Cosine similarity, clustering tests
```

---

## 🚀 Deployment Guide

### Prerequisites

| Tool | Version |
|------|---------|
| AWS CLI | ≥ 2.x (configured with credentials) |
| Terraform | ≥ 1.6.0 |
| Python | 3.11 |
| Node.js | 18.x |
| Git | any |

### Step 1 — Add GitHub Secrets

In your GitHub repository → Settings → Secrets and variables → Actions:

| Secret | Value |
|--------|-------|
| `AWS_ACCESS_KEY_ID` | Your AWS access key |
| `AWS_SECRET_ACCESS_KEY` | Your AWS secret key |
| `TF_STATE_BUCKET` | (set after Step 2) |
| `TF_STATE_LOCK_TABLE` | (set after Step 2) |

### Step 2 — Bootstrap Remote State (one-time)

Run the **Bootstrap** GitHub Action:
1. Go to Actions → "Qleam — Bootstrap Remote State"
2. Click "Run workflow"
3. Type `bootstrap` in the confirm field
4. Run it

This creates:
- S3 bucket for Terraform state
- DynamoDB table for state locking

Copy the output values into `TF_STATE_BUCKET` and `TF_STATE_LOCK_TABLE` secrets.

### Step 3 — Deploy to DEV

Push to the `develop` branch:
```bash
git checkout -b develop
git push origin develop
```

The CI/CD pipeline will:
1. ✅ Run unit tests
2. 📦 Build Lambda packages + audio layer
3. ⚛️ Build React frontend
4. 📋 Run `terraform plan`
5. 🚀 Run `terraform apply` (DEV)
6. 🌐 Deploy frontend to S3 + invalidate CloudFront

### Step 4 — Deploy to PROD

Push to `main` branch. PROD deployment requires **manual approval** in GitHub Environments.

```bash
git checkout main
git merge develop
git push origin main
```

### Step 5 — Configure Frontend Environment Variables

After Terraform apply, get the outputs:
```bash
cd qleam/infrastructure/environments/dev
terraform output
```

Set these as GitHub Secrets or in your `.env.local`:
```
REACT_APP_COGNITO_USER_POOL_ID=us-east-1_xxxxx
REACT_APP_COGNITO_CLIENT_ID=xxxxxxxxxx
REACT_APP_API_URL=https://xxxxxxxxxx.execute-api.us-east-1.amazonaws.com/dev
```

---

## 🔧 Local Development

### Run Tests
```bash
cd qleam
pip install pytest pytest-cov boto3 moto numpy
python -m pytest tests/ -v
```

### Run Frontend Locally
```bash
cd qleam/frontend
npm install
# Create .env.local with REACT_APP_* variables
npm start
```

### Manual Lambda Build
```bash
cd qleam

# Build shared utils layer
mkdir -p lambdas/layers/shared_utils_pkg/python
cp shared/*.py lambdas/layers/shared_utils_pkg/python/
cd lambdas/layers/shared_utils_pkg && zip -r ../shared_utils.zip python/ && cd ../../..

# Build audio layer (Linux only — use Docker on Windows)
pip install librosa numpy scipy --target lambdas/layers/audio_processing_pkg/python/
cd lambdas/layers/audio_processing_pkg && zip -r ../audio_processing.zip python/ && cd ../../..

# Build each Lambda
for fn in feature_extraction cluster_engine reinforcement_engine insight_generator feedback_processor api_handler; do
  cd lambdas/$fn && zip -r dist/${fn}.zip handler.py && cd ../..
done
```

### Manual Terraform Apply (DEV)
```bash
cd qleam/infrastructure/environments/dev
terraform init
terraform plan -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

---

## 🧠 ML Pipeline Details

### Feature Extraction
| Feature | Method | Range |
|---------|--------|-------|
| Rhythm | RMS energy peak regularity (CV inverse) | 0–1 |
| Repetition | MFCC self-similarity matrix off-diagonal mean | 0–1 |
| Emotional Intensity | F0 variance + RMS energy variance | 0–1 |
| Expressive Flow | Pause ratio + continuity ratio | 0–1 |

### EMA Baseline Update
```
new_baseline = α × current + (1 - α) × previous
α = 0.3 (configurable)
```

### Cluster Assignment
```
cosine_similarity(embedding, centroid) ≥ 0.85 → attach
                                       < 0.85 → create new cluster
```

### Reinforcement Weight Update
```
helpful     → weight += 0.10  (max 1.0)
neutral     → weight -= 0.02  (min 0.0)
ineffective → weight -= 0.05  (min 0.0)
```

### Confidence Score
```
confidence = intent_weight × reinforcement_weight × frequency_factor × semantic_factor
frequency_factor = min(session_count / 10, 1.0)
semantic_factor  = 1.0 + (semantic_alignment × 0.2)
max confidence   = 0.95 (never 100%)
```

---

## 📊 DynamoDB Tables

| Table | PK | GSI |
|-------|----|-----|
| ChildProfile | child_id | — |
| Session | session_id | child_id-timestamp-index |
| SoundCluster | cluster_id | child_id-last_updated-index |
| SemanticBridge | bridge_id | child_id-index, cluster_id-index |
| Feedback | feedback_id | session_id-created_at-index |

---

## 🔐 Security

- All S3 buckets: encrypted (AES-256), versioned, public access blocked
- DynamoDB: encrypted at rest, PITR enabled
- Lambda: runs in private VPC subnets, no public internet access
- API Gateway: Cognito JWT authorizer on all routes
- IAM: least-privilege roles per service
- Cognito: email verification required, MFA optional (enabled in prod)

---

## 📈 Monitoring

CloudWatch alarms configured for:
- Lambda error rate > threshold
- Lambda duration > threshold
- API Gateway 5xx errors
- Step Function failures

Dashboard: `qleam-{env}-dashboard` in CloudWatch console.

---

## ⚠️ Disclaimer

Qleam provides **behavioral pattern observations only**. It is not a medical device and does not provide medical diagnoses. Always consult a healthcare professional for medical concerns.

---

*Built with ❤️ — Terraform + AWS Lambda + React + Python*
