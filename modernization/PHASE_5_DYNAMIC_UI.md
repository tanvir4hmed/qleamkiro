# Phase 5: Dynamic UI Overhaul (INSIGHT)

## Goal
Replace static template cards with dynamic, conversational insights. Meaningful radar charts. Context-aware suggestions that never repeat. Dunstan reference sound playback for 0-3m. The parent should feel like talking to an AI that knows their baby, not reading a form.

## Current Problems
1. Static 3-card template (What I hear / What it means / What to try) — same content every time
2. FeatureChart shows meaningless data from dead code (removed in Phase 1)
3. No variation in advice — parents see same tips repeatedly
4. No real acoustic data visualization
5. Feels like reading a template, not interacting with AI

## Page Layout

```
+------------------------------------------+
| <- Back                                   |
|                                           |
| Emma's Session - 2:30 PM today            |
|                                           |
| +---------------------------------------+ |
| |                                       | |
| |  [emoji] Your baby sounds hungry      | |
| |                                       | |
| |  I'm picking up a rhythmic cry with   | |
| |  a nasal "neh" quality at 425 Hz -    | |
| |  this is a classic Dunstan hunger     | |
| |  signal for newborns.                 | |
| |                                       | |
| |  The cry builds in waves with         | |
| |  regular pauses, which is typical     | |
| |  when a baby is signaling they're     | |
| |  ready to eat.                        | |
| |                                       | |
| |  +--- Confidence ----------------+    | |
| |  | ################----  72%      |    | |
| |  | Strong signal. Session 8 of   |    | |
| |  | Emma - I'm getting to know    |    | |
| |  | her patterns well.            |    | |
| |  +-------------------------------+    | |
| |                                       | |
| |  +- Try this -------------------+     | |
| |  | * Offer a feed, watch for    |     | |
| |  |   rooting and hand-to-mouth  |     | |
| |  | * If just fed, try a different|     | |
| |  |   position or check for burp |     | |
| |  +------------------------------+     | |
| |                                       | |
| |  I'm also picking up mild discomfort  | |
| |  signals (18%) - if feeding doesn't   | |
| |  settle things, check comfort next.   | |
| |                                       | |
| +---------------------------------------+ |
|                                           |
| +- Acoustic Analysis ------------------+ |
| |                                       | |
| |  +----------+  +------------------+   | |
| |  | EMOTION  |  | FEATURES         |   | |
| |  | MATCH    |  |                  |   | |
| |  |          |  |     Pitch        |   | |
| |  |  Hungry  |  |      /\         |   | |
| |  |   /\    |  | Dur /  \ Stab   |   | |
| |  |  /  \   |  |    /    \       |   | |
| |  |  \  /   |  |   \    /       |   | |
| |  |   \/    |  |    \  /         |   | |
| |  |  Pain   |  |     \/          |   | |
| |  +----------+  |   Energy        |   | |
| |                 +------------------+   | |
| |                                       | |
| |  Pitch: 425 Hz (newborn cry range)    | |
| |  Energy: moderate, rhythmic waves     | |
| |  Stability: steady (not erratic)      | |
| |  Duration: 6.2 seconds                | |
| |                                       | |
| +---------------------------------------+ |
|                                           |
| +- Dunstan Sound (0-3m only) ----------+ |
| |  Sounds like "Neh" (hungry)           | |
| |  [> Play reference sound]             | |
| |                                       | |
| |  "Neh" is a reflexive sound babies    | |
| |  make when hungry, caused by the      | |
| |  sucking reflex pushing the tongue    | |
| |  to the roof of the mouth.            | |
| +---------------------------------------+ |
|                                           |
| +- Was this right? --------------------+ |
| | Help Qleam learn Emma's patterns      | |
| |     [Yes, correct]  [No, different]   | |
| +---------------------------------------+ |
|                                           |
| [disclaimer] Behavioral observation, not  |
| medical advice.                           |
+------------------------------------------+
```

## A. Dynamic Narrative System

For each emotion, maintain a pool of narrative templates with acoustic data slots:

```javascript
const NARRATIVES = {
  hungry: [
    "Your baby's cry has a {intensity} rhythmic pattern with {pitch_desc} pitch - this often signals hunger. The sound {duration_desc}.",
    "I'm picking up a {intensity} cry with {pitch_desc} tones that build steadily. This pattern is commonly associated with hunger.",
    "The recording shows a {pattern_desc} cry that {builds_or_steady}. Combined with the {pitch_desc} pitch, this suggests your baby may be hungry.",
    "{childName} sounds hungry. The cry has a {intensity} {pattern_desc} quality with {pitch_desc} undertones.",
    "I'm hearing a clear hunger signal from {childName}. The {intensity} cry with {pitch_desc} pitch and {pattern_desc} rhythm is typical of babies asking to eat.",
    // 5+ more variants per emotion
  ],
  tired: [...],
  discomfort: [...],
  gas: [...],
  pain: [...],
  overstimulated: [...],
  content: [...],
};
```

Slots filled from REAL acoustic data (from GATE/EARS measurements):
- `{intensity}` -> "strong" / "moderate" / "gentle" (from RMS energy)
- `{pitch_desc}` -> "rising" / "steady" / "high-pitched" / "nasal" (from F0 trajectory)
- `{duration_desc}` -> "started quietly and built up" / "was intense from the start" / "comes in waves"
- `{pattern_desc}` -> "repetitive" / "continuous" / "intermittent" / "rhythmic"
- `{builds_or_steady}` -> "builds in intensity" / "stays relatively steady" / "comes and goes"
- `{childName}` -> from child profile

### Why This Varies Every Time
1. **Random template selection** — never same as last 3 sessions for this child (tracked in localStorage)
2. **Actual acoustic measurements fill the slots** — data-driven, not canned text
3. **Session context changes the framing** — session count, confidence level, time of day

### Confidence Message (Also Varies)
```javascript
function buildConfidenceMessage(confidence, sessionCount, childName) {
  if (confidence > 0.7 && sessionCount > 5)
    return `Strong signal. I'm getting to know ${childName}'s patterns well.`;
  else if (confidence > 0.7)
    return `Strong signal, even this early. Keep recording to build accuracy.`;
  else if (confidence > 0.4)
    return `Moderate signal. A few more sessions will sharpen this.`;
  else
    return `Early pattern - I'm still learning ${childName}'s unique voice.`;
}
```

### "Also Possible" Woven Into Narrative
```javascript
// Not a separate card — part of the flowing text
if (secondEmotion && secondScore > 0.15) {
  alsoText = `I'm also picking up ${secondLabel} signals `
    + `(${Math.round(secondScore * 100)}%) - if ${primaryAction} doesn't help, `
    + `${secondaryAction} next.`;
}
```

## B. Context-Aware Suggestions (Never Repeat)

### Suggestion Pool Structure
```javascript
const SUGGESTIONS = {
  hungry: [
    {
      text: "Try offering a feed - hunger cries tend to build when the need isn't met",
      conditions: { hours_since_feed: ">2", not_tried_recently: true },
      group: "feed",
      variants: [
        "Your baby might be ready to eat",
        "It's been a while since the last feed - this could be hunger",
        "Hunger cries often start slow and escalate - offering a feed now may settle things quickly",
      ]
    },
    {
      text: "If you recently fed, try burping first - sometimes gas mimics hunger",
      conditions: { hours_since_feed: "<1" },
      group: "burp"
    },
    {
      text: "Check if rooting reflex is present - gently stroke their cheek",
      conditions: { age_days: "<120" },
      group: "check"
    },
    {
      text: "Watch for hand-to-mouth movements - another hunger cue to confirm",
      conditions: {},
      group: "observe"
    },
    // 10+ suggestions per emotion, each with conditions and variants
  ],
  tired: [...],
  // etc.
};
```

### Selection Algorithm
1. Filter by conditions (time of day, age, hours since feed if tracked)
2. Exclude suggestions shown in last 3 sessions for this child (localStorage tracking)
3. Exclude groups where parent previously said "didn't help" (feedback history)
4. Pick 2-3 from remaining, prefer different groups
5. Randomize phrasing variant within selected suggestion

### Escalation
If 3rd+ cry session in 2 hours:
- Skip basic suggestions
- Show: "Your baby seems persistently unsettled. If basic comfort measures haven't helped, consider: [advanced suggestions like checking temperature, pediatrician call, etc.]"

### Session Count Today
- First cry: gentle, exploratory suggestions
- 4th cry in 2 hours: escalate, different advice, more assertive

## C. Two Radar Charts

### 1. Emotion Match Spider
7 axes representing emotion scores from the BRAIN classifier:

```javascript
// Data from model softmax output (emotion_scores)
const emotionData = [
  { emotion: 'Hungry', score: 75 },
  { emotion: 'Tired', score: 15 },
  { emotion: 'Discomfort', score: 18 },
  { emotion: 'Gas', score: 8 },
  { emotion: 'Pain', score: 3 },
  { emotion: 'Overstimulated', score: 12 },
  { emotion: 'Content', score: 5 },
];
```

- Values: 0-100% (from model softmax probabilities — REAL data)
- Dominant emotion axis highlighted
- Shows WHY the model chose this emotion (other scores visible)
- Color: emotion-specific (red for pain, blue for tired, etc.)

### 2. Acoustic Features Spider
6 axes showing REAL acoustic measurements:

```javascript
// Normalize raw measurements to 0-100 scale
const featureData = [
  { feature: 'Pitch', value: normalize(f0_mean, 100, 800) },
  { feature: 'Energy', value: normalize(rms_mean, 0, 0.2) },
  { feature: 'Stability', value: 100 - normalize(f0_instability, 0, 0.5) },
  { feature: 'Voicing', value: voiced_fraction * 100 },
  { feature: 'Brightness', value: normalize(spectral_centroid, 500, 4000) },
  { feature: 'Variation', value: normalize(energy_var, 0, 1) },
];
```

- **Pitch**: Average F0 normalized to 0-100 (within baby range)
- **Energy**: RMS energy normalized
- **Stability**: How consistent the pitch is (low jitter = high stability)
- **Voicing**: % of frames that are voiced
- **Brightness**: Spectral centroid (higher = brighter/sharper cry)
- **Variation**: F0 range / standard deviation (how much pitch changes)

All values are REAL measurements from the audio, extracted during GATE/EARS processing. Below the chart, show human-readable descriptions:
```
Pitch: 425 Hz (newborn cry range)
Energy: moderate, rhythmic waves
Stability: steady (not erratic)
Duration: 6.2 seconds
```

## D. Dunstan Sound Section (0-3m Only)

```
[Only shown if age_days <= 90]

  Sounds like "Neh" (hungry reflex sound)
  [> Play reference sound]

  "Neh" is a reflexive sound babies make when hungry,
  caused by the sucking reflex pushing the tongue to
  the roof of the mouth.
```

- If age > 90 days: section hidden entirely (not applicable)
- If age <= 90 but no clear match: "Your baby's cry doesn't clearly match a known reflexive sound - this is completely normal. Not every cry fits a category."
- Reference sounds: 5 short audio clips (neh, owh, heh, eairh, eh) stored in S3/CloudFront
- Simple HTML5 audio player, no library needed

## E. Progressive Reveal Animation

Content appears sequentially to feel like live analysis:

1. [0ms] Emotion badge fades in
2. [300ms] Confidence bar animates to value
3. [600ms] Narrative text appears (typing effect or fade)
4. [1000ms] Radar charts draw their axes
5. [1500ms] Suggestions slide in
6. [2000ms] Dunstan section (if applicable)

CSS animations only, no external library.

## F. Backend: Insight Generator Changes

The insight_generator Lambda must return richer data for the frontend:

```python
insight_response = {
    "display_type": "cry",
    "headline": "Your baby sounds hungry",
    "headline_icon": "emoji_code",

    # Emotion scores (for Emotion Match radar)
    "emotion_scores": {
        "hungry": 0.75, "tired": 0.15, "discomfort": 0.18,
        "gas": 0.08, "pain": 0.03, "overstimulated": 0.12, "content": 0.05
    },

    # Acoustic measurements (for Acoustic Features radar)
    "acoustic_features": {
        "pitch_hz": 425, "pitch_normalized": 68,
        "energy_normalized": 55,
        "stability_normalized": 72,
        "voicing_pct": 85,
        "brightness_normalized": 48,
        "variation_normalized": 35,
    },

    # Narrative slot data (for template filling)
    "narrative_data": {
        "intensity": "moderate",
        "pitch_desc": "nasal, rising",
        "duration_desc": "builds in waves with regular pauses",
        "pattern_desc": "rhythmic",
    },

    # Session context (for suggestion selection)
    "session_context": {
        "session_count_today": 3,
        "hours_since_last_session": 1.5,
        "child_total_sessions": 8,
    },

    # Dunstan (0-3m only, None otherwise)
    "dunstan_sound": "neh",
    "dunstan_description": "Reflexive sound caused by sucking reflex...",

    # Standard fields
    "emotion": "hungry",
    "emotion_confidence": 0.75,
    "also_possible": [
        {"label": "discomfort", "score": 0.18},
        {"label": "tired", "score": 0.15}
    ],
    "disclaimer": "Behavioral observation, not medical advice.",
}
```

Frontend composes the full display from this data — template selection, slot filling, suggestion picking, chart rendering all happen client-side.

## Tasks

### 5.1 Build Narrative Template System
- Create `frontend/src/data/narratives.js` with emotion-specific template pools (5+ per emotion)
- Slot-filling function that takes narrative_data from backend
- Selection algorithm: avoid last 3 shown to this child (localStorage tracking)

### 5.2 Build Suggestion Engine
- Create `frontend/src/data/suggestions.js` with condition-tagged pools (10+ per emotion)
- Context evaluator (time of day, session count, feedback history)
- Selection + deduplication + variant picking
- localStorage tracking of shown suggestions per child
- Escalation logic for repeated sessions

### 5.3 Redesign InsightPanel Component
- Remove static 3-card layout entirely
- New flow: emotion badge -> narrative -> confidence -> suggestions -> "also possible" woven in -> charts -> dunstan
- Progressive reveal animations (CSS only)
- Responsive design (mobile-first)

### 5.4 Build Emotion Radar Chart
- 7-axis radar using recharts (already installed)
- Data from emotion_scores (model softmax output)
- Dominant emotion highlighted
- Tooltips with percentage

### 5.5 Build Acoustic Features Radar Chart
- 6-axis radar using recharts
- Data from acoustic_features (real measurements)
- Normalized to 0-100 scale
- Below chart: human-readable descriptions with actual values + units

### 5.6 Dunstan Reference Section
- Conditional render (age_days <= 90 only)
- HTML5 audio player for reference sounds
- Upload 5 reference clips to S3/CloudFront (neh, owh, heh, eairh, eh)
- Graceful handling when no match found

### 5.7 Update SessionDetail Page
- Progressive reveal of content sections
- Better loading animation (pulsing waveform or similar)
- Mobile-responsive layout
- Feedback section integrates seamlessly

### 5.8 Backend: Update insight_generator
- Return emotion_scores (all 7), acoustic_features (6 normalized), narrative_data, session_context
- Compute narrative slot values from acoustic measurements
- Track session_count_today from DynamoDB

## Files Changed
- CREATE: frontend/src/data/narratives.js, frontend/src/data/suggestions.js
- REWRITE: frontend/src/components/InsightPanel.js (complete rewrite)
- MODIFY: frontend/src/pages/SessionDetail.js, frontend/src/App.css
- MODIFY: lambdas/insight_generator/handler.py (return richer data structure)

## Success Criteria
- Same emotion never shows identical text twice in a row for same child
- Suggestions vary based on context (time, history, what was tried, escalation)
- Both radar charts show REAL data from model + acoustic measurements
- Dunstan section appears only for 0-3m babies, with working audio playback
- Progressive reveal animation feels smooth and natural
- Parent feels like interacting with an AI that knows their baby

## Deploy
- Workflows: `2-lambda-deploy` (insight_generator changes) then `3-frontend-deploy`
