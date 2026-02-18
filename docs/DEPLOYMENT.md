# Qleam MVP — Deployment Guide

> Step-by-step instructions to deploy Qleam from zero to production on AWS using GitHub Actions + Terraform.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Repository Setup](#2-repository-setup)
3. [AWS IAM Setup](#3-aws-iam-setup)
4. [GitHub Secrets Configuration](#4-github-secrets-configuration)
5. [Step 1 — Bootstrap Remote State](#step-1--bootstrap-remote-state)
6. [Step 2 — Deploy to DEV](#step-2--deploy-to-dev)
7. [Step 3 — Configure Frontend](#step-3--configure-frontend)
8. [Step 4 — Deploy to PROD](#step-4--deploy-to-prod)
9. [Post-Deployment Verification](#post-deployment-verification)
10. [Rollback Procedure](#rollback-procedure)
11. [Destroy Environment](#destroy-environment)
12. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### Required Tools (local machine)

| Tool | Minimum Version | Install |
|------|----------------|---------|
| AWS CLI | 2.x | https://aws.amazon.com/cli/ |
| Terraform | 1.6.0 | https://developer.hashicorp.com/terraform/install |
| Python | 3.11 | https://python.org |
| Node.js | 18.x | https://nodejs.org |
| Git | any | https://git-scm.com |

### AWS Account Requirements

- AWS account with programmatic access
- Permissions: IAM, S3, DynamoDB, Lambda, API Gateway, Cognito, CloudFront, CloudWatch, Step Functions, VPC, Bedrock (optional)
- Recommended: Create a dedicated IAM user for CI/CD with `AdministratorAccess` (restrict further in production)

---

## 2. Repository Setup

```bash
# Clone the repository
git clone https://github.com/YOUR_ORG/qleam.git
cd qleam

# Create the develop branch
git checkout -b develop
git push origin develop
```

### Branch Strategy

| Branch | Environment | Deployment |
|--------|-------------|------------|
| `develop` | DEV | Automatic on push |
| `main` | PROD | Manual approval required |
| `feature/*` | — | PR only (plan runs) |

---

## 3. AWS IAM Setup

### Create CI/CD IAM User

```bash
# Create user
aws iam create-user --user-name qleam-cicd

# Attach policy (use AdministratorAccess for MVP, restrict later)
aws iam attach-user-policy \
  --user-name qleam-cicd \
  --policy-arn arn:aws:iam::aws:policy/AdministratorAccess

# Create access keys
aws iam create-access-key --user-name qleam-cicd
```

Save the `AccessKeyId` and `SecretAccessKey` — you'll need them in the next step.

### Enable Amazon Bedrock (PROD only)

If using Bedrock for AI-generated insights:
1. Go to AWS Console → Amazon Bedrock → Model access
2. Request access to **Claude 3 Haiku** (`anthropic.claude-3-haiku-20240307-v1:0`)
3. Wait for approval (usually instant for Haiku)

---

## 4. GitHub Secrets Configuration

Go to: **GitHub Repo → Settings → Secrets and variables → Actions → New repository secret**

### Required Secrets

| Secret Name | Value | When to Set |
|-------------|-------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM user access key | Before Step 1 |
| `AWS_SECRET_ACCESS_KEY` | IAM user secret key | Before Step 1 |
| `TF_STATE_BUCKET` | Output from bootstrap | After Step 1 |
| `TF_STATE_LOCK_TABLE` | Output from bootstrap | After Step 1 |

### GitHub Environments Setup

Go to: **GitHub Repo → Settings → Environments**

Create two environments:
1. **`dev`** — No protection rules (auto-deploy)
2. **`prod`** — Add **Required reviewers** (yourself) to require manual approval

---

## Step 1 — Bootstrap Remote State

> **Run once only.** Creates the S3 bucket and DynamoDB table for Terraform remote state.

### Via GitHub Actions (Recommended)

1. Go to **Actions** tab in GitHub
2. Select **"Qleam — Bootstrap Remote State"**
3. Click **"Run workflow"**
4. In the `confirm` field, type exactly: `bootstrap`
5. Click **"Run workflow"**

### Via Local Terraform (Alternative)

```bash
cd qleam/infrastructure/global

# Configure AWS credentials
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1

terraform init
terraform apply -auto-approve
```

### After Bootstrap — Get Outputs

```bash
cd qleam/infrastructure/global
terraform output
```

Expected output:
```
tf_state_bucket_name     = "qleam-terraform-state-XXXXXXXX"
tf_state_lock_table_name = "qleam-terraform-state-lock"
```

**Add these values as GitHub Secrets:**
- `TF_STATE_BUCKET` = `qleam-terraform-state-XXXXXXXX`
- `TF_STATE_LOCK_TABLE` = `qleam-terraform-state-lock`

---

## Step 2 — Deploy to DEV

### Trigger Deployment

```bash
git checkout develop
git push origin develop
```

### What Happens (CI/CD Pipeline)

```
[1] Test          → pytest unit tests (normalization, similarity)
[2] Build Lambdas → zip each handler + build audio layer (librosa)
[3] Build Frontend → npm ci && npm run build
[4] TF Plan       → terraform plan (shows what will be created)
[5] TF Apply DEV  → terraform apply (creates all AWS resources)
[6] Deploy Frontend → aws s3 sync build/ → S3 + CloudFront invalidation
```

### Expected Resources Created (~15–20 minutes)

| Resource | Name |
|----------|------|
| VPC | qleam-dev-vpc |
| S3 (audio) | qleam-dev-audio-storage |
| S3 (frontend) | qleam-dev-frontend |
| DynamoDB (5 tables) | qleam-dev-ChildProfile, Session, etc. |
| Cognito User Pool | qleam-dev-user-pool |
| Lambda (6 functions) | qleam-dev-feature-extraction, etc. |
| Step Functions | qleam-dev-audio-pipeline |
| API Gateway | qleam-dev-api |
| CloudFront | (auto-generated domain) |
| CloudWatch | qleam-dev-dashboard |

### Get DEV Outputs

```bash
cd qleam/infrastructure/environments/dev
terraform output
```

---

## Step 3 — Configure Frontend

After DEV deployment, get the Terraform outputs and configure the frontend:

### Get Values

```bash
cd qleam/infrastructure/environments/dev
terraform output cognito_user_pool_id
terraform output cognito_client_id
terraform output api_endpoint
terraform output cloudfront_domain_name
```

### Set as GitHub Secrets (for CI/CD builds)

| Secret | Terraform Output |
|--------|-----------------|
| `REACT_APP_COGNITO_USER_POOL_ID` | `cognito_user_pool_id` |
| `REACT_APP_COGNITO_CLIENT_ID` | `cognito_client_id` |
| `REACT_APP_API_URL` | `api_endpoint` |

### For Local Development

Create `qleam/frontend/.env.local`:
```env
REACT_APP_COGNITO_USER_POOL_ID=us-east-1_XXXXXXXXX
REACT_APP_COGNITO_CLIENT_ID=XXXXXXXXXXXXXXXXXXXXXXXXXX
REACT_APP_API_URL=https://XXXXXXXXXX.execute-api.us-east-1.amazonaws.com/dev
```

---

## Step 4 — Deploy to PROD

### Merge to Main

```bash
git checkout main
git merge develop
git push origin main
```

### Approval Gate

1. The pipeline will automatically deploy to DEV first
2. After DEV succeeds, it will **pause and wait for approval**
3. Go to **Actions → Running workflow → Review deployments**
4. Click **"Approve and deploy"**

### PROD Differences from DEV

| Setting | DEV | PROD |
|---------|-----|------|
| VPC CIDR | 10.0.0.0/16 | 10.1.0.0/16 |
| AZs | 2 | 3 |
| MFA | Disabled | Enabled |
| Audio retention | 90 days | 180 days |
| Log retention | 30 days | 90 days |
| Bedrock | Disabled | Enabled |
| Alert email | (empty) | alerts@qleam.io |
| Error thresholds | Relaxed | Strict |

---

## Post-Deployment Verification

### 1. Test API Health

```bash
# Get API endpoint
API_URL=$(cd qleam/infrastructure/environments/dev && terraform output -raw api_endpoint)

# Test (should return 401 without auth — that's correct)
curl -s -o /dev/null -w "%{http_code}" $API_URL/child
# Expected: 401
```

### 2. Test Cognito Auth

```bash
# Create a test user
aws cognito-idp sign-up \
  --client-id YOUR_CLIENT_ID \
  --username test@example.com \
  --password TestPass123! \
  --user-attributes Name=given_name,Value=Test

# Confirm the user (skip email verification for testing)
aws cognito-idp admin-confirm-sign-up \
  --user-pool-id YOUR_USER_POOL_ID \
  --username test@example.com
```

### 3. Test Full Pipeline

```bash
# Get auth token
TOKEN=$(aws cognito-idp initiate-auth \
  --auth-flow USER_PASSWORD_AUTH \
  --client-id YOUR_CLIENT_ID \
  --auth-parameters USERNAME=test@example.com,PASSWORD=TestPass123! \
  --query 'AuthenticationResult.IdToken' --output text)

# Create child profile
curl -X POST $API_URL/child \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Baby"}'

# Expected: {"child_id": "...", "message": "Child profile created"}
```

### 4. Verify CloudWatch Dashboard

Go to: **AWS Console → CloudWatch → Dashboards → qleam-dev-dashboard**

---

## Rollback Procedure

### Lambda Rollback (Quick)

```bash
# List Lambda versions
aws lambda list-versions-by-function \
  --function-name qleam-dev-feature-extraction

# Rollback to previous version
aws lambda update-alias \
  --function-name qleam-dev-feature-extraction \
  --name live \
  --function-version PREVIOUS_VERSION
```

### Terraform Rollback

```bash
cd qleam/infrastructure/environments/dev

# View state history
terraform state list

# Rollback via git (revert to previous commit)
git revert HEAD
git push origin develop
# CI/CD will re-apply the previous configuration
```

### DynamoDB Point-in-Time Recovery

```bash
# Restore table to specific time
aws dynamodb restore-table-to-point-in-time \
  --source-table-name qleam-dev-Session \
  --target-table-name qleam-dev-Session-restored \
  --restore-date-time "2026-02-18T10:00:00Z"
```

---

## Destroy Environment

> ⚠️ **WARNING: This permanently deletes all data.**

```bash
cd qleam/infrastructure/environments/dev

# Destroy all resources
terraform destroy -var-file=terraform.tfvars

# Type 'yes' when prompted
```

### Destroy Global State (Last Resort)

```bash
cd qleam/infrastructure/global
terraform destroy -auto-approve
```

---

## Troubleshooting

### Lambda Layer Too Large

The audio processing layer (librosa + numpy + scipy) can exceed 250MB unzipped.

**Solution:** Use a Docker-based build:
```bash
docker run --rm -v $(pwd):/var/task \
  public.ecr.aws/lambda/python:3.11 \
  pip install librosa numpy scipy -t /var/task/python/
```

### Terraform State Lock

If a pipeline fails mid-apply, the state may be locked.

```bash
# Force unlock (use the lock ID from the error message)
cd qleam/infrastructure/environments/dev
terraform force-unlock LOCK_ID
```

### Cognito Callback URL Mismatch

If login redirects fail, update the Cognito app client callback URLs:
```bash
aws cognito-idp update-user-pool-client \
  --user-pool-id YOUR_POOL_ID \
  --client-id YOUR_CLIENT_ID \
  --callback-urls "https://YOUR_CLOUDFRONT_DOMAIN/callback" \
  --logout-urls "https://YOUR_CLOUDFRONT_DOMAIN/logout"
```

### Step Function Timeout

Default timeout is 5 minutes. If audio processing takes longer:
```hcl
# In modules/step_functions/main.tf
timeout_seconds = 600  # Increase to 10 minutes
```

### CloudFront 403 on React Routes

Add a CloudFront error page for SPA routing:
```hcl
# In modules/frontend/main.tf — already configured
custom_error_response {
  error_code         = 403
  response_code      = 200
  response_page_path = "/index.html"
}
```

---

## Cost Estimate (DEV — Light Usage)

| Service | Monthly Cost (est.) |
|---------|-------------------|
| Lambda (1000 invocations) | ~$0.00 (free tier) |
| API Gateway (10K requests) | ~$0.04 |
| DynamoDB (on-demand) | ~$0.25 |
| S3 (1GB audio) | ~$0.02 |
| CloudFront | ~$0.01 |
| Cognito (< 50K MAU) | $0.00 (free tier) |
| Step Functions (1000 executions) | ~$0.00 (free tier) |
| NAT Gateway | ~$32/month ⚠️ |
| **Total** | **~$33/month** |

> 💡 **Cost tip:** The NAT Gateway dominates DEV costs. For dev-only, you can set `enable_nat_gateway = false` and use VPC endpoints instead.

---

*Last updated: February 2026*
