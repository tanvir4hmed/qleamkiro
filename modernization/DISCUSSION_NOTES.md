# Discussion Notes - All Ideas & Decisions

This captures every decision made during planning. The source of truth for why things are the way they are.

---

## Decision 1: Stop Adding Extra Marks

The current system patches rule-based scoring with bonuses, priors, compound rules, and conflict resolvers. Every new edge case adds another hack (EMOTION_PROFILES_0_6M, _soft_range_match, _score_profiles, _derive_signatures, _apply_conflict_rules, prior biases like hungry=0.08, gas=0.00). The new system replaces ALL of this with a trained ML model that learns patterns from data. 970 lines of cry_analyzer.py -> ~100 lines.

## Decision 2: HuBERT Over wav2vec 2.0

September 2025 paper "Speech transformer models for extracting information from baby cries" (arXiv:2509.02259) tested multiple models specifically on baby cry:
> "Wav2Vec2 did not achieve the best result on any task when compared to UniSpeech and HuBERT."

HuBERT is the same architecture (self-supervised transformer, 768-dim, ~360MB), same cost, same infrastructure — but proven better for baby cry. No reason to use wav2vec 2.0.

Source: https://arxiv.org/abs/2509.02259

## Decision 3: No YAMNet as Separate Layer

Initially considered YAMNet (3MB, Lambda) as a "sound classification" middle layer between GATE and HuBERT. Rejected because:
- HuBERT embeddings + our classifier can classify sound type AND distinguish emotions — one model does both jobs
- Adding YAMNet = two model inferences instead of one, extra complexity for no gain
- The GATE layer handles quick rejection with cheap acoustic checks (F0, RMS) — no model needed for silence/adult/noise detection
- YAMNet knows "baby cry" as a class but can't distinguish emotions — doesn't solve our real problem

## Decision 4: Pre-Train on Public Datasets (Not Empty Launch)

Problem: wav2vec/HuBERT gives better EARS but without a trained BRAIN, the data is useless. A classifier with zero training data just guesses.

Solution: Pre-train the classifier on existing public baby cry datasets BEFORE launch.

Available datasets:
| Dataset | Samples | Labels | Source |
|---|---|---|---|
| Dunstan Baby Language | 1,128 | 9 emotion labels, 0-2yr | GitHub (donateacry corpus) |
| DonateACry | 457 (cleaned) | 5 emotion labels | GitHub open source |
| Baby Chillanto | 2,268 | 5 labels (medical grade) | CONACYT Mexico (request) |

Combined: ~3,500-4,000 labeled samples. Not huge, but enough for a real baseline.

What this means: Day 1 we launch with a classifier that actually learned from baby cry data, not with empty research priors or hand-tuned heuristics. Parent-confirmed data then makes it progressively better.

## Decision 5: Build Clean, Label Fresh

User collected audio data and ran it through the current (flawed) pipeline. Those extracted features are biased by the old system's thresholds and hand-tuned rules.

Decision: **Keep raw audio files, discard old extracted features.** The data_analysis Excel files in the repo are from the old pipeline and should NOT be used for the new system. When ready, re-process raw audio through HuBERT, then re-label with parent confirmation.

## Decision 6: Age as Continuous Input (Three Layers)

Baby development is continuous, not slot-based. A baby on day 89 and day 91 sound identical. Development is a gradient.

**Layer 1 — DATA STORAGE**: Store exact age_days = 47 in every record. Maximum granularity.
**Layer 2 — MODEL TRAINING**: age_days as continuous input with encoding:
```python
def encode_age(age_days):
    return [
        age_days / 730.0,               # normalized 0-1
        math.sin(age_days * pi / 90),   # ~3-month cycles
        math.sin(age_days * pi / 180),  # ~6-month cycles
        1.0 if age_days < 90 else 0.0,  # newborn hint
    ]
```
**Layer 3 — PARENT DISPLAY**: Slot labels for UX only (0-3m, 3-6m, 6-12m, 12-24m).

The model discovers age transitions from data. Research says "Dunstan neh exists 0-3m" — our data might show neh peaks at day 10-25, fades by day 50-100. Slots would hide this.

## Decision 7: Anonymized Training Data (Option A)

When audio enters training pipeline:
1. Extract: HuBERT embeddings + mel spectrogram + emotion label + age_days
2. Strip ALL PII: child_id, parent_id, session_id, S3 audio path
3. Store anonymized feature vector in training table (new UUID, no traceability)

On child deletion:
- Delete S3 audio files
- Delete session records, feedback records, training candidates
- Anonymized training features -> STAY (no PII, can't be traced back)
- Trained model -> STAYS (aggregated weights, no individual data)

This is standard practice in health ML under HIPAA/GDPR.

## Decision 8: SageMaker Serverless (Not Lambda) for HuBERT

HuBERT is ~360MB. Options considered:
- Lambda 10GB RAM: possible but slow cold start, memory pressure
- SageMaker Real-time GPU: $380/month always-on (overkill for our volume)
- **SageMaker Serverless**: scales to zero, pay per inference, ~$0.0001-0.0003 per call

Only baby sounds (~40% of uploads) hit SageMaker. The rest are rejected by GATE on Lambda in <2s. For 1000 sessions/month, SageMaker cost is ~$0.30-1.00.

## Decision 9: Dynamic UI (Not Static Templates)

Current InsightPanel shows same 3 cards every time. Problems identified:
1. "What to try" shows identical advice for same emotion — every time
2. Dunstan sounds won't always be present (only 0-3m)
3. Feels like reading a form, not interacting with AI

Solutions:
- **Narrative templates with data slots**: 5+ variants per emotion, filled with real acoustic measurements. Same emotion produces different text because different template + different data values.
- **Context-aware suggestions**: Tagged with conditions (time of day, hours since feed, session count, what was tried before). Selection excludes last 3 shown to this child. Escalation for repeated sessions.
- **Dunstan section**: Only shown for age_days <= 90. Hidden entirely for older babies. Includes audio playback of reference sounds (5 clips in S3).
- **Two real radar charts**: Emotion Match (7 axes from model probabilities) + Acoustic Features (6 axes from real measurements).
- **Progressive reveal**: CSS animations, content appears sequentially (badge -> narrative -> charts -> suggestions -> dunstan).

## Decision 10: 6-Layer Architecture

```
1. EARS    HuBERT on SageMaker Serverless (768-dim embeddings)
2. BRAIN   Classifier on Lambda (embeddings + age_days -> emotions)
3. GATE    Acoustic checks on Lambda (reject silence/adult/noise <2s)
4. LEARNING Parent confirms -> anonymize -> store -> retrain
5. PERSONALIZATION Per-child embedding similarity (future)
6. INSIGHT  Dynamic UI with narratives + charts + suggestions
```

Execution order: GATE first (cheap reject) -> EARS (only for baby sounds) -> BRAIN -> INSIGHT.

## Decision 11: Training Sample Structure

Every parent-confirmed sample stores:
```python
{
    "feature_id": "uuid",
    "hubert_embeddings_s3": "s3://...",
    "mel_spectrogram_s3": "s3://...",
    "age_days": 47,                   # EXACT, never a slot
    "confirmed_emotion": "hungry",
    "confirmation_source": "parent_correct",  # or parent_confirm
    "model_confidence_at_time": 0.82,
    "audio_quality_snr": 18.5,
    "duration_s": 7.2,
    "device_type": "iphone_14",
    "environment": "home_quiet",
    "created_at": "2026-03-07T...",
    # NO child_id, NO parent_id, NO session_id
}
```

## Decision 12: Performance Targets

| Scenario | Target | Current |
|---|---|---|
| Silence/adult/noise | <2s reject | 13-25s (processes everything) |
| Baby cry full analysis | 4-8s | 13-25s |
| Baby speech/laugh | 3-5s | 13-25s |

Breakdown for cry:
- Upload to S3: 1-3s
- GATE (Lambda): 1-2s
- EARS (SageMaker HuBERT): 0.3-0.8s (GPU, warm)
- BRAIN (Lambda classifier): <0.05s
- INSIGHT (Lambda): 1-2s
- Frontend polling: 1-2s

## Decision 13: Terraform for All Infrastructure

All new AWS resources created via Terraform so they can be easily moved or destroyed:
- SageMaker endpoint (HuBERT)
- DynamoDB tables (training_features, model_versions)
- EventBridge rules (training trigger)
- Step Functions (training pipeline)
- Lambda functions (training_check, model_trainer)
- IAM roles and policies
- S3 lifecycle rules

## Decision 14: Keep From Current System

Only these parts of the current codebase are worth keeping:
- **Audio download/load** (audio_utils.py download + load functions — just I/O)
- **Basic acoustic gate** (RMS threshold for silence, F0 range for adult — simple math)
- **Dunstan reference mapping** (static lookup table for 0-3m display text only — NOT scoring)
- **Speech transcriber** (for speech-type sessions, if it works)

Everything else: delete and replace with HuBERT + trained classifier.

## Decision 15: Model Weight Blending

As our own parent-confirmed data grows, shift from public-dataset model to our retrained model:

| Our Confirmed Samples | Public Dataset Weight | Our Data Weight |
|---|---|---|
| 0-29 | 100% | 0% |
| 30-99 | 70% | 30% |
| 100-299 | 40% | 60% |
| 300+ | 15% | 85% |

The Phase 2 model (trained on Dunstan + DonateACry + Chillanto) serves us on day 1 but gracefully fades as our own data proves more accurate.

---

## References

- HuBERT vs wav2vec 2.0 for baby cry: https://arxiv.org/abs/2509.02259
- Layer-wise features for infant cry (Mar 2025): https://link.springer.com/article/10.1007/s41870-025-02992-1
- DonateACry corpus: https://github.com/gveres/donateacry-corpus
- Baby Chillanto database: CONACYT Mexico
- ICSD dataset: https://arxiv.org/html/2408.10561v1
- DeepInfant V2: https://github.com/skytells-research/DeepInfant
- Kaggle Baby Cry Sense: https://www.kaggle.com/datasets/mennaahmed23/baby-cry-dataset
- HuBERT model: https://huggingface.co/facebook/hubert-base-ls960
- Baby cry CNN+MFCC (2025): https://www.mdpi.com/2076-3417/15/5/2648
