# AIdeas: QLEAM AI

Team Name: Qlitch  
Category: Daily Life Enhancement  
Cover Image: **Image: Cover - From Cry to Clarity (parent recording + live insight screen)**  
Tags: `#aideas-2025` `#daily-life-enhancement` `#APJC`

## App category
Daily Life Enhancement
Social Impact
Team Members : @swarupa26

Qleam AI fits Daily Life Enhancement because it supports one of the most stressful daily moments for new parents: understanding why a baby is crying. Instead of guesswork, parents get a clear, structured interpretation from a short recording, with practical response guidance in the same session.

## My vision
My vision is simple: make early child communication understandable in real life, not only in research papers.

I build Qleam AI as a parent-facing web app for children in the early development stage. A parent records a short audio clip, and the app turns that moment into a readable insight: detected sound type, likely cry emotion, confidence, acoustic explanation, and actionable suggestions. The system stays personalized by learning from confirmed parent feedback over time.

The core idea is that every child develops expressive patterns differently. Qleam AI treats this as a learning signal, not noise.

## Why this matters
The first years of life are intense for both babies and caregivers. Crying is frequent, ambiguous, and emotionally heavy. Parents often face repeated cycles of uncertainty, especially at night or in noisy home conditions.

Qleam AI matters because it improves day-to-day clarity:
- It reduces trial-and-error in immediate care decisions.
- It provides a consistent interpretation framework instead of random guesswork.
- It creates a feedback loop where the system improves from real parent-confirmed outcomes.

This is Daily Life Enhancement at a practical level: less confusion, faster response, better emotional confidence for families.

## How I built this
I build Qleam AI as a serverless, privacy-aware AWS pipeline with two complementary intelligence paths: a reliable rule path and a learning model path.

### Runtime architecture
- React frontend for recording, session history, and insight display
- Amazon Cognito for parent authentication
- Amazon API Gateway + AWS Lambda for app APIs
- AWS Step Functions for end-to-end orchestration
- Amazon S3 for session audio and model artifacts
- Amazon DynamoDB for session, feedback, and model lifecycle data
- SageMaker endpoint for HuBERT embedding extraction in advanced inference path

### Session processing flow
1. Parent records audio in browser and uploads securely to S3.
2. Processing pipeline runs quality checks, diarization, and sound classification.
3. If the recording is valid and cry-related, advanced inference extracts embeddings and predicts cry emotion probabilities.
4. Insight service generates the parent-facing output with emotion and acoustic context.
5. Parent feedback (correct/incorrect emotion) is captured and gated for training quality.

### Why the technical direction changes from the original Bedrock-first plan
The original concept starts from a Bedrock-centered idea. In implementation, I keep the core cry decision engine deterministic and model-driven for three reasons:
- lower latency for short-session feedback loops,
- easier quality control for safety-critical parenting guidance,
- better Free Tier cost discipline for continuous iteration.

This keeps the product responsive and testable while still delivering a strong AI experience.

### Self-learning model as the key milestone
Qleam AI uses a staged learning approach:
- A public baseline emotion model provides initial class behavior.
- Parent-confirmed samples are anonymized and converted into confirmed training data.
- Retraining promotes newer model versions when validation improves.

This turns Qleam AI from a static classifier into a continuously improving system. The most important milestone is not just predicting one session correctly, but improving interpretation quality across sessions as real household data accumulates.

### Development milestones reached
- End-to-end recording-to-insight pipeline in production-style serverless flow
- Robust reject handling for noisy or invalid audio
- Parent feedback loop with quality gates
- Retrain/validate/promote model lifecycle with version control
- Frontend experience with confidence and acoustic explainability

## Demo
Use these visuals in order so readers follow the journey from recording to learning.

- **Image: 1 - Home screen with child profile and Record Session button**
- **Image: 2 - Recording in progress (timer + upload transition)**
- **Image: 3 - Session insight headline (emotion, confidence, guidance)**
- **Image: 4 - Emotion Match radar and Acoustic Analysis radar side by side**
- **Image: 5 - Feedback modal (Was this correct? + corrected emotion selection)**
- **Image: 6 - Session history timeline showing multiple insights**
- **Image: 7 - Model learning view (version progression / training contribution snapshot)**
- **Image: 8 - Mobile view of the same insight flow**

Optional short video:
- **Video: 0:00-4:30 - Record -> Analyze -> Feedback -> Updated insight journey**

## What I learned
I learn five practical lessons while building Qleam AI:

1. **Personalization beats one-size-fits-all for baby communication.**  
   Cry patterns vary by child and context, so the feedback loop is essential.

2. **Data quality gates are as important as model architecture.**  
   If poor audio enters training, model quality drifts quickly.

3. **Parents trust systems that explain themselves.**  
   Confidence + acoustic context + actionable suggestions increase clarity and usability.

4. **A hybrid path is stronger than a single path.**  
   Combining robust fallback logic with model inference keeps the product reliable in real-world conditions.

5. **Continuous learning is the real product advantage.**  
   The biggest value is cumulative: the system improves from confirmed outcomes instead of staying fixed after launch.


