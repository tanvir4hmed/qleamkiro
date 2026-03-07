# Qleam Modernization Plan

## Vision
Transform Qleam from a rule-based, hand-tuned baby sound analyzer into a modern ML-powered system.

## The 6-Layer Architecture

```
COMPLETE SYSTEM

1. EARS (feature extraction)
   HuBERT (best for baby cry — proven Sep 2025 research)
   Input: raw audio waveform
   Output: 768-dim contextual embeddings
   Runs on: SageMaker Serverless (scales to zero)

2. BRAIN (classification)
   Small neural network trained on baby cry data
   Input: HuBERT embeddings + age_days (continuous)
   Output: hungry 70%, tired 20%, gas 10%
   Pre-trained on: Dunstan (1128) + DonateACry (457) + Baby Chillanto (2268)
   Runs on: Lambda (<1s inference)

3. GATE (early rejection)
   Lightweight acoustic checks (F0, RMS, energy)
   Silence? Adult? Noise? -> reject in <2s
   Only baby sounds reach EARS
   Runs on: Lambda (pennies)

4. LEARNING (self-training)
   Parent confirms -> quality gate -> anonymize -> store
   Retrain BRAIN when sample threshold reached
   Model weight shifts: research priors -> trained model as data grows
   Runs on: Step Functions + Lambda

5. PERSONALIZATION (per-child)
   Compare embeddings against child's own confirmed history
   Blend: 80% global model + 20% per-child similarity
   Runs on: Lambda (future phase)

6. INSIGHT (what parent sees)
   Dynamic conversational narrative (never repeats)
   Two radar charts (emotion match + acoustic features)
   Context-aware suggestions (time, history, what was tried)
   Dunstan reference with audio playback (0-3m only)
   Runs on: Lambda + React frontend
```

## Execution Flow

```
Audio Upload -> S3                           ~1-3s
  -> Lambda: GATE                            ~1-2s
     (quality check, silence/adult reject)
     |
  -> SageMaker Serverless: EARS              ~0.3-0.8s (GPU)
     (HuBERT 768-dim embeddings)
     |
  -> Lambda: BRAIN                           ~0.05s
     (classifier: embeddings + age_days)
     |
  -> Lambda: INSIGHT                         ~1-2s
     (format for parent)
     |
  -> Frontend polling                        ~1-2s
                                         ─────────
  TOTAL                                      ~4-8 seconds
```

## Current System Problems
1. **Redundant computation**: F0 computed 5 times, RMS 4 times across modules
2. **No early rejection**: Silence/adult/noise goes through full 13-25s pipeline
3. **Hand-tuned scoring**: Profiles + compound rules + signatures + conflict rules + priors = fragile hacks
4. **Dead code**: ~2500 lines across 5 unused modules
5. **Meaningless charts**: FeatureChart shows scores from unused evidence_model
6. **Static UI**: Same template, same advice every time for same emotion
7. **No real ML**: Nearest-centroid classifier with 80-sample minimum, never activated
8. **No training validation**: Current system accepts all data indiscriminately

## Three Layers of Age Handling

```
Layer 1: DATA STORAGE (granular)
  Store: age_days = 47
  Every sample has exact age. Maximum flexibility.

Layer 2: MODEL TRAINING (continuous)
  Input: audio_embedding + age_days (as number)
  Model learns: at age X, pattern Y = emotion Z
  No hard boundaries. Learns smooth transitions.
  Can discover: "neh reflex peaks at day 14-40, fades by day 70-100"

Layer 3: PARENT DISPLAY (simplified slots)
  0-3m:   "Newborn — reflex sounds dominant"
  3-6m:   "Early vocal — cooing and new sounds"
  6-12m:  "Babbling — syllable patterns emerging"
  12-24m: "First words — language developing"
  These are just UX labels. The model uses exact age_days internally.
```

## Why This Is Powerful

**Discovery potential**: With continuous age data, the model can discover things researchers haven't found. Research says "Dunstan neh reflex exists 0-3 months" — our data might show neh peaks at day 10-25, starts fading at day 50, some babies lose it by day 40 while others keep it to day 100. Slot-based analysis hides this detail.

**Self-correcting research**: World research says "Gas cry (eairh) is F0 400-660Hz for 0-6m". Our collected data from thousands of babies might show different ranges at different ages. The model automatically adjusts because it learned from continuous data, not slot-averaged research papers.

**Per-child growth tracking**: Track how each baby's patterns evolve day by day, detecting developmental transitions in real time.

## Phases

### Phase 1: Pipeline Cleanup & Early Rejection (GATE)
> Goal: Fast, clean pipeline. Remove dead code. Early reject non-baby sounds in <2s.

### Phase 2: HuBERT Feature Extraction + Pre-Training (EARS + BRAIN bootstrap)
> Goal: Deploy HuBERT on SageMaker Serverless. Pre-train classifier on public datasets (Dunstan + DonateACry + Baby Chillanto). Launch with a real model, not empty priors.

### Phase 3: Self-Training Pipeline & Anonymized Storage (LEARNING)
> Goal: Parent-confirmed data flows into anonymized training dataset. Quality gates. Auto-retrain.

### Phase 4: Age-Continuous Emotion Classifier (BRAIN refinement)
> Goal: Age-conditioned classifier using age_days as continuous input. Replace all rule-based scoring.

### Phase 5: Dynamic UI Overhaul (INSIGHT)
> Goal: Conversational insights, meaningful charts, context-aware suggestions, Dunstan playback.

### Phase 6: Child Deletion & Data Privacy
> Goal: Full GDPR/COPPA compliance. Delete audio on child removal. Anonymized training data stays.

---

See individual phase docs for detailed specs:
- [Phase 1](./PHASE_1_PIPELINE_CLEANUP.md)
- [Phase 2](./PHASE_2_HUBERT_PRETRAIN.md)
- [Phase 3](./PHASE_3_SELF_TRAINING.md)
- [Phase 4](./PHASE_4_AGE_CLASSIFIER.md)
- [Phase 5](./PHASE_5_DYNAMIC_UI.md)
- [Phase 6](./PHASE_6_PRIVACY.md)
- [Dead Code Inventory](./DEAD_CODE_INVENTORY.md)
- [Discussion Notes](./DISCUSSION_NOTES.md)
