# Qleam MVP — Architecture Document

> Complete system architecture with diagrams for all layers: infrastructure, data flow, ML pipeline, and security.

---

## 1. High-Level System Architecture

```mermaid
graph TB
    subgraph CLIENT["🌐 Client Layer"]
        APP["React SPA\n(AWS Amplify)"]
        MIC["Browser\nMicrophone API"]
    end

    subgraph AUTH["🔐 Authentication"]
        COGNITO["Amazon Cognito\nUser Pool\n(JWT Tokens)"]
    end

    subgraph EDGE["⚡ Edge / API Layer"]
        CF["CloudFront CDN\n(Frontend Hosting)"]
        APIGW["API Gateway\n(REST API)"]
        S3_FE["S3\n(Frontend Bucket)"]
    end

    subgraph COMPUTE["🧠 Compute Layer"]
        API_LAMBDA["API Handler\nLambda"]
        SFN["Step Functions\n(Audio Pipeline)"]
        FE_LAMBDA["Feature Extraction\nLambda"]
        CE_LAMBDA["Cluster Engine\nLambda"]
        IG_LAMBDA["Insight Generator\nLambda"]
        RE_LAMBDA["Reinforcement Engine\nLambda"]
        FP_LAMBDA["Feedback Processor\nLambda"]
    end

    subgraph STORAGE["💾 Storage Layer"]
        S3_AUDIO["S3\n(Audio Storage)"]
        DDB_CP["DynamoDB\nChildProfile"]
        DDB_SE["DynamoDB\nSession"]
        DDB_SC["DynamoDB\nSoundCluster"]
        DDB_SB["DynamoDB\nSemanticBridge"]
        DDB_FB["DynamoDB\nFeedback"]
    end

    subgraph AI["🤖 AI Layer"]
        BEDROCK["Amazon Bedrock\n(Claude 3 Haiku)\n[PROD only]"]
    end

    subgraph OPS["📊 Operations"]
        CW["CloudWatch\n(Logs + Alarms)"]
        DASH["CloudWatch\nDashboard"]
    end

    subgraph NETWORK["🔒 Network"]
        VPC["VPC\n10.0.0.0/16"]
        PUB_SUB["Public Subnets\n(NAT Gateway)"]
        PRIV_SUB["Private Subnets\n(Lambda)"]
    end

    %% Client flows
    APP --> CF
    MIC --> APP
    APP --> COGNITO
    APP --> APIGW

    %% Edge flows
    CF --> S3_FE
    APIGW --> COGNITO
    APIGW --> API_LAMBDA

    %% API Lambda flows
    API_LAMBDA --> S3_AUDIO
    API_LAMBDA --> SFN
    API_LAMBDA --> DDB_SE
    API_LAMBDA --> DDB_CP
    API_LAMBDA --> FP_LAMBDA

    %% Step Functions pipeline
    SFN --> FE_LAMBDA
    SFN --> CE_LAMBDA
    SFN --> IG_LAMBDA

    %% Lambda → Storage
    FE_LAMBDA --> S3_AUDIO
    FE_LAMBDA --> DDB_CP
    FE_LAMBDA --> DDB_SE
    CE_LAMBDA --> DDB_SC
    CE_LAMBDA --> DDB_SE
    IG_LAMBDA --> DDB_SE
    IG_LAMBDA --> DDB_SC
    IG_LAMBDA --> DDB_SB
    IG_LAMBDA --> BEDROCK
    RE_LAMBDA --> DDB_SC
    RE_LAMBDA --> DDB_SB
    FP_LAMBDA --> DDB_FB
    FP_LAMBDA --> RE_LAMBDA

    %% Network
    API_LAMBDA --> PRIV_SUB
    FE_LAMBDA --> PRIV_SUB
    CE_LAMBDA --> PRIV_SUB
    IG_LAMBDA --> PRIV_SUB
    PRIV_SUB --> PUB_SUB
    PUB_SUB --> VPC

    %% Monitoring
    API_LAMBDA --> CW
    FE_LAMBDA --> CW
    CE_LAMBDA --> CW
    IG_LAMBDA --> CW
    SFN --> CW
    CW --> DASH

    style CLIENT fill:#e8f4f8,stroke:#2196F3
    style AUTH fill:#fff3e0,stroke:#FF9800
    style EDGE fill:#f3e5f5,stroke:#9C27B0
    style COMPUTE fill:#e8f5e9,stroke:#4CAF50
    style STORAGE fill:#fce4ec,stroke:#E91E63
    style AI fill:#e0f2f1,stroke:#009688
    style OPS fill:#f5f5f5,stroke:#9E9E9E
    style NETWORK fill:#fff8e1,stroke:#FFC107
```

---

## 2. AWS Infrastructure Architecture

```mermaid
graph LR
    subgraph REGION["AWS Region: us-east-1"]
        subgraph VPC["VPC (10.0.0.0/16)"]
            subgraph AZ1["Availability Zone A"]
                PUB1["Public Subnet\n10.0.1.0/24"]
                PRIV1["Private Subnet\n10.0.3.0/24"]
                NAT1["NAT Gateway"]
            end
            subgraph AZ2["Availability Zone B"]
                PUB2["Public Subnet\n10.0.2.0/24"]
                PRIV2["Private Subnet\n10.0.4.0/24"]
            end
            IGW["Internet Gateway"]
            SG_LAMBDA["Security Group\n(Lambda)\nEgress: 443 only"]
        end

        subgraph GLOBAL_SERVICES["Global / Regional Services"]
            CF["CloudFront\nDistribution"]
            COGNITO["Cognito\nUser Pool"]
            APIGW["API Gateway\nREST API"]
        end

        subgraph LAMBDA_LAYER["Lambda Functions (Private Subnets)"]
            L1["feature-extraction\n512MB / 5min"]
            L2["cluster-engine\n256MB / 2min"]
            L3["insight-generator\n256MB / 2min"]
            L4["reinforcement-engine\n256MB / 1min"]
            L5["feedback-processor\n128MB / 30s"]
            L6["api-handler\n256MB / 30s"]
            LAY1["Layer: audio-processing\n(librosa+numpy+scipy)"]
            LAY2["Layer: shared-utils\n(constants+normalization)"]
        end

        subgraph SFN_LAYER["Orchestration"]
            SFN["Step Functions\nExpress Workflow\n5min timeout"]
        end

        subgraph STORAGE_LAYER["Storage"]
            S3A["S3: Audio\nAES-256 encrypted\nVersioned"]
            S3F["S3: Frontend\nStatic website"]
            DDB1["DynamoDB\nChildProfile\nOn-demand"]
            DDB2["DynamoDB\nSession\nOn-demand"]
            DDB3["DynamoDB\nSoundCluster\nOn-demand"]
            DDB4["DynamoDB\nSemanticBridge\nOn-demand"]
            DDB5["DynamoDB\nFeedback\nOn-demand"]
        end

        subgraph MONITORING["Monitoring"]
            CWL["CloudWatch Logs\n30/90 day retention"]
            CWA["CloudWatch Alarms\n(Lambda + API + SFN)"]
            CWD["CloudWatch Dashboard"]
            SNS["SNS Topic\n(Email Alerts)"]
        end

        subgraph AI_LAYER["AI (PROD)"]
            BEDROCK["Bedrock\nClaude 3 Haiku"]
        end
    end

    IGW --> PUB1
    IGW --> PUB2
    PUB1 --> NAT1
    NAT1 --> PRIV1
    PRIV1 --> SG_LAMBDA
    PRIV2 --> SG_LAMBDA
    SG_LAMBDA --> L1
    SG_LAMBDA --> L2
    SG_LAMBDA --> L3
    SG_LAMBDA --> L4
    SG_LAMBDA --> L5
    SG_LAMBDA --> L6
    L1 --> LAY1
    L1 --> LAY2
    L2 --> LAY2
    L3 --> LAY2
    APIGW --> L6
    L6 --> SFN
    SFN --> L1
    SFN --> L2
    SFN --> L3
    L3 --> BEDROCK
    L1 --> S3A
    L1 --> DDB1
    L1 --> DDB2
    L2 --> DDB3
    L3 --> DDB4
    L5 --> DDB5
    CF --> S3F
    CWA --> SNS
    CWA --> CWD
```

---

## 3. Terraform Module Dependency Graph

```mermaid
graph TD
    GLOBAL["global/\n(S3 state + DynamoDB lock)"]

    subgraph ENV["environments/dev or prod"]
        VPC["module.vpc\n(Network foundation)"]
        IAM["module.iam\n(Roles & policies)"]
        S3["module.s3\n(Audio storage)"]
        DDB["module.dynamodb\n(5 tables)"]
        COGNITO["module.cognito\n(Auth)"]
        FRONTEND["module.frontend\n(CloudFront + S3)"]
        LAMBDA["module.lambda\n(6 functions + 2 layers)"]
        SFN["module.step_functions\n(Pipeline orchestration)"]
        APIGW["module.api_gateway\n(REST API)"]
        CW["module.cloudwatch\n(Monitoring)"]
    end

    GLOBAL -.->|"remote state\n(S3 backend)"| ENV

    VPC --> LAMBDA
    IAM --> LAMBDA
    IAM --> SFN
    S3 --> LAMBDA
    DDB --> LAMBDA
    COGNITO --> APIGW
    FRONTEND --> COGNITO
    FRONTEND --> S3
    LAMBDA --> SFN
    LAMBDA --> APIGW
    SFN --> CW
    APIGW --> CW
    LAMBDA --> CW

    style GLOBAL fill:#fff3e0,stroke:#FF9800
    style VPC fill:#e3f2fd,stroke:#2196F3
    style IAM fill:#fce4ec,stroke:#E91E63
    style S3 fill:#e8f5e9,stroke:#4CAF50
    style DDB fill:#e8f5e9,stroke:#4CAF50
    style COGNITO fill:#f3e5f5,stroke:#9C27B0
    style FRONTEND fill:#e0f2f1,stroke:#009688
    style LAMBDA fill:#fff8e1,stroke:#FFC107
    style SFN fill:#fff8e1,stroke:#FFC107
    style APIGW fill:#e8eaf6,stroke:#3F51B5
    style CW fill:#f5f5f5,stroke:#9E9E9E
```

---

## 4. DynamoDB Data Model

```mermaid
erDiagram
    ChildProfile {
        string child_id PK
        string parent_id
        string name
        map baseline_features
        float readiness_score
        string language_maturity_level
        int session_count
        string created_at
        string updated_at
    }

    Session {
        string session_id PK
        string child_id GSI
        string timestamp GSI-RANGE
        string s3_audio_path
        map feature_scores
        list embedding_vector
        string cluster_id
        bool deviation_flag
        string deviation_level
        float deviation_score
        float duration_seconds
        bool processed
        map insight
    }

    SoundCluster {
        string cluster_id PK
        string child_id GSI
        string last_updated GSI-RANGE
        list embedding_vector
        int frequency_count
        float reinforcement_weight
        map probable_intents
        float semantic_alignment_score
        string created_at
    }

    SemanticBridge {
        string bridge_id PK
        string child_id GSI1
        string cluster_id GSI2
        string word_token
        int co_occurrence_count
        float semantic_confidence_score
        string last_updated
        string created_at
    }

    Feedback {
        string feedback_id PK
        string session_id GSI
        string created_at GSI-RANGE
        string child_id
        string cluster_id
        string response_type
        string effectiveness
        string word_token
    }

    ChildProfile ||--o{ Session : "has many"
    ChildProfile ||--o{ SoundCluster : "has many"
    Session }o--|| SoundCluster : "assigned to"
    SoundCluster ||--o{ SemanticBridge : "has many"
    Session ||--o{ Feedback : "receives"
```

---

## 5. Security Architecture

```mermaid
graph TB
    subgraph INTERNET["Internet"]
        USER["Parent\n(Browser)"]
    end

    subgraph PERIMETER["Perimeter Security"]
        CF_WAF["CloudFront\n+ HTTPS only\n+ TLS 1.2+"]
        COGNITO_AUTH["Cognito\nJWT Auth\n+ Email verify\n+ MFA (PROD)"]
    end

    subgraph API_LAYER["API Security"]
        APIGW_AUTH["API Gateway\nCognito Authorizer\n(JWT validation)"]
        CORS["CORS Policy\n(Allowed origins only)"]
    end

    subgraph COMPUTE_SEC["Compute Security"]
        VPC_PRIV["Private VPC Subnets\n(No public IP)"]
        SG["Security Group\nEgress: 443 only\nNo inbound"]
        IAM_ROLE["IAM Execution Role\nLeast privilege\nPer-service"]
    end

    subgraph DATA_SEC["Data Security"]
        S3_ENC["S3 AES-256\nEncryption at rest\nPublic access blocked\nVersioning enabled"]
        DDB_ENC["DynamoDB\nEncryption at rest\nPITR enabled"]
        TLS["TLS in transit\n(All API calls)"]
    end

    subgraph AUDIT["Audit & Compliance"]
        CW_LOGS["CloudWatch Logs\n(All Lambda invocations)"]
        CW_ALARMS["CloudWatch Alarms\n(Error rate monitoring)"]
        DISCLAIMER["Non-diagnostic\nDisclaimer on all outputs"]
    end

    USER --> CF_WAF
    CF_WAF --> COGNITO_AUTH
    COGNITO_AUTH --> APIGW_AUTH
    APIGW_AUTH --> CORS
    CORS --> VPC_PRIV
    VPC_PRIV --> SG
    SG --> IAM_ROLE
    IAM_ROLE --> S3_ENC
    IAM_ROLE --> DDB_ENC
    IAM_ROLE --> TLS
    IAM_ROLE --> CW_LOGS
    CW_LOGS --> CW_ALARMS

    style INTERNET fill:#ffebee,stroke:#f44336
    style PERIMETER fill:#e8f5e9,stroke:#4CAF50
    style API_LAYER fill:#e3f2fd,stroke:#2196F3
    style COMPUTE_SEC fill:#fff3e0,stroke:#FF9800
    style DATA_SEC fill:#f3e5f5,stroke:#9C27B0
    style AUDIT fill:#f5f5f5,stroke:#9E9E9E
```

---

## 6. Multi-Environment Architecture

```mermaid
graph LR
    subgraph SHARED["Shared (Global)"]
        TF_STATE["S3: Terraform State\nqleam-terraform-state"]
        TF_LOCK["DynamoDB: State Lock\nqleam-terraform-state-lock"]
        ECR["GitHub Actions\nArtifact Store"]
    end

    subgraph DEV_ENV["DEV Environment"]
        DEV_VPC["VPC 10.0.0.0/16\n2 AZs"]
        DEV_LAMBDA["Lambda Functions\n(dev prefix)"]
        DEV_DDB["DynamoDB Tables\n(dev prefix)"]
        DEV_API["API Gateway\n/dev stage"]
        DEV_CF["CloudFront\n(dev frontend)"]
    end

    subgraph PROD_ENV["PROD Environment"]
        PROD_VPC["VPC 10.1.0.0/16\n3 AZs"]
        PROD_LAMBDA["Lambda Functions\n(prod prefix)\n+ Bedrock enabled"]
        PROD_DDB["DynamoDB Tables\n(prod prefix)\n+ PITR enabled"]
        PROD_API["API Gateway\n/prod stage"]
        PROD_CF["CloudFront\n(prod frontend)"]
    end

    TF_STATE --> DEV_ENV
    TF_STATE --> PROD_ENV
    TF_LOCK --> DEV_ENV
    TF_LOCK --> PROD_ENV
    ECR --> DEV_LAMBDA
    ECR --> PROD_LAMBDA

    style SHARED fill:#fff3e0,stroke:#FF9800
    style DEV_ENV fill:#e3f2fd,stroke:#2196F3
    style PROD_ENV fill:#e8f5e9,stroke:#4CAF50
```

---

## 7. Component Interaction Summary

| Component | Triggers | Triggered By | Data Written | Data Read |
|-----------|----------|--------------|--------------|-----------|
| API Handler | User HTTP request | API Gateway | Session (pending) | ChildProfile, Session |
| Feature Extraction | Step Function | Step Functions | Session, ChildProfile | S3 audio |
| Cluster Engine | Step Function | Step Functions | SoundCluster, Session | SoundCluster |
| Insight Generator | Step Function | Step Functions | Session (insight) | Session, SoundCluster, SemanticBridge, ChildProfile |
| Feedback Processor | API Handler | API Handler (sync) | Feedback | Session |
| Reinforcement Engine | Feedback Processor | Feedback Processor (async) | SoundCluster, SemanticBridge | SoundCluster |

---

## 8. Scalability Design

```mermaid
graph TB
    subgraph SCALE["Scaling Characteristics"]
        L_SCALE["Lambda\nAuto-scales to 1000 concurrent\nPer-function concurrency limits"]
        DDB_SCALE["DynamoDB On-Demand\nAuto-scales read/write\nNo capacity planning needed"]
        SFN_SCALE["Step Functions Express\nUp to 100K executions/sec\nPer-account limits apply"]
        CF_SCALE["CloudFront\nGlobal edge network\nUnlimited scale"]
        APIGW_SCALE["API Gateway\n10K req/sec default\nIncrease via support ticket"]
    end

    subgraph BOTTLENECKS["Potential Bottlenecks"]
        AUDIO_SIZE["Audio Layer Size\n~200MB compressed\nCold start: ~3-5s"]
        DDB_HOT["DynamoDB Hot Partitions\nMitigated by UUID keys"]
        BEDROCK_LIMIT["Bedrock Rate Limits\n~100 req/min (Haiku)"]
    end

    subgraph MITIGATIONS["Mitigations"]
        PROV_CONCURRENCY["Provisioned Concurrency\n(Feature Extraction)\nEliminate cold starts"]
        DDB_DAX["DynamoDB DAX\n(Future: read caching)"]
        BEDROCK_FALLBACK["Rule-based fallback\nif Bedrock throttled"]
    end

    AUDIO_SIZE --> PROV_CONCURRENCY
    DDB_HOT --> DDB_DAX
    BEDROCK_LIMIT --> BEDROCK_FALLBACK
```

---

*Architecture version: MVP 1.0 — February 2026*
