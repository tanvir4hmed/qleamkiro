# Qleam — Master Research & Build Index
## Start Here. Everything You Need to Know Is in This File.

**Last Updated:** February 2026
**Status:** Phases 0–8 complete. Phase 9 (UI Rebuild) is next.
**Build Progress:** Phase 0 ✅ | Phase 1 ✅ | Phase 2 ✅ | Phase 3 ✅ | Phase 4 ✅ | Phase 5 ✅ | Phase 6 ✅ | Phase 7 ✅ | Phase 8 ✅ | Phase 9 🔲
**Purpose:** This document is the single entry point for anyone — including future AI sessions with no chat history — to understand the complete project, what has been decided, what needs to be built, and in what order.

---

## Table of Contents

1. [What This Project Is](#1-what-this-project-is)
2. [The Foundational Inputs — Baby Profile](#2-the-foundational-inputs--baby-profile)
3. [Document Map — What Each File Contains](#3-document-map--what-each-file-contains)
4. [Current System State — What Exists vs What Is Needed](#4-current-system-state--what-exists-vs-what-is-needed)
5. [Key Design Decisions — Locked and Final](#5-key-design-decisions--locked-and-final)
6. [Complete Phase-by-Phase Build Plan](#6-complete-phase-by-phase-build-plan)
7. [Age-Wise Feedback Schema — How Feedback Evolves With the Baby](#7-age-wise-feedback-schema--how-feedback-evolves-with-the-baby)
8. [Stage-Aware UI — What the App Shows at Each Stage](#8-stage-aware-ui--what-the-app-shows-at-each-stage)
9. [Data Storage Principles — What Is Stored and Why](#9-data-storage-principles--what-is-stored-and-why)
10. [Infrastructure Decisions](#10-infrastructure-decisions)
11. [Writing Guide — Papers, Blogs, Articles](#11-writing-guide--papers-blogs-articles)

---

## 1. What This Project Is

Qleam is an AI system that learns a baby's private language from birth. Every baby develops a unique communication system before conventional language exists — specific sounds for specific needs, shaped by their anatomy, environment, and caregivers. This system is currently invisible to science and to parents. Qleam makes it visible.

The app records a baby's vocalizations. It analyzes the audio using physics-based acoustic signal processing, validates that the recording is genuinely from an infant (not an adult, not background noise), identifies which enrolled baby is speaking, and generates an insight about what the baby is communicating. Over time, across hundreds of sessions, it builds a personal concept graph of everything this baby knows and how they express it. Eventually it can decode a stream of pre-linguistic sounds in real time — "meh meh wawa bah" becomes "asking for water before lunch" — because it has learned this specific child's private language from day zero.

As the child grows into language (approximately 24–36 months), the app transitions from intent translation to language development tracking. The insight changes from "baby may be hungry" to "your child used a complete sentence — language milestone." The app never stops being useful — it grows with the child.

At scale, the data from thousands of children — acoustically rich, longitudinally tracked, parent-confirmed, context-annotated — becomes a scientific dataset that does not exist anywhere in developmental psychology research. It enables new mathematical theories of language emergence, replaces outdated static research categories with data-driven ones, and potentially contributes to PhD-level and publishable research.

**The three goals, in order of dependency:**
1. Accurate per-session insight (what is this baby communicating right now)
2. Private language extraction (what is this baby's personal signal system)
3. Scientific contribution (what does this data reveal about how language begins)

---

## 2. The Foundational Inputs — Baby Profile

**Birth date is the single most important data point in the entire system.**

Every layer of analysis — feature interpretation, confidence scoring, developmental stage classification, feedback UI rendering, concept graph activation, language emergence detection — is calibrated against developmental age. Without birth date, the system cannot know whether a recording is from a 3-month-old or a 24-month-old. These require completely different analysis pipelines.

### Required Baby Profile Inputs (at registration)

```
baby_profile = {
  baby_name:      string        ← Display name. Used in all parent-facing text.
                                   "Your baby" → "Emma's sounds show..."
  birth_date:     ISO date      ← THE CORNERSTONE. Drives developmental stage,
                                   feature interpretation, UI mode, feedback schema,
                                   confidence calibration, concept graph activation.
  parent_id:      string        ← Account link. Drives trust scoring.
  enrolled_at:    timestamp     ← Session 1 date. Baselines start here.
}
```

### How Birth Date Drives Everything

```
At every session:
  age_days    = today - birth_date
  age_months  = age_days / 30.44

  developmental_stage = classify(age_months, acoustic_features)
    → NEWBORN        (0–2m)
    → YOUNG_INFANT   (2–6m)
    → OLDER_INFANT   (6–12m)
    → TODDLER_EARLY  (12–18m)
    → TODDLER_MID    (18–24m)
    → TODDLER_LATE   (24–36m)
    → PRESCHOOL      (36m+)

  Stage determines:
    → Which analysis pipeline runs (pre-linguistic / transition / linguistic)
    → Which features are interpreted how
    → What confidence range is appropriate
    → What the feedback UI shows
    → What questions are asked
    → Whether concept graph is active
    → What "insight" means (need translation vs language development)
```

### Why Baby Name Matters

Not just display. Baby name is used in:
- All insight text ("Emma's sounds show..." not "your baby's sounds show...")
- Journey view timeline ("Emma's first canonical babble: Age 6m 12d")
- Developmental progress page ("Emma is in the canonical babbling stage")
- Proto-word detection ("Emma has developed a consistent water signal")

Every piece of parent-facing text should feel personal, not generic.

---

## 3. Document Map — What Each File Contains

### `MASTER_INDEX.md` ← **YOU ARE HERE**
The single entry point. Project overview, all decisions, complete build plan, writing guide. Read this first every session.

### `RESEARCH_VISION_2.0.md` (95 KB, ~2100 lines)
The master scientific and architectural vision. Contains:
- Full system description across 18 sections
- All 9 processing layers with inputs, outputs, dependencies
- Three-source evidence model (acoustic + research + feedback)
- Parent feedback trust and delta scoring system
- Personal concept graph design
- Stream decoder architecture
- Developmental lifecycle (birth → sentences)
- Environmental and contextual data strategy
- Population model and federated learning design
- Mathematical framework (Bayesian, VTL, CBR, phase transition)
- Complete implementation task breakdown by phase
- Data collection strategy
- Ethical framework
- Long-term AI companion vision including Bedrock model decision

**Use for:** Full system understanding, architecture decisions, feature design

### `PHD_RESEARCH_FRAMEWORK.md` (59 KB, ~542 lines)
Complete PhD thesis proposal in standard scientific format. Contains:
- Structured abstract
- Literature review (Wolff 1969, Thelen 1994, Smith & Yu 2008, McMahan FedAvg, etc.)
- 5 formal Research Questions (RQ1–RQ5)
- 7 novel scientific contributions with novelty statements
- Theoretical framework
- Methodology and evaluation strategy
- Ethical considerations (GDPR Article 6, COPPA, IRB)
- 30+ APA-formatted references

**Use for:** PhD proposal, academic papers, grant applications, literature grounding

### `TECHNICAL_PIPELINE.md` (74 KB, ~1797 lines)
Complete technical specification. Contains:
- ASCII system architecture diagram
- Three pipeline stages (pre-linguistic / transition / linguistic)
- Each layer (0–9) with input schemas, algorithms, output schemas, error conditions
- Component correlation map (dependency graph)
- Four-dataset ecosystem (old research → population → individual → private language)
- Cold start solution (day 1 accuracy without individual data)
- Concept graph DynamoDB schema and all operations
- Stream decoder algorithm
- Federated learning with differential privacy
- AWS infrastructure cost model
- 7 identified gaps from audio science literature

**Use for:** Implementation reference, developer handoff, technical articles

### `SCIENTIFIC_MATHEMATICS.md` (56 KB, ~935 lines)
PhD-quality mathematical treatment. Contains:
- All equations numbered (1.1 → 12.16)
- Theorem 3.1: Acoustic Separability (infants always separable from adults — proved)
- Theorem 8.1: Trust score convergence proof
- Theorem 10.1: Differential privacy guarantee (ε=1.0, δ=1e-5)
- Theorem 10.2: Federated learning convergence bound O(1/√T)
- Theorem 11.1: Acoustic Individuality Bound (< 1% confusion after 20 sessions)
- Theorem 11.2: Minimum Observation Bound (~13 sessions for reliable concept mapping)
- Phase transition model (φ order parameter)
- Trust-Weighted Kalman Filter (new method)
- Developmental Trajectory ODE (new method)
- All evaluation metrics formally defined

**Use for:** PhD dissertation mathematics chapters, journal papers, conference papers

---

## 4. Current System State — What Exists vs What Is Needed

### Confirmed Build State (as of February 2026)

Phases 0–4 are complete. The table below reflects confirmed codebase state.

| Component | Status | Phase | Notes |
|---|---|---|---|
| Audio recording (frontend) | ✅ Complete | 0 | WebM/WAV via MediaRecorder |
| Feature extraction Lambda | ✅ Complete | 3 | 65+ features across 8 groups (was 4) |
| MFCC embedding (26-dim) | ✅ Complete | 0 | Used for clustering |
| Cluster engine | ✅ Complete | 0 | Cosine similarity, threshold 0.85 |
| Insight generator Lambda | ✅ Complete | 4 | Three-Source Evidence Model v2 |
| Amazon Bedrock (Claude 3.5 Haiku) | ✅ Complete | 0 | Natural language output; LINGUISTIC mode uses separate prompt |
| Parent feedback (3 inputs) | ✅ Complete | 4 | response_type, effectiveness, word_token, notes, stage fields |
| Reinforcement weights | ✅ Complete | 0 | +0.10 helpful, -0.02 neutral, -0.05 ineffective |
| EMA baseline | ✅ Complete | 0 | α=0.3 default |
| Step Functions state machine | ✅ Complete | 0 | extract → cluster → insight |
| DynamoDB tables | ✅ Complete | 4 | Sessions, clusters, baselines, feedback, semantic_bridge, concept_graph, milestones |
| S3 audio storage | ✅ Complete | 0 | Raw audio files |
| Baby profile | ✅ Complete | 1 | birth_date, baby_name, parent_trust_score, context_reliability stored |
| Audio quality gate (Layer 0) | ✅ Complete | 1 | SNR≥10dB, duration≥3s, silence<0.80, clipping<0.5% |
| Biological validation (Layer 1) | ✅ Complete | 1 | F1–F4 formants, VTL via mean spacing, Bayesian threshold 13.0cm |
| Speaker diarization | ✅ Complete | 2 | Segment-level infant/adult classification |
| Enrolled baby verification | ✅ Complete | 2 | Cosine similarity against session history |
| Developmental mode detection | ✅ Complete | 2 | PRE_LINGUISTIC / TRANSITION / LINGUISTIC routing |
| Context collection | ✅ Complete | 3 | Feeding time, health state, environment from parent |
| Rich feature extraction (65+) | ✅ Complete | 3 | 8 groups: prosodic, voice quality, MFCC, spectral, temporal, formant, cry/babble, CBR |
| Formant extraction (F1–F4) | ✅ Complete | 1/3 | Via LPC; F4 added for correct VTL formula |
| Three-Source Evidence Model | ✅ Complete | 4 | 60% acoustic + 15% research + 25% feedback×FRS×DS |
| Research priors (stage-specific) | ✅ Complete | 4 | 8 developmental stages, context-adjusted |
| Expected Feedback Profile (EFP) | ✅ Complete | 4 | Stored before parent sees result |
| Parent trust score (FRS) | ✅ Complete | 4 | EMA α=0.15, stored per child profile |
| Delta scoring | ✅ Complete | 4 | DS = 0.60×RMS + 0.40×EPS in feedback_processor |
| Honest confidence scoring | ✅ Complete | 4 | Caps: 0.92 always, 0.40 ≤5 sessions, 0.35 weak signal |
| LINGUISTIC mode insight | ✅ Complete | 4 | Separate pipeline for 24m+ children |
| Concept graph (DynamoDB table) | ✅ Complete | 4 | Table exists, universal concepts pre-populated at registration |
| Milestones table | ✅ Complete | 4 | Table exists, 10 milestone types defined |
| NLP on free text | ✅ Complete | 5 | nlp_processor Lambda; Bedrock extraction of intent + objects |
| Concept graph operations | ✅ Complete | 5 | upsert_concept, get_concepts, pre_populate; concept_decoder Lambda |
| Stage-aware feedback (backend) | ✅ Complete | 5 | notes/stage fields forwarded through API → feedback_processor → NLP |
| Developmental stage tracking | ✅ Complete | 6 | developmental_tracker Lambda; CBR EMA, φ order parameter |
| Proto-word crystallisation | ✅ Complete | 6 | 5-criteria check in proto_word.py; concept_decoder Lambda |
| Milestone logging | ✅ Complete | 6 | milestones_table; 10 milestone types; logged by developmental_tracker |
| Speech analysis pipeline | ✅ Complete | 7 | speech_analyzer Lambda; MLU, vocab diversity, pragmatic classification |
| Language development insight | ✅ Complete | 7 | LINGUISTIC mode in insight_generator; separate Bedrock prompt |
| Population model / federated | ✅ Complete | 8 | federated_aggregator Lambda; FedAvg + DP noise (ε=1.0, δ=1e-5); stage-stratified |
| FL population prior injection | ✅ Complete | 8 | evidence_model.py accepts population_prior; insight_generator loads from DynamoDB |
| Stage-aware UI | 🔲 Pending | 9 | Journey view, private language page, progress page |

---

## 5. Key Design Decisions — Locked and Final

These are resolved. Do not re-debate unless new scientific evidence changes the reasoning.

### Evidence Model
```
Intent Score = 0.60 × Acoustic Signal
             + 0.15 × Research Prior      ← never eliminated, permanent contribution
             + 0.25 × Feedback × FRS × DS ← trust and delta modulated
```
Research prior floor: 0.10 minimum always. Research is never discarded.

### Feedback Storage
Raw feedback is **never deleted**. Even when trust score reaches zero. The record is needed for:
- Trust score recovery and re-evaluation
- Population model integrity
- Research dataset ground truth
- Pattern detection across time

### Trust Score Visibility
**Parents never see their trust score.** Protection is invisible. The only user-facing signal is "Want to update your feedback?" when a mis-click is suspected.

### Confidence Honesty
- FLOOR: 0.10 (never zero certainty)
- CAP: 0.92 (never claim certainty)
- Early sessions (< 5): HARD CAP at 0.40 regardless of formula
- Weak acoustic signal: HARD CAP at 0.35 regardless of formula

### Model Infrastructure
- **Amazon Bedrock — Claude 3 Haiku** for natural language generation
- Credits confirmed: "Amazon Bedrock" is in AWS credits eligible services list
- All on-demand Bedrock invocations are credit-deductible
- Do NOT use Provisioned Throughput (different billing, not credit-eligible)
- Migration path at scale: Amazon Nova Lite (~4x cheaper, sufficient quality)

### Baby Profile
- **Birth date is required, not optional.** Without it the system cannot determine developmental stage, which drives every pipeline decision.
- **Baby name is required.** Every parent-facing insight uses it. "Your baby" is never acceptable when we know the name.

### Feedback Schema
- Flexible, stage-tagged JSON payload — not fixed fields
- Schema varies by developmental stage
- `developmental_stage` field tells the system how to interpret the payload
- Stage is determined by birth date + acoustic evidence, not parent input

---

## 6. Complete Phase-by-Phase Build Plan

Each phase is one build command. I (the AI) handle all internal dependencies within a phase. The user tests and confirms between phases before proceeding to the next.

---

### Phase 0 — Audit ✅ COMPLETE
**Command:** "Run Phase 0"
**What I do:**
- Read every Lambda handler
- Read every DynamoDB table schema
- Read every Step Functions state machine definition
- Read every frontend component related to recording, feedback, insight display
- Read baby profile schema — confirm if birth_date exists
- Produce exact gap list: what exists, what is missing, what needs modification vs creation
- Confirm the build plan is accurate before any code is written

**Output:** Confirmed gap analysis document, exact file list, confirmed Phase 1–9 scope
**You do:** Review, confirm, say "Build Phase 1"

---

### Phase 1 — Foundation Gates ✅ COMPLETE
**Command:** "Build Phase 1"
**Depends on:** Phase 0 confirmed
**What gets built:**

**Layer 0 — Audio Quality Gate:**
- SNR (Signal-to-Noise Ratio) measurement per recording
- Clipping detection
- Duration validation (minimum: 3 seconds, maximum: 60 seconds)
- Silence ratio check (reject if > 80% silence)
- Lombard Effect flag (background noise affecting vocalization)
- Rejection pipeline with parent-facing message per rejection reason

**Layer 1 — Biological Validation (Physics Gate):**
- Formant extraction F1, F2, F3, F4 using LPC peak-picking
- Vocal Tract Length (VTL) estimation: `VTL = c / (2 × mean_formant_spacing)`
- Temperature correction: `c = 331 + 0.6 × T_celsius`
- Adult VTL threshold: reject if VTL > 12cm
- F0 range classification: reject if median F0 < 250Hz
- Sound type classifier: reject if not infant vocalization
- Nonlinear dynamics check for adult cry mimicry detection
- All gates run BEFORE any intent analysis
- Step Functions updated: add validation state before extraction

**Baby Profile:**
- Confirm birth_date field exists in registration flow
- If missing: add birth_date and baby_name as required fields at registration
- Add developmental age calculation utility: `age_months = (today - birth_date) / 30.44`
- Add stage classifier based on age_months + acoustic confirmation

**Output:** No adult recordings ever produce insights. Every session has a validated developmental stage.
**You do:** Test with your own voice. Confirm rejection. Test with real baby recording. Confirm pass.

---

### Phase 2 — Speaker Identity ✅ COMPLETE
**Command:** "Build Phase 2"
**Depends on:** Phase 1 complete and tested

**Layer 2A — Speaker Diarization:**
- Segment recordings by speaker
- Age group classifier per segment (infant / child / adult)
- Extract only infant segments for downstream analysis
- Flag presence of other speakers in session metadata

**Layer 2B — Enrolled Baby Verification:**
- Build embedding verification model from session history
- Verification score: `cosine_similarity(new_embedding, enrolled_centroid) × stage_consistency × session_confidence`
- Session-count-aware threshold: low threshold first 5 sessions, standard from session 6
- Parent notification when identity is uncertain (not accusatory)

**Layer 2C — Developmental Mode Detection:**
- Linguistic vs pre-linguistic mode classifier
- `MODE_PRELINGUISTIC` / `MODE_TRANSITION` / `MODE_LINGUISTIC`
- Detection signals: CBR, VOT patterns, utterance structure, F0 sentence-level contours
- Pipeline routing based on mode
- Session schema updated: add `mode` field

**Output:** Every session knows who is speaking and what developmental mode applies.

---

### Phase 3 — Context Collection + Rich Feature Extraction ✅ COMPLETE
**Command:** "Build Phase 3"
**Depends on:** Phase 2 complete

**Layer 3 — Context Collection:**
- Pre-session parent questionnaire (3 taps max):
  - Time since last feeding: `< 1h / 1-2h / 2-4h / 4h+`
  - Health state: `well / mild cold / fever / ear issue`
  - Environment: `home quiet / home noisy / car / outside`
- Weather API integration (temperature, humidity — single lightweight call)
- Context bundle stored with every session
- Lombard correction applied using context SNR data

**Layer 4 — Rich Feature Extraction (replaces current 4 features):**
Current 4 → New 50–80 features:

*Temporal:* RMS envelope, ZCR, onset strength, silence ratio, bout length, burst frequency, ADSR shape
*Spectral:* Centroid, bandwidth, rolloff, flux, flatness, contrast, harmonic ratio
*Cepstral:* MFCCs 1–13 (expand), delta MFCCs, delta-delta MFCCs, LPC coefficients
*Formant:* F1, F2, F3, F4 frequencies, bandwidths, F2 slope (from LPC)
*Pitch:* F0 trajectory, F0 range, F0 variability, contour shape, jitter, shimmer
*Voice quality:* HNR, breathiness index, creakiness, VOT, strain index
*Developmental:* Phonation type, CBR, syllable structure, intonation contour class
*Nonlinear:* Lyapunov exponent, bifurcation detection, recurrence quantification

Feature vector: 26-dimensional → 50–80 dimensional
Stored in session record, used for all downstream analysis.

**Output:** Every session has full contextual metadata and complete acoustic picture.

---

### Phase 4 — Insight Engine Rebuild ✅ COMPLETE
**Command:** "Build Phase 4"
**Depends on:** Phase 3 complete

**Three-Source Intent Classification:**
- Remove hard-coded rule-based intent mapping
- Implement full TSE (Three-Source Evidence) model:
  - Acoustic score from Phase 3 features (weight: 0.60)
  - Research prior lookup (weight: 0.15 fixed floor)
  - Feedback score × trust × delta (weight: 0.25 × FRS × DS)
- Context-adjusted Bayesian classification
- Dimensional output: arousal × valence (not discrete categories)
- Top-3 intent display with weights always

**Expected Feedback Profile (EFP):**
- Computed and stored BEFORE parent sees any result
- Records what the system expects the parent should report
- Stored in `feedback` table: `expected_feedback_profile` field

**Parent Feedback Trust System (FRS):**
- Trust score per parent account (initial: 0.50)
- EMA update: `FRS(t) = EMA(alignment_score, α=0.15)`
- Mis-click detection: submission_speed < 2000ms → MISCLICK flag
- Pattern detection: uniform responses across diverse sessions → LOW_INFORMATION flag

**Delta Scoring:**
- Computed after parent responds
- Response Match Score (RMS) + Effectiveness Plausibility Score (EPS)
- `Delta Score = 0.60 × RMS + 0.40 × EPS`
- Stored in feedback record

**Honest Confidence Scoring:**
- 7-factor formula replacing current simple formula
- Hard cap 0.40 for first 5 sessions
- Hard cap 0.35 for weak acoustic signals
- Session-count calibration factor: `min(sessions / 20, 1.0)`

**Health Deviation Flagging:**
- Acoustic patterns deviating from personal baseline in health-consistent ways
- Parent-facing: "Something sounds different — worth noting if you're concerned"
- Never a diagnosis

**Output:** Insight engine is accurate, honest, multi-source, trust-aware.

---

### Phase 5 — Concept Graph + NLP + Evolved Feedback ✅ COMPLETE
**Command:** "Build Phase 5"
**Depends on:** Phase 4 complete

**Personal Concept Graph Engine:**
- New DynamoDB table: `concept_graph`
  - `PK: child_id, SK: concept_id`
  - Fields: label, category, first_appeared, acoustic_clusters[], context_signatures[], confidence, confirmation_count, parent_descriptions[]
- Universal layer pre-populated at baby registration:
  - hunger, thirst, sleep, discomfort, pain, cold, hot, connection, attention, comfort, fear
- Personal layer: created from parent free text + acoustic emergence signals
- Concept node operations: add, link_cluster, update_confidence, fade_unused

**NLP Pipeline for Parent Free Text:**
- New Lambda: `nlp_processor`
- Intent and object extraction from free text
- Uncertainty language detection ("I think", "maybe" → confidence modifier)
- Concept extraction: "she reached for her bunny" → concept: "bunny_toy"
- Links extracted concept to acoustic cluster from that session
- Updates concept graph confidence

**Evolved Feedback UI (Stage-Aware):**
- Feedback form rendered based on `developmental_stage` from session
- Dynamic concept list generated from personal concept graph (top concepts by frequency)
- Stage-specific fields (see Section 7 of this document)
- Free text field active from 6 months
- "baba/dada" proto-sound hint ONLY for PRE_LINGUISTIC stage
- Transcription field for LINGUISTIC stage

**Flexible Feedback Schema:**
- `feedback_payload` JSON varies by `developmental_stage`
- `stage_version` field tells system which schema applies
- All stages stored in same `feedback` DynamoDB table

**Output:** App understands what baby wants by name, not just by category. Parents describe freely. System learns.

---

### Phase 6 — Stream Decoder + Developmental Tracking ✅ COMPLETE
**Command:** "Build Phase 6"
**Depends on:** Phase 5 complete (concept graph must exist)

**Stream Decoder:**
- Continuous audio segmentation into cluster sequences
- Per-cluster concept graph lookup (not just intent — specific concept node)
- Context-weighted Bayesian inference over personal concept space
- Bounded concept space inference: "which of the N concepts this baby knows fits?"
- Sequence reasoning: "meh meh wawa bah" → food/drink cluster + water cluster = asking for drink
- Unknown cluster detection and parent flagging
- Real-time output: concept name, confidence, evidence count, reasoning

**Developmental Stage Tracking (Layer 7):**
- 7-stage phonological classifier (vegetative → first words)
- CBR trend tracking per session rolling window
- Stage-aware adaptive EMA: α changes at developmental transitions
- VTL growth curve (physical development tracking)
- Acoustic change rate (vocabulary expansion rate)
- Regression detection (temporary reversion to earlier stage)
- Milestone logging: first canonical babble, first proto-word, first word combination

**Proto-Word Crystallisation:**
- 5-criteria detection algorithm (cluster stability, context consistency, confirmation history)
- Parent notification: "This sound is becoming consistent — it may mean X"
- Confidence growth tracking per proto-word candidate
- Promotion to "established signal" at confidence ≥ 0.85

**Personal Phoneme Inventory:**
- Tracks all distinct cluster types this baby produces
- First appearance date per cluster (milestone events)
- Shannon entropy tracking (diversity of sounds)
- Growth rate: new cluster types per week

**Output:** Real-time stream decoding. Developmental trajectory visible. Milestones recorded.

---

### Phase 7 — Speech Analysis Pipeline ✅ COMPLETE
**Command:** "Build Phase 7"
**Depends on:** Phase 6 complete (mode detection must be stable)

**Linguistic Mode Pipeline (for MODE_LINGUISTIC children 24m+):**
- MLU (Mean Length of Utterance) calculation — gold standard language metric
- Vocabulary diversity: type-token ratio
- Phonological accuracy scoring
- Sentence structure complexity
- Pragmatic classification: request / question / declaration / refusal
- Emotional prosody extraction (separate from intent — HOW they said it)
- Language milestone checking against developmental norms

**Language Development Insight Generation:**
- No intent insight for linguistic-mode sessions ("baby may be hungry" is wrong when child said it)
- Language insight: "Complete 3-word sentence. Milestone active. MLU this week: 2.8"
- Emotional prosody insight: "Calm, assertive tone — good emotional self-regulation"
- Vocabulary tracking: new words detected this session

**Journey View Data Pipeline:**
- Every session contributes a timeline entry
- Milestone events are flagged automatically
- Full developmental archive: day 0 → present
- "18 months ago, this was an unconfirmed cluster. Today it's a sentence."

**Output:** App is useful for the full 0–3+ year range, not just pre-linguistic phase.

---

### Phase 8 — Population Model (Federated Learning) ✅ COMPLETE
**Command:** "Build Phase 8"
**Depends on:** Phases 1–7 complete and generating quality data

**Federated Learning Infrastructure:**
- Anonymised model weight update aggregation
- Privacy-preserving: raw audio never leaves, only statistical updates sent
- Differential privacy: calibrated noise added to updates (ε=1.0, δ=1e-5 target)
- Quality filter before aggregation: FRS > 0.60, delta > 0.65, no flags, data_quality = HIGH/MEDIUM
- Stage-stratified aggregation: babies at same developmental stage inform each other

**Category Replacement:**
- Hard-coded research categories → data-driven population model categories
- Research prior (0.15 weight) updated from population model as data grows
- Research floor: minimum 0.10 always — research never fully replaced
- A/B evaluation: new model vs old categories, parent feedback as ground truth
- Timeline: 6 months of data before first meaningful population model

**Output:** Every baby benefits from every other baby's confirmed data. Accuracy improves collectively.

---

### Phase 9 — Parent Interface Rebuild
**Command:** "Build Phase 9"
**Depends on:** All backend phases complete

**Session View (revised):**
- Baby name in every insight: "Emma's sounds show..."
- Validation confirmation shown before insight (confirmed: Emma's voice)
- Dimensional insight output (arousal × valence + probable intent)
- Honest confidence with session count context ("Session 3 of your journey with Emma")
- Top 3 alternatives always visible
- Context acknowledgment: "Analysis adjusted for: 4 hours since last feed"
- Health flag if warranted (gentle, not alarming)

**Developmental Progress Page:**
- Current stage with name, description, what to expect next
- Stage progression timeline
- CBR trend chart
- Vocal repertoire size and growth rate
- VTL growth curve (physical development)
- Milestone log with dates
- Language emergence indicator (φ order parameter, honestly presented)

**Private Language Page (unlocks progressively):**
- Emma's personal signal library
- Each entry: sound description / what it means / confidence / times confirmed
- Proto-word candidates with evidence
- Personal phoneme inventory
- "Emma says X when she means Y" — established signals

**Journey View:**
- Full developmental timeline from session 1
- Every milestone event with date and age
- "Emma at 6m 12d: First canonical babble recorded"
- "Emma at 9m 3d: Water signal forming — confirmed 8 times"
- "Emma at 26m 11d: First complete sentence"
- The full arc, from first cry to first sentence, in one scroll

---

## 7. Age-Wise Feedback Schema — How Feedback Evolves With the Baby

This section documents how the feedback UI and stored data schema evolve as the child develops. This was a key design discussion and must be preserved here.

### The Core Problem
A single feedback form does not work across 0–36 months:
- At 3 months: baby cannot want a specific toy — feeding/comfort/sleep covers all needs
- At 15 months: baby has 80 concepts in their personal graph — fixed categories miss 95% of what they want
- At 30 months: baby is speaking sentences — asking "did it help?" is absurd

### Stage-by-Stage Feedback Schema

**STAGE: PRE_LINGUISTIC (0–6 months)**
```
feedback_payload = {
  response_type: ENUM["feeding","comfort","sleep_routine","discomfort_check",
                       "reduce_stimulation","vocal_play"],
  effectiveness: ENUM["helpful","neutral","ineffective"],
  word_token:    string (optional) — "did you hear a repeated sound? e.g. baba, dada, meh"
}
```

**STAGE: YOUNG_INFANT (6–12 months)**
```
feedback_payload = {
  response_type: ENUM[same as above],
  effectiveness: ENUM["helpful","neutral","ineffective"],
  free_text:     string (optional) — "what do you think they wanted? what happened?"
  word_token:    string (optional) — "what sound did they make?"
}
```

**STAGE: TODDLER_EARLY (12–18 months)**
```
feedback_payload = {
  concept_selected:  concept_node_id OR null,  ← from personal concept graph
  fixed_fallback:    ENUM["feeding","comfort","sleep"] OR null,
  free_text:         string — "what did they want? describe if not in list"
  effectiveness:     ENUM["helpful","neutral","ineffective"],
  sound_description: string — "what sound did they make?"
}
```

**STAGE: TODDLER_MID (18–24 months)**
```
feedback_payload = {
  concept_selected:      concept_node_id OR null,
  free_text:             string (primary) — "what did they say or want?"
  partial_transcription: string (optional) — "what sounds did they make?"
  effectiveness:         ENUM["helpful","neutral","ineffective"],
  understood:            ENUM["fully","partially","not_at_all"]
}
```

**STAGE: TODDLER_LATE (24–36 months)**
```
feedback_payload = {
  transcription:    string — "what did they say?" (full sentence attempt)
  concept_selected: concept_node_id OR null,
  free_text:        string — "what did they want?"
  understood:       ENUM["yes","mostly","no"],
  language_quality: ENUM["full_sentence","word_combination","sounds_only"],
  // NO effectiveness field — child expressed clearly, nothing to judge
}
```

**STAGE: PRESCHOOL (36+ months)**
```
feedback_payload = {
  transcription:     string,
  understood:        ENUM["yes","mostly","no"],
  language_quality:  ENUM["complex_sentence","simple_sentence","word_combination"],
  emotional_tone:    ENUM["calm","excited","distressed","frustrated","happy"] (parent observation),
  // Insight at this stage is purely language development
}
```

### DynamoDB Storage
All stages stored in same `feedback` table. `developmental_stage` + `stage_version` fields declare which schema applies to `feedback_payload`.

---

## 8. Stage-Aware UI — What the App Shows at Each Stage

This documents the UI differentiation that must exist. The "baba/dada" question is for infants. A toddler who is speaking needs completely different questions.

| Stage | Word/Sound Field | Effectiveness Question | Concept List | Free Text |
|---|---|---|---|---|
| 0–6m | "Heard a repeated sound? e.g. baba, dada" | Yes | No | No |
| 6–12m | "What sound did they make?" | Yes | No | Optional |
| 12–18m | "What sound did they make?" | Yes | Yes — from graph | Prominent |
| 18–24m | "What did they say?" | Yes | Yes — quick taps | Primary |
| 24m+ | "Write what they said" (transcription) | **No** | Tap or type | Primary |

**The insight title also changes:**
- 0–18m: "Emma's Vocalization Analysis"
- 18–24m: "Emma's Communication Session"
- 24m+: "Emma's Language Session"

**The insight content changes:**
- 0–18m: Intent translation ("may be hungry, tired, seeking connection")
- 24m+: Language development ("complete sentence, MLU 3.2, vocabulary growing")

---

## 9. Data Storage Principles — What Is Stored and Why

### Everything Is Stored. Nothing Is Discarded.

| Data | Stored? | Where | Why |
|---|---|---|---|
| Raw audio | Yes, with expiry | S3 | Re-analysis with future better models |
| Full feature vector (50–80) | Yes | DynamoDB sessions | Longitudinal tracking |
| Acoustic intent distribution | Yes | DynamoDB sessions | Three-source model |
| Expected Feedback Profile | Yes, before parent responds | DynamoDB feedback | Delta scoring requires it |
| Raw parent feedback | Yes, permanent | DynamoDB feedback | Trust recovery, audit trail |
| Submission speed | Yes | DynamoDB feedback | Mis-click detection |
| Delta score | Yes | DynamoDB feedback | Trust system, quality flag |
| Trust score at submission | Yes | DynamoDB feedback | Longitudinal trust tracking |
| Reliability flags | Yes | DynamoDB feedback | Population model filtering |
| Free text | Yes | DynamoDB feedback | NLP re-processing improves |
| NLP extracted concepts | Yes | DynamoDB feedback | Concept graph building |
| Outcome consistency | Written after next session | DynamoDB feedback | Retrospective validation |
| Concept graph | Yes, growing | DynamoDB concept_graph | Private language system |
| VTL estimates | Yes, per session | DynamoDB sessions | Growth curve tracking |
| CBR values | Yes, per session | DynamoDB sessions | Developmental tracking |
| Developmental stage | Yes, per session | DynamoDB sessions | Stage-aware processing |
| Milestone events | Yes, permanent | DynamoDB milestones | Journey view |
| Population model updates | Anonymised weights only | S3 model store | Federated aggregation |

### Audio Deletion Policy
Raw audio: S3 lifecycle policy — delete after 30 days post feature extraction.
Exception: Parent can opt in to longer retention for research contribution (explicit consent required).

---

## 10. Infrastructure Decisions

### AWS Services in Use
- **Lambda:** All processing (feature extraction, cluster engine, insight generator, NLP processor, feedback processor, reinforcement engine, stream decoder)
- **Step Functions:** Orchestrates session processing pipeline
- **DynamoDB:** All persistent data (sessions, feedback, concept graph, clusters, milestones)
- **S3:** Raw audio, model weights
- **Amazon Bedrock — Claude 3 Haiku:** Natural language generation only
  - **Credits confirmed:** "Amazon Bedrock" is in AWS eligible credits services list
  - Use on-demand pricing only. Never use Provisioned Throughput.
  - Migration at scale: Amazon Nova Lite (~4x cheaper, sufficient quality)
- **Weather API:** Temperature + humidity for context layer (single lightweight call per session)

### New DynamoDB Tables Needed (from Phase 0 audit)
- `concept_graph` — personal concept nodes per child
- `concept_cluster_links` — acoustic cluster to concept mappings
- `milestones` — developmental milestone events per child
- `feedback_v2` — flexible stage-aware feedback schema (may extend existing `feedback` table)
- `trust_scores` — rolling FRS per parent account

### New Lambda Functions Needed
- `validation_gate` (Layer 0 + Layer 1)
- `speaker_identity` (Layer 2)
- `context_collector` (Layer 3)
- `rich_feature_extractor` (replaces current feature extractor)
- `nlp_processor` (free text extraction)
- `stream_decoder` (real-time concept inference)
- `developmental_tracker` (stage, CBR, VTL, milestones)
- `speech_analyzer` (MLU, vocabulary, language development)
- `federated_aggregator` (population model updates)

---

## 11. Writing Guide — Papers, Blogs, Articles

### For Academic Papers / PhD Chapters

| Topic | Primary Source | Section |
|---|---|---|
| Problem statement and motivation | PHD_RESEARCH_FRAMEWORK.md | Sections 1–2 |
| Literature review | PHD_RESEARCH_FRAMEWORK.md | Section 3 |
| Research questions | PHD_RESEARCH_FRAMEWORK.md | Section 4 |
| Novel contributions | PHD_RESEARCH_FRAMEWORK.md | Section 5 |
| All mathematics | SCIENTIFIC_MATHEMATICS.md | All sections |
| Theorems and proofs | SCIENTIFIC_MATHEMATICS.md | Sections 3, 8, 10, 11 |
| Evaluation metrics | SCIENTIFIC_MATHEMATICS.md | Section 12 |
| Ethics | PHD_RESEARCH_FRAMEWORK.md | Section 9 |
| References | PHD_RESEARCH_FRAMEWORK.md | Final section |

### For Technical Articles / Developer Blogs

| Topic | Primary Source | Section |
|---|---|---|
| System architecture | TECHNICAL_PIPELINE.md | Sections 1–3 |
| Pipeline evolution | TECHNICAL_PIPELINE.md | Section 2 |
| Cold start solution | TECHNICAL_PIPELINE.md | Section 6 |
| Federated learning | TECHNICAL_PIPELINE.md | Section 9 |
| AWS infrastructure | TECHNICAL_PIPELINE.md | Section 10 |
| Feature extraction | RESEARCH_VISION_2.0.md | Section 3 |
| Concept graph design | RESEARCH_VISION_2.0.md | Section 12 |

### For General / Parenting / Product Blogs

| Topic | Primary Source | Section |
|---|---|---|
| What is private language | RESEARCH_VISION_2.0.md | Section 12.1 |
| How the app grows with the baby | RESEARCH_VISION_2.0.md | Section 18.1 |
| The journey view narrative | RESEARCH_VISION_2.0.md | Section 18.2 |
| Why acoustic physics cannot be fooled | RESEARCH_VISION_2.0.md | Section 4 |
| What audio can reveal about a baby | RESEARCH_VISION_2.0.md | Section 3 |
| The bounded concept space insight | MASTER_INDEX.md | Section 7 |

### For Grant Applications

| Topic | Source |
|---|---|
| Scientific gap and motivation | PHD_RESEARCH_FRAMEWORK.md Sections 1–3 |
| Novel contributions | PHD_RESEARCH_FRAMEWORK.md Section 5 |
| Research questions | PHD_RESEARCH_FRAMEWORK.md Section 4 |
| Dataset potential | RESEARCH_VISION_2.0.md Section 11 |
| Mathematical rigor | SCIENTIFIC_MATHEMATICS.md Theorems 3.1, 11.1, 11.2 |
| Ethics | PHD_RESEARCH_FRAMEWORK.md Section 9 |

---

## Document Maintenance

Update this index when:
- A phase is completed (update Section 4 current system state)
- A new design decision is made (add to Section 5)
- A new document is created (add to Section 3)
- A new data field is added (add to Section 9)

**This document must always reflect the current true state of the project.**
Anyone reading it — including an AI in a new session with no chat history — should be able to understand exactly where the project is and what to do next.

---

*Qleam sits at the intersection of acoustic signal processing, developmental psychology, information theory, dynamical systems mathematics, and machine learning. Its scientific contribution is not in any single technique but in their convergence toward a single goal: understanding what a baby is communicating, tracking how their private language emerges, and giving parents and science a continuous window into the earliest moments of human language — from first cry to first sentence.*
