# Phase 4: Age-Continuous Emotion Classifier (BRAIN Refinement)

## Goal
Upgrade the BRAIN classifier to use age_days as continuous input alongside HuBERT embeddings. This is what makes our system genuinely better than any existing research — the model learns age-specific patterns from continuous data, not arbitrary slot boundaries.

## Prerequisites
- Phase 2 complete (HuBERT deployed, initial classifier working)
- Phase 3 complete (training pipeline storing confirmed data with age_days)
- Minimum ~100 confirmed samples with age_days to start seeing age benefit

## Why Age-Conditioned Classification Matters

Baby development is continuous, not slot-based:

```
Day 1   ████                    Pure reflex cries
Day 30  ████                    Still reflex, slightly varied
Day 60  ███▓                    Early cooing appearing alongside cry
Day 89  ███▓▓                   More variation
Day 90  ███▓▓                   <- Nothing magically changes here
Day 91  ███▓▓                   Same baby, one day older
Day 120 ██▓▓▓                   Dunstan reflexes fading
Day 180 █▓▓▓▓▓                  Canonical babbling emerging
Day 365 ░▓▓▓▓▓▓▓▓              First words mixing with cries
```

The same audio pattern means different things at different ages:
- High-pitched rhythmic cry at day 30 = very likely hunger (neh reflex strong)
- Same pattern at day 80 = still likely hunger but less certain (reflex fading)
- Same pattern at day 150 = could be frustration (neh gone, new patterns)

No manual slot boundaries. The model discovers when transitions happen from the data.

## Model Architecture

```
Input 1: HuBERT embeddings (768-dim)     Input 2: age_days
         |                                        |
    [Dense 256, ReLU]                      Age encoding:
    [Dense 128, ReLU]                        age_days / 730.0 (normalized 0-1)
    [Dropout 0.3]                            sin(age_days * pi / 90)  (~3m cycles)
         |                                   sin(age_days * pi / 180) (~6m cycles)
         |                                   1.0 if age_days < 90 else 0.0 (newborn hint)
         |                                        |
         |                                   [Dense 16, ReLU]
         |                                   [Dense 8, ReLU]
         |                                        |
         +----------------+-----------------------+
                          |
                    [Concatenate: 128 + 8 = 136]
                    [Dense 64, ReLU]
                    [Dense 32, ReLU]
                    [Dense 7, Softmax]
                          |
                    Emotion Probabilities
                    (hungry, tired, discomfort,
                     gas, pain, overstimulated, content)
```

### Why This Age Encoding

```python
def encode_age(age_days):
    return [
        age_days / 730.0,               # normalized 0-1 for 0-24 months
        math.sin(age_days * pi / 90),   # captures ~3-month developmental cycles
        math.sin(age_days * pi / 180),  # captures ~6-month developmental cycles
        1.0 if age_days < 90 else 0.0,  # is_newborn hint (Dunstan period)
    ]
```

- **Normalized age**: smooth gradient, model sees continuous progression
- **Sin cycles**: capture known developmental milestones (~3m Dunstan fade, ~6m babbling onset)
- **Newborn flag**: explicit signal for Dunstan-relevant period
- The model learns which encoding matters most — we provide the raw signals

## Emotion Classes (7)

1. **hungry** — rhythmic, builds in waves, neh quality (0-3m)
2. **tired / sleepy** — whiny, lower pitch, owh quality (0-3m)
3. **discomfort** — sharp, irregular, heh quality (diaper, temperature, position)
4. **gas / colic** — tense, high-pitched, eairh quality (0-3m), drawn out
5. **pain** — sudden, high-intensity, piercing
6. **overstimulated** — fussy, erratic, hard to console
7. **content / fussy** — low-intensity, no clear distress

## What This Replaces

### Current cry_analyzer.py (970 lines) contains:
- EMOTION_PROFILES_0_6M (hand-tuned weighted rules per emotion)
- _soft_range_match, _score_profiles, _derive_signatures
- _apply_conflict_rules
- Prior biases (hungry=0.08, gas=0.00) — manually pushing scores
- Compound rules and signature detection
- All the "adding extra marks" logic

### New cry_analyzer.py (~100 lines):
```python
def analyze_cry(hubert_embeddings, age_days, model_version=None):
    """
    Returns emotion probabilities from trained age-conditioned model.
    Falls back to Phase 2 model (no age) if age-conditioned model not ready.
    """
    age_features = encode_age(age_days)

    if model_version and age_conditioned_model_exists(model_version):
        # Phase 4 model: HuBERT embeddings + age_days
        emotion_scores = run_age_model(hubert_embeddings, age_features, model_version)
    elif base_model_exists():
        # Phase 2/3 model: HuBERT embeddings only (no age input)
        emotion_scores = run_base_model(hubert_embeddings)
    else:
        # Should not happen after Phase 2, but safety fallback
        emotion_scores = research_baseline(age_days)

    return {
        "emotions": sorted_by_score(emotion_scores),
        "top_emotion": top_emotion(emotion_scores),
        "confidence": max(emotion_scores.values()),
        "also_possible": second_and_third(emotion_scores),
        "dunstan_sound": dunstan_lookup(age_days) if age_days <= 90 else None,
    }


def dunstan_lookup(age_days):
    """Static lookup for 0-3m Dunstan display text only. NOT used for scoring."""
    # This is just for the UI — showing "Sounds like Neh" with play button
    # The actual classification comes from the trained model above
    return DUNSTAN_MAP.get(...)  # simple mapping
```

**970 lines -> ~100 lines.** One model replaces profiles + compound rules + signatures + conflict resolution + priors.

## Training Pipeline (Extends Phase 3)

### Data Preparation
1. Query DynamoDB training_features table (all confirmed samples)
2. Load HuBERT embeddings from S3
3. Now include age_days in feature vector (Phase 3 model didn't use it)
4. Group by confirmed_emotion, check class balance
5. Augment underrepresented classes:
   - Time stretch (0.9x - 1.1x)
   - Pitch shift (+/- 1 semitone)
   - Add background noise
   - Age jitter (+/- 3 days) for age augmentation

### Training
- Input: [768-dim HuBERT embeddings, 4-dim age encoding]
- Output: 7-class softmax
- Optimizer: Adam, lr=0.001 with schedule
- Loss: categorical cross-entropy
- Batch size: 32
- Epochs: 50 with early stopping (patience=10)
- Framework: TensorFlow -> export to TFLite for Lambda

### Validation & Promotion
- Track per-emotion accuracy, precision, recall
- Track per-age-group accuracy (for monitoring, not for model architecture)
- Only promote if overall accuracy >= current model
- Also check: no single emotion drops below 50% recall (prevent class collapse)
- Store model version in S3: `models/emotion-classifier-age/v{N}/model.tflite`

## Discovery Potential

With continuous age data, the model can discover what researchers haven't:

```
Research says: "Dunstan neh reflex exists 0-3 months"

Our data might show:
  - neh is strongest at day 10-25
  - neh starts fading at day 50, not day 90
  - some babies lose neh by day 40, others keep it to day 100
  - there's a NEW pattern at day 35-60 that nobody documented
```

```
Research says: "Gas cry (eairh) is F0 400-660Hz for 0-6m"

Our collected data might show:
  - At day 1-14: eairh is actually F0 450-700Hz (higher than research)
  - At day 30-60: F0 400-620Hz (matches research)
  - At day 70-90: F0 380-580Hz (research missed this decline)
```

We can't discover this if we group everything into "0-3m" slots. The slot hides the detail.

## Per-Child Growth Tracking (Layer 5: PERSONALIZATION preview)

```
Baby Emma:
  Day 15: neh detected (confidence 0.85)
  Day 30: neh detected (confidence 0.90) — peak
  Day 45: neh detected (confidence 0.72) — fading
  Day 55: neh detected (confidence 0.45) — almost gone
  Day 60: new vocalization pattern emerging
  Day 75: cooing detected alongside cry

-> "Emma's hunger signal is transitioning. She's developing
    new ways to communicate. This is normal development."
```

This requires storing per-child embeddings (Phase 5/6 handles privacy of these).

## Tasks

### 4.1 Implement Age Encoding
- `shared/age_encoder.py`: `encode_age(age_days)` -> 4-dim vector
- Normalized age + sin cycles + newborn flag
- Unit tests for edge cases (day 0, day 730, negative)

### 4.2 Upgrade Classifier Architecture
- Modify `shared/emotion_classifier.py` to accept age input
- Two-branch architecture: embedding branch + age branch -> concatenate -> classify
- Export to TFLite with both inputs

### 4.3 Update Training Script
- `scripts/train_emotion_model.py` now includes age_days in training
- Age augmentation (+/- 3 days jitter)
- Per-age-group accuracy monitoring

### 4.4 Rewrite cry_analyzer.py
- Remove ALL hand-tuned profiles, rules, priors, compound rules, signatures, conflict resolution
- New: load TFLite model, run inference with embeddings + age_days
- Keep ONLY Dunstan lookup for 0-3m display text (not scoring)
- ~100 lines replacing ~970 lines

### 4.5 Update insight_generator
- Receives emotion probabilities directly from classifier (not from rule-based scoring)
- Top emotion + confidence from model softmax
- also_possible from 2nd/3rd highest probabilities
- No more conflict resolution needed — model handles overlapping patterns
- age_days flows through to insight text generation

### 4.6 Model Serving
- TFLite model (~2MB) loaded from S3 at Lambda cold start
- Cached in /tmp for warm invocations
- Inference: <50ms on Lambda (just dense layers on 772-dim input)

## Infrastructure (Terraform)
- No new resources — reuses Phase 3 model_versions table and training pipeline
- Update model_trainer Lambda to include age-conditioned architecture
- Update Step Function if needed for new training parameters

## Success Criteria
- age_days used as continuous input (no slot boundaries in model)
- cry_analyzer.py reduced from 970 lines to ~100 lines
- Zero hand-tuned profiles, rules, or priors in scoring path
- Per-age-group accuracy tracked (monitoring, not architecture)
- Model discovers age-specific patterns from data
- Inference latency <50ms on Lambda (classifier only, not including HuBERT)
- End-to-end still 4-8 seconds

## Deploy
- Workflows: `2-lambda-deploy` (updated cry_analyzer, classifier, insight_generator)
