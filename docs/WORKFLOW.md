# Qleam MVP — Workflow Diagrams

> End-to-end workflow diagrams for every major process in the Qleam system.

---

## 1. CI/CD Pipeline Workflow (3 Separate Workflows)

Qleam uses **3 independent workflows** to allow isolated deployments:

### 1.1 Infrastructure Workflow (`infra-deploy.yml`)
Triggers on changes to `infrastructure/**` (except Lambda module)

```mermaid
flowchart TD
    PUSH["👨‍💻 Push to develop branch\ninfrastructure/** changes"]
    
    subgraph PLAN["Job: Terraform Plan"]
        P1["Checkout code"]
        P2["Configure AWS credentials"]
        P3["terraform init\n(S3 backend)"]
        P4["terraform validate"]
        P5["terraform plan"]
        P6["Upload plan output"]
        P1 --> P2 --> P3 --> P4 --> P5 --> P6
    end
    
    subgraph APPLY["Job: Terraform Apply\n(requires approval)"]
        A1["Checkout code"]
        A2["Configure AWS credentials"]
        A3["terraform init"]
        A4["terraform apply -auto-approve"]
        A5["Show outputs"]
        A1 --> A2 --> A3 --> A4 --> A5
    end
    
    PUSH --> PLAN --> APPLY
    
    style PLAN fill:#e3f2fd,stroke:#2196F3
    style APPLY fill:#e8f5e9,stroke:#4CAF50
```

### 1.2 Lambda Workflow (`lambda-deploy.yml`)
Triggers on changes to `lambdas/**`, `shared/**`, or `docker/**`

```mermaid
flowchart TD
    PUSH["👨‍💻 Push to develop branch\nlambdas/**, shared/**, docker/**"]
    
    subgraph TEST["Job: Run Tests"]
        T1["Setup Python 3.11"]
        T2["pip install pytest moto boto3 numpy"]
        T3["pytest tests/ -v --cov"]
        T1 --> T2 --> T3
    end
    
    subgraph BUILD["Job: Build & Push Lambda Images"]
        B1["Login to Amazon ECR"]
        B2["Fetch ECR repository URLs\nfrom Terraform state"]
        B3["Build Docker images\n(6 Lambda functions)"]
        B4["Push to ECR\n(commit SHA + latest tags)"]
        B5["Update Lambda functions\nwith new image URIs"]
        B1 --> B2 --> B3 --> B4 --> B5
    end
    
    PUSH --> TEST --> BUILD
    
    style TEST fill:#e3f2fd,stroke:#2196F3
    style BUILD fill:#e8f5e9,stroke:#4CAF50
```

### 1.3 Frontend Workflow (`frontend-deploy.yml`)
Triggers on changes to `frontend/**`

```mermaid
flowchart TD
    PUSH["👨‍💻 Push to develop branch\nfrontend/**"]
    
    subgraph BUILD["Job: Build Frontend"]
        F1["Fetch Terraform outputs\n(Cognito IDs, API URL)"]
        F2["Setup Node.js 18"]
        F3["npm install"]
        F4["npm run build\n(REACT_APP_* env vars)"]
        F5["Upload build artifact"]
        F1 --> F2 --> F3 --> F4 --> F5
    end
    
    subgraph DEPLOY["Job: Deploy Frontend"]
        D1["Download build artifact"]
        D2["S3 sync to frontend bucket"]
        D3["CloudFront invalidation"]
        D4["Display deployment URL"]
        D1 --> D2 --> D3 --> D4
    end
    
    PUSH --> BUILD --> DEPLOY
    
    style BUILD fill:#e3f2fd,stroke:#2196F3
    style DEPLOY fill:#e8f5e9,stroke:#4CAF50
```

---

## 2. Lambda Container Image Architecture

Lambda functions are deployed as **Docker container images** stored in ECR:

```mermaid
flowchart LR
    subgraph SOURCE["Source Code"]
        HANDLER["handler.py\n(Lambda code)"]
        SHARED["shared/\n(common utilities)"]
        DOCKER["Dockerfile\n(AWS Lambda Python 3.11)"]
    end
    
    subgraph BUILD["Build Process"]
        DOCKER_BUILD["docker build\n-t ecr-repo:sha"]
        LIBROSA["librosa, scipy, numpy\n(audio processing)"]
        BOTO3["boto3\n(AWS SDK)"]
    end
    
    subgraph ECR["Amazon ECR"]
        REPO_FE["qleam-dev-feature-extraction"]
        REPO_CE["qleam-dev-cluster-engine"]
        REPO_RE["qleam-dev-reinforcement-engine"]
        REPO_IG["qleam-dev-insight-generator"]
        REPO_FP["qleam-dev-feedback-processor"]
        REPO_AH["qleam-dev-api-handler"]
    end
    
    subgraph LAMBDA["AWS Lambda"]
        L_FE["Feature Extraction\n(1024 MB)"]
        L_CE["Cluster Engine\n(512 MB)"]
        L_RE["Reinforcement Engine\n(512 MB)"]
        L_IG["Insight Generator\n(512 MB)"]
        L_FP["Feedback Processor\n(512 MB)"]
        L_AH["API Handler\n(512 MB)"]
    end
    
    SOURCE --> BUILD
    BUILD --> ECR
    ECR --> LAMBDA
    
    style ECR fill:#fff3e0,stroke:#FF9800
    style LAMBDA fill:#e8f5e9,stroke:#4CAF50
```

---

## 3. Audio Processing Pipeline (Step Functions)

```mermaid
flowchart TD
    START(["▶ Step Function\nExecution Start"])

    START --> INPUT["Input:\n{child_id, session_id,\ns3_audio_path}"]

    subgraph STATE1["State 1: Feature Extraction Lambda"]
        FE1["Download audio\nfrom S3"]
        FE2["Load audio\n(librosa, 22050Hz mono)"]
        FE3["Voice Activity Detection\n(trim silence)"]
        FE4["Extract Features"]
        FE5["Compute MFCC embedding\n(26-dim L2-normalized)"]
        FE6["Get/Create ChildProfile\nfrom DynamoDB"]
        FE7["Update EMA baseline\nnew = 0.3×current + 0.7×prev"]
        FE8["Compute deviation level\n(none/low/moderate/high)"]
        FE9["Compute readiness score\n(weighted composite)"]
        FE10["Save Session record\nto DynamoDB"]
        FE11["Update ChildProfile\n(baseline + readiness)"]

        FE1 --> FE2 --> FE3 --> FE4
        FE4 --> |"rhythm\nrepetition\nintensity\nflow"| FE5
        FE5 --> FE6 --> FE7 --> FE8 --> FE9 --> FE10 --> FE11
    end

    INPUT --> STATE1

    STATE1 --> |"feature_scores\nembedding_vector\ndeviation"| STATE2

    subgraph STATE2["State 2: Cluster Engine Lambda"]
        CE1["Query all clusters\nfor child_id (GSI)"]
        CE2{"Clusters\nexist?"}
        CE3["Compute cosine similarity\nvs each cluster centroid"]
        CE4{"Best similarity\n≥ 0.85?"}
        CE5["Attach to existing cluster\nUpdate centroid (incremental mean)\nIncrement frequency_count"]
        CE6["Create new cluster\nreinforcement_weight = 0.5\nprobable_intents = {}"]
        CE7["Link session → cluster_id\nin Session table"]

        CE1 --> CE2
        CE2 -->|No clusters| CE6
        CE2 -->|Has clusters| CE3
        CE3 --> CE4
        CE4 -->|Yes| CE5
        CE4 -->|No| CE6
        CE5 --> CE7
        CE6 --> CE7
    end

    STATE2 --> |"cluster_id\naction: attached/created\nsimilarity_score"| STATE3

    subgraph STATE3["State 3: Insight Generator Lambda"]
        IG1["Fetch Session, ChildProfile,\nCluster, SemanticBridge"]
        IG2["Determine probable intent\n(max probable_intents weight)"]
        IG3["Compute confidence score\nintent × reinforcement × frequency × semantic"]
        IG4["Determine cluster stability\n(forming/emerging/stable)"]
        IG5{"USE_BEDROCK\n= true?"}
        IG6["Generate insight\nvia Bedrock Claude 3 Haiku"]
        IG7["Rule-based suggested\nresponse (fallback)"]
        IG8["Build structured insight\nobject"]
        IG9["Save insight to\nSession record"]

        IG1 --> IG2 --> IG3 --> IG4 --> IG5
        IG5 -->|Yes| IG6
        IG5 -->|No| IG7
        IG6 --> IG8
        IG7 --> IG8
        IG8 --> IG9
    end

    STATE3 --> |"insight object\nstored in Session"| END_OK(["✅ Pipeline Complete\nInsight available via API"])

    STATE1 -->|"Error"| CATCH1["Catch: Feature\nExtraction Failed"]
    STATE2 -->|"Error"| CATCH2["Catch: Cluster\nEngine Failed"]
    STATE3 -->|"Error"| CATCH3["Catch: Insight\nGeneration Failed"]

    CATCH1 --> FAIL(["❌ Execution Failed\nCloudWatch alarm triggered"])
    CATCH2 --> FAIL
    CATCH3 --> FAIL

    style STATE1 fill:#e3f2fd,stroke:#2196F3
    style STATE2 fill:#e8f5e9,stroke:#4CAF50
    style STATE3 fill:#f3e5f5,stroke:#9C27B0
```

---

## 4. Bootstrap & First-Time Setup Workflow

```mermaid
flowchart TD
    START(["🚀 Start: New Project Setup"])

    START --> PREREQ["Install Prerequisites\nAWS CLI, Terraform, Docker, Python, Node, Git"]
    PREREQ --> IAM_SETUP["Create IAM User: qleam-cicd\nAttach AdministratorAccess\nGenerate Access Keys"]
    IAM_SETUP --> GITHUB_REPO["Create GitHub Repository\nPush qleam/ code"]
    GITHUB_REPO --> SECRETS["Add GitHub Secrets:\n• AWS_ACCESS_KEY_ID\n• AWS_SECRET_ACCESS_KEY"]

    SECRETS --> MANUAL_STATE["📦 Manually Create State Bucket\naws s3api create-bucket\n--bucket qleam-terraform-state"]
    
    MANUAL_STATE --> STATE_CONFIG["Configure State Bucket:\n• Enable versioning\n• Enable encryption\n• Block public access\n• Create DynamoDB lock table"]

    STATE_CONFIG --> ENV_SETUP["Create GitHub Environments:\n• dev (no protection)\n• prod (required reviewers)"]

    ENV_SETUP --> BEDROCK_CHECK{"Using Bedrock\nin PROD?"}
    BEDROCK_CHECK -->|Yes| BEDROCK_ENABLE["Enable Bedrock Model Access\nAWS Console → Bedrock\n→ Claude 3 Haiku"]
    BEDROCK_CHECK -->|No| PUSH_DEV

    BEDROCK_ENABLE --> PUSH_DEV["git push origin develop\n→ Triggers infra-deploy"]

    PUSH_DEV --> INFRA_DEPLOY["Infrastructure Deployed:\n• VPC, IAM, ECR\n• S3, DynamoDB\n• Cognito, API Gateway\n• Step Functions, CloudWatch"]

    INFRA_DEPLOY --> LAMBDA_DEPLOY["Trigger lambda-deploy:\n• Build Docker images\n• Push to ECR\n• Update Lambda functions"]

    LAMBDA_DEPLOY --> TEST_DEV["Test DEV Environment:\n• Sign up via CloudFront URL\n• Record test audio\n• Verify insight generated"]

    TEST_DEV --> PROD_READY{"Ready for PROD?"}
    PROD_READY -->|Yes| PUSH_MAIN["git push origin main\n→ Triggers PROD pipeline"]
    PROD_READY -->|No| ITERATE["Iterate on DEV\nFix issues"]
    ITERATE --> PUSH_DEV

    PUSH_MAIN --> APPROVAL["⏸️ Manual Approval\nRequired in GitHub"]
    APPROVAL --> PROD_DEPLOY["PROD Deployed ✅\nAll resources created"]
    PROD_DEPLOY --> DONE(["🎉 Qleam MVP Live!"])

    style START fill:#e8f5e9,stroke:#4CAF50
    style DONE fill:#e8f5e9,stroke:#4CAF50
    style MANUAL_STATE fill:#fff3e0,stroke:#FF9800
    style APPROVAL fill:#fce4ec,stroke:#E91E63
```

---

## 5. Terraform State Management

The Terraform state is stored in a **manually created S3 bucket** that persists across destroy/deploy cycles:

```mermaid
flowchart TD
    subgraph MANUAL["Manual Creation (One-time)"]
        CREATE["aws s3api create-bucket\n--bucket qleam-terraform-state"]
        VERSION["Enable versioning"]
        ENCRYPT["Enable encryption (AES256)"]
        BLOCK["Block public access"]
        LOCK["Create DynamoDB table\nqleam-terraform-state-lock"]
    end
    
    subgraph STATE["State Storage"]
        DEV_STATE["s3://qleam-terraform-state/dev/terraform.tfstate"]
        PROD_STATE["s3://qleam-terraform-state/prod/terraform.tfstate"]
        LAMBDA_LAYER["s3://qleam-terraform-state/lambda-layers/"]
    end
    
    subgraph TERRAFORM["Terraform Operations"]
        INIT["terraform init\n-backend-config bucket"]
        PLAN["terraform plan"]
        APPLY["terraform apply"]
        DESTROY["terraform destroy\n(preserves state bucket)"]
    end
    
    MANUAL --> STATE
    STATE --> TERRAFORM
    
    DESTROY --> PRESERVED["State bucket preserved\nfor next deployment"]
    
    style MANUAL fill:#fff3e0,stroke:#FF9800
    style STATE fill:#e3f2fd,stroke:#2196F3
    style PRESERVED fill:#e8f5e9,stroke:#4CAF50
```

---

## 6. Parent Session Recording Workflow

```mermaid
sequenceDiagram
    actor Parent
    participant App as React App
    participant Cognito as Amazon Cognito
    participant API as API Gateway
    participant Lambda as API Handler
    participant S3 as S3 (Audio)
    participant SFN as Step Functions
    participant Pipeline as Processing Pipeline
    participant DB as DynamoDB

    Parent->>App: Opens Qleam app
    App->>Cognito: Authenticate (JWT)
    Cognito-->>App: ID Token

    Parent->>App: Clicks "Start Recording"
    App->>App: navigator.mediaDevices.getUserMedia()
    App->>App: MediaRecorder.start()

    Note over App: Recording 5-30 seconds...

    Parent->>App: Clicks "Stop"
    App->>App: MediaRecorder.stop() → Blob

    App->>API: POST /session/upload\n{child_id}\nAuthorization: Bearer JWT
    API->>Lambda: Route to upload_session()
    Lambda->>S3: generate_presigned_url(PUT, 5min)
    Lambda->>DB: Create Session record\n{processed: false}
    Lambda-->>API: {session_id, upload_url}
    API-->>App: {session_id, upload_url}

    App->>S3: PUT audio.wav → presigned URL\n(direct browser → S3)
    S3-->>App: 200 OK

    App->>API: POST /session/{id}/start
    API->>Lambda: Route to start_processing()
    Lambda->>SFN: start_execution()\n{child_id, session_id, s3_key}
    SFN-->>Lambda: execution_arn
    Lambda-->>API: {status: "processing"}
    API-->>App: {status: "processing"}

    App->>App: Navigate to SessionDetail\nStart polling /insight

    loop Poll every 3 seconds
        App->>API: GET /session/{id}/insight
        API->>Lambda: Route to get_insight()
        Lambda->>DB: GetItem Session
        DB-->>Lambda: {processed: false}
        Lambda-->>API: {status: "processing"}
        API-->>App: {status: "processing"}
    end

    Note over SFN,Pipeline: Step Functions executes pipeline...
    SFN->>Pipeline: Feature Extraction → Cluster Engine → Insight Generator
    Pipeline->>DB: Update Session {processed: true, insight: {...}}

    App->>API: GET /session/{id}/insight
    API->>Lambda: Route to get_insight()
    Lambda->>DB: GetItem Session
    DB-->>Lambda: {processed: true, insight: {...}}
    Lambda-->>API: {insight: {...}}
    API-->>App: Full insight object

    App->>Parent: Display insight:\n- Probable intent + confidence\n- Suggested response\n- Feature radar chart
```

---

*Workflow diagrams version: MVP 2.0 — February 2026*
*All diagrams use Mermaid syntax — render in GitHub, VS Code (Mermaid extension), or https://mermaid.live*