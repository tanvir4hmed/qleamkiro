# Qleam MVP — Workflow Diagrams

> End-to-end workflow diagrams for every major process in the Qleam system.

---

## 1. CI/CD Pipeline Workflow

```mermaid
flowchart TD
    DEV_PUSH["👨‍💻 Developer pushes code\nto develop or main branch"]
    PR["🔀 Pull Request\nto main"]

    DEV_PUSH --> TRIGGER
    PR --> TRIGGER

    TRIGGER["GitHub Actions\nWorkflow Triggered"]

    subgraph JOB1["Job 1: Test (parallel)"]
        T1["Setup Python 3.11"]
        T2["pip install pytest moto boto3 numpy"]
        T3["pytest tests/ -v --cov"]
        T4["Upload coverage report"]
        T1 --> T2 --> T3 --> T4
    end

    subgraph JOB2["Job 2: Build Lambdas (parallel)"]
        B1["Build shared_utils layer\n(cp shared/*.py → zip)"]
        B2["Build audio_processing layer\n(pip install librosa numpy scipy\n--platform manylinux2014_x86_64)"]
        B3["Zip each Lambda handler\n(6 functions)"]
        B4["Upload artifacts\n(GitHub Actions store)"]
        B1 --> B3
        B2 --> B3
        B3 --> B4
    end

    subgraph JOB3["Job 3: Build Frontend (parallel)"]
        F1["Setup Node.js 18"]
        F2["npm ci"]
        F3["npm run build\n(REACT_APP_* env vars)"]
        F4["Upload build artifact"]
        F1 --> F2 --> F3 --> F4
    end

    TRIGGER --> JOB1
    TRIGGER --> JOB2
    TRIGGER --> JOB3

    subgraph JOB4["Job 4: Terraform Plan"]
        P1["Download Lambda artifacts"]
        P2["terraform init\n(S3 backend)"]
        P3["terraform validate"]
        P4["terraform plan -out=tfplan"]
        P5{"PR?"}
        P6["Comment plan on PR"]
        P7["Upload tfplan artifact"]
        P1 --> P2 --> P3 --> P4 --> P5
        P5 -->|Yes| P6
        P5 -->|No| P7
        P6 --> P7
    end

    JOB1 --> JOB4
    JOB2 --> JOB4
    JOB3 --> JOB4

    subgraph JOB5["Job 5: Deploy DEV"]
        D1["terraform apply -auto-approve"]
        D2["aws s3 sync build/ → S3"]
        D3["CloudFront invalidation"]
        D1 --> D2 --> D3
    end

    JOB4 --> BRANCH_CHECK{"Branch?"}
    BRANCH_CHECK -->|"develop or main"| JOB5
    BRANCH_CHECK -->|"PR only"| STOP["✅ Plan only\n(no deploy)"]

    subgraph JOB6["Job 6: Deploy PROD\n(main branch only)"]
        APPROVAL["⏸️ Manual Approval\nRequired in GitHub\nEnvironments"]
        PD1["terraform apply -auto-approve\n(prod tfvars)"]
        PD2["aws s3 sync build/ → S3 (prod)"]
        PD3["CloudFront invalidation (prod)"]
        APPROVAL --> PD1 --> PD2 --> PD3
    end

    JOB5 --> MAIN_CHECK{"main branch?"}
    MAIN_CHECK -->|Yes| JOB6
    MAIN_CHECK -->|No| DONE_DEV["✅ DEV deployed"]
    JOB6 --> DONE_PROD["✅ PROD deployed"]

    style JOB1 fill:#e3f2fd,stroke:#2196F3
    style JOB2 fill:#e8f5e9,stroke:#4CAF50
    style JOB3 fill:#f3e5f5,stroke:#9C27B0
    style JOB4 fill:#fff3e0,stroke:#FF9800
    style JOB5 fill:#e0f2f1,stroke:#009688
    style JOB6 fill:#fce4ec,stroke:#E91E63
```

---

## 2. Audio Processing Pipeline (Step Functions)

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

        subgraph FEATURES["Feature Extraction Detail"]
            R["Rhythm\nRMS energy peak\nregularity (CV⁻¹)"]
            REP["Repetition\nMFCC self-similarity\noff-diagonal mean"]
            INT["Emotional Intensity\nF0 variance +\nRMS energy variance"]
            FLOW["Expressive Flow\nPause ratio +\ncontinuity ratio"]
        end
        FE4 --> FEATURES
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
    style FEATURES fill:#fff8e1,stroke:#FFC107
```

---

## 3. Parent Session Recording Workflow

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

## 4. Feedback & Reinforcement Learning Workflow

```mermaid
sequenceDiagram
    actor Parent
    participant App as React App
    participant API as API Gateway
    participant FP as Feedback Processor
    participant RE as Reinforcement Engine
    participant DB_FB as DynamoDB Feedback
    participant DB_SC as DynamoDB SoundCluster
    participant DB_SB as DynamoDB SemanticBridge

    Parent->>App: Selects response tried\n(e.g. "Feeding")
    Parent->>App: Selects effectiveness\n("Helpful" / "Neutral" / "Ineffective")
    Parent->>App: (Optional) Types word heard\n(e.g. "mama")
    Parent->>App: Clicks "Submit Feedback"

    App->>API: POST /session/{id}/feedback\n{response_type, effectiveness, word_token}

    API->>FP: Invoke (synchronous)
    FP->>DB_FB: GetItem Session → get child_id, cluster_id
    FP->>DB_FB: PutItem Feedback record\n{feedback_id, session_id, effectiveness...}
    FP->>RE: Invoke Lambda (async Event)\n{child_id, cluster_id, effectiveness, word_token}
    FP-->>API: {status: "feedback_processed", feedback_id}
    API-->>App: 200 OK

    App->>Parent: "✓ Thank you! Feedback recorded."

    Note over RE: Async reinforcement update...

    RE->>DB_SC: GetItem SoundCluster
    DB_SC-->>RE: {reinforcement_weight: 0.5, probable_intents: {...}}

    alt effectiveness = "helpful"
        RE->>RE: new_weight = min(0.5 + 0.1, 1.0) = 0.6
        RE->>RE: intents["hunger"] += 0.1 → normalize
    else effectiveness = "neutral"
        RE->>RE: new_weight = max(0.5 - 0.02, 0.0) = 0.48
    else effectiveness = "ineffective"
        RE->>RE: new_weight = max(0.5 - 0.05, 0.0) = 0.45
        RE->>RE: intents["hunger"] -= 0.05 → normalize
    end

    RE->>DB_SC: UpdateItem SoundCluster\n{reinforcement_weight, probable_intents}

    opt word_token provided
        RE->>DB_SB: Query SemanticBridge by cluster_id
        alt Bridge exists for word
            RE->>DB_SB: UpdateItem\nco_occurrence_count += 1\nconfidence += 0.05
        else New word
            RE->>DB_SB: PutItem new SemanticBridge\n{word_token, confidence: 0.05}
        end
        RE->>DB_SC: UpdateItem semantic_alignment_score
    end

    Note over DB_SC: Next session for this child\nwill use updated weights
```

---

## 5. ML Learning Loop Over Time

```mermaid
flowchart LR
    subgraph SESSION1["Session 1"]
        S1_AUDIO["Audio\nRecorded"]
        S1_FEAT["Features\nExtracted"]
        S1_CLUSTER["New Cluster\nCreated\n(weight=0.5)"]
        S1_INSIGHT["Insight:\nUnknown\n(confidence: low)"]
        S1_AUDIO --> S1_FEAT --> S1_CLUSTER --> S1_INSIGHT
    end

    subgraph FEEDBACK1["Feedback 1"]
        FB1["Parent tries feeding\n→ Helpful"]
        FB1_UPDATE["Cluster weight: 0.5→0.6\nintents: {hunger: 0.1}"]
        FB1 --> FB1_UPDATE
    end

    subgraph SESSION2["Session 2-3"]
        S2_AUDIO["Similar Audio\nRecorded"]
        S2_CLUSTER["Attached to\nSame Cluster\n(similarity ≥ 0.85)"]
        S2_BASELINE["EMA Baseline\nUpdated (α=0.3)"]
        S2_INSIGHT["Insight:\nHunger (low conf)"]
        S2_AUDIO --> S2_CLUSTER --> S2_BASELINE --> S2_INSIGHT
    end

    subgraph FEEDBACK2["Feedback 2-3"]
        FB2["Parent confirms\nfeeding works"]
        FB2_UPDATE["Cluster weight: 0.6→0.7\nintents: {hunger: 0.3}"]
        FB2 --> FB2_UPDATE
    end

    subgraph SESSION5["Session 5+"]
        S5_AUDIO["Similar Audio"]
        S5_CLUSTER["Cluster: emerging\nfrequency=5"]
        S5_INSIGHT["Insight:\nHunger (medium conf ~45%)"]
        S5_AUDIO --> S5_CLUSTER --> S5_INSIGHT
    end

    subgraph SESSION10["Session 10+"]
        S10_AUDIO["Similar Audio"]
        S10_CLUSTER["Cluster: stable\nfrequency=10+\nweight=0.9"]
        S10_INSIGHT["Insight:\nHunger (high conf ~75%)"]
        S10_AUDIO --> S10_CLUSTER --> S10_INSIGHT
    end

    subgraph SEMANTIC["Semantic Bridge"]
        WORD["Parent hears 'mama'\nEnters in feedback"]
        BRIDGE["SemanticBridge created\nword='mama'\nconfidence=0.05"]
        BRIDGE_GROW["After 5 co-occurrences\nconfidence=0.25\nAlignment boosts insight"]
        WORD --> BRIDGE --> BRIDGE_GROW
    end

    SESSION1 --> FEEDBACK1 --> SESSION2 --> FEEDBACK2 --> SESSION5 --> SESSION10
    FEEDBACK2 --> SEMANTIC
    SEMANTIC --> SESSION10

    style SESSION1 fill:#e3f2fd,stroke:#2196F3
    style SESSION2 fill:#e8f5e9,stroke:#4CAF50
    style SESSION5 fill:#fff3e0,stroke:#FF9800
    style SESSION10 fill:#e8f5e9,stroke:#4CAF50
    style FEEDBACK1 fill:#fce4ec,stroke:#E91E63
    style FEEDBACK2 fill:#fce4ec,stroke:#E91E63
    style SEMANTIC fill:#f3e5f5,stroke:#9C27B0
```

---

## 6. Bootstrap & First-Time Setup Workflow

```mermaid
flowchart TD
    START(["🚀 Start: New Project Setup"])

    START --> PREREQ["Install Prerequisites\nAWS CLI, Terraform, Python, Node, Git"]
    PREREQ --> IAM_SETUP["Create IAM User: qleam-cicd\nAttach AdministratorAccess\nGenerate Access Keys"]
    IAM_SETUP --> GITHUB_REPO["Create GitHub Repository\nPush qleam/ code"]
    GITHUB_REPO --> SECRETS1["Add GitHub Secrets:\n• AWS_ACCESS_KEY_ID\n• AWS_SECRET_ACCESS_KEY"]

    SECRETS1 --> BOOTSTRAP["Run Bootstrap Workflow\n(GitHub Actions)\nType 'bootstrap' to confirm"]

    BOOTSTRAP --> BOOTSTRAP_CREATES["Creates:\n• S3: qleam-terraform-state-XXXX\n• DynamoDB: qleam-terraform-state-lock"]

    BOOTSTRAP_CREATES --> SECRETS2["Add GitHub Secrets:\n• TF_STATE_BUCKET\n• TF_STATE_LOCK_TABLE"]

    SECRETS2 --> ENV_SETUP["Create GitHub Environments:\n• dev (no protection)\n• prod (required reviewers)"]

    ENV_SETUP --> BEDROCK_CHECK{"Using Bedrock\nin PROD?"}
    BEDROCK_CHECK -->|Yes| BEDROCK_ENABLE["Enable Bedrock Model Access\nAWS Console → Bedrock\n→ Claude 3 Haiku"]
    BEDROCK_CHECK -->|No| PUSH_DEV

    BEDROCK_ENABLE --> PUSH_DEV["git push origin develop\n→ Triggers CI/CD"]

    PUSH_DEV --> PIPELINE_RUNS["Pipeline Runs:\n1. Tests ✅\n2. Build Lambdas ✅\n3. Build Frontend ✅\n4. TF Plan ✅\n5. TF Apply DEV ✅\n6. Deploy Frontend ✅"]

    PIPELINE_RUNS --> GET_OUTPUTS["Get Terraform Outputs:\nterraform output\n(API URL, Cognito IDs, CloudFront)"]

    GET_OUTPUTS --> FRONTEND_CONFIG["Add Frontend Secrets:\n• REACT_APP_COGNITO_USER_POOL_ID\n• REACT_APP_COGNITO_CLIENT_ID\n• REACT_APP_API_URL"]

    FRONTEND_CONFIG --> TEST_DEV["Test DEV Environment:\n• Sign up via CloudFront URL\n• Record test audio\n• Verify insight generated"]

    TEST_DEV --> PROD_READY{"Ready for PROD?"}
    PROD_READY -->|Yes| PUSH_MAIN["git push origin main\n→ Triggers PROD pipeline"]
    PROD_READY -->|No| ITERATE["Iterate on DEV\nFix issues"]
    ITERATE --> PUSH_DEV

    PUSH_MAIN --> APPROVAL["⏸️ Manual Approval\nRequired in GitHub"]
    APPROVAL --> PROD_DEPLOY["PROD Deployed ✅\nAll resources created"]
    PROD_DEPLOY --> DONE(["🎉 Qleam MVP Live!"])

    style START fill:#e8f5e9,stroke:#4CAF50
    style DONE fill:#e8f5e9,stroke:#4CAF50
    style BOOTSTRAP fill:#fff3e0,stroke:#FF9800
    style APPROVAL fill:#fce4ec,stroke:#E91E63
```

---

## 7. Data Flow: Audio → Insight

```mermaid
flowchart LR
    subgraph INPUT["Input"]
        WAV["WAV Audio\n5-30 seconds\n(baby vocalization)"]
    end

    subgraph PREPROCESSING["Pre-processing"]
        LOAD["librosa.load()\n22050Hz mono"]
        VAD["Voice Activity Detection\ntrim silence (top_db=20)"]
        LOAD --> VAD
    end

    subgraph FEATURE_EXT["Feature Extraction"]
        MFCC["MFCC\n13 coefficients\n(mean + std = 26-dim)"]
        RHYTHM["Rhythm Score\nRMS peaks → CV⁻¹"]
        REPET["Repetition Score\nSelf-similarity matrix"]
        INTENS["Intensity Score\nF0 variance + RMS variance"]
        FLOW["Flow Score\nPause ratio + continuity"]
        EMBED["Embedding Vector\n26-dim L2-normalized"]
    end

    subgraph BASELINE["Baseline Update"]
        EMA["EMA Update\nnew = 0.3×curr + 0.7×prev"]
        DEV["Deviation Detection\n|curr - baseline| / baseline"]
        READY["Readiness Score\n0.25×rhythm + 0.25×rep\n+ 0.30×intensity + 0.20×flow"]
    end

    subgraph CLUSTERING["Clustering"]
        COS["Cosine Similarity\nvs all child clusters"]
        THRESH{"≥ 0.85?"}
        ATTACH["Attach to cluster\nUpdate centroid"]
        CREATE["Create new cluster\nweight=0.5"]
    end

    subgraph INFERENCE["Intent Inference"]
        INTENTS["probable_intents\n(from reinforcement history)"]
        CONF["Confidence Score\nintent × weight × freq × semantic"]
        LABEL["Intent Label\n(hunger/connection/etc.)"]
    end

    subgraph OUTPUT["Output to Parent"]
        INSIGHT["Structured Insight:\n• Probable intent + confidence\n• Suggested response\n• Feature scores\n• Deviation level\n• Disclaimer"]
    end

    WAV --> PREPROCESSING
    PREPROCESSING --> FEATURE_EXT
    MFCC --> EMBED
    FEATURE_EXT --> BASELINE
    EMBED --> CLUSTERING
    COS --> THRESH
    THRESH -->|Yes| ATTACH
    THRESH -->|No| CREATE
    ATTACH --> INFERENCE
    CREATE --> INFERENCE
    BASELINE --> INFERENCE
    INTENTS --> CONF --> LABEL
    INFERENCE --> OUTPUT

    style INPUT fill:#e3f2fd,stroke:#2196F3
    style PREPROCESSING fill:#e8f5e9,stroke:#4CAF50
    style FEATURE_EXT fill:#fff3e0,stroke:#FF9800
    style BASELINE fill:#f3e5f5,stroke:#9C27B0
    style CLUSTERING fill:#e0f2f1,stroke:#009688
    style INFERENCE fill:#fce4ec,stroke:#E91E63
    style OUTPUT fill:#e8f5e9,stroke:#4CAF50
```

---

*Workflow diagrams version: MVP 1.0 — February 2026*
*All diagrams use Mermaid syntax — render in GitHub, VS Code (Mermaid extension), or https://mermaid.live*
