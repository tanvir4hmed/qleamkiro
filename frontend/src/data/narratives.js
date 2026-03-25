/**
 * Qleam — Dynamic Narrative Templates
 *
 * Each emotion has 5+ narrative templates with acoustic data slots.
 * Slots are filled from real acoustic measurements returned by the backend.
 *
 * Slots:
 *   {intensity}      -> "strong" / "moderate" / "gentle" (from RMS energy)
 *   {pitch_desc}     -> "high-pitched, rising" / "steady" etc. (from F0)
 *   {duration_desc}  -> "builds in waves with regular pauses" etc.
 *   {pattern_desc}   -> "rhythmic" / "continuous" / "intermittent" etc.
 *   {builds_or_steady} -> "builds in intensity" / "stays relatively steady"
 *   {childName}      -> from child profile
 */

const NARRATIVES = {
  hungry: [
    "Your baby's cry has a {intensity} rhythmic pattern with {pitch_desc} pitch — this often signals hunger. The sound {duration_desc}.",
    "I'm picking up a {intensity} cry with {pitch_desc} tones that build steadily. This pattern is commonly associated with hunger.",
    "The recording shows a {pattern_desc} cry that {builds_or_steady}. Combined with the {pitch_desc} pitch, this suggests your baby may be hungry.",
    "{childName} sounds hungry. The cry has a {intensity} {pattern_desc} quality with {pitch_desc} undertones.",
    "I'm hearing a clear hunger signal. The {intensity} cry with {pitch_desc} pitch and {pattern_desc} rhythm is typical of babies asking to eat.",
    "A {intensity}, {pattern_desc} cry pattern — the {pitch_desc} quality and the way it {builds_or_steady} are classic hunger cues.",
  ],
  tired: [
    "Your baby sounds sleepy. The {intensity} cry has a {pitch_desc}, breathy quality that {duration_desc}.",
    "I'm picking up tired signals — a {intensity} cry with {pitch_desc} tones. The sound {builds_or_steady}, which is typical before sleep.",
    "This {pattern_desc} cry has a yawn-like quality. The {intensity} sound with {pitch_desc} pitch suggests your baby may be ready for rest.",
    "{childName} might be ready for a nap. The {intensity}, {pattern_desc} cry with {pitch_desc} pitch has a drowsy quality to it.",
    "A soft, {pattern_desc} sound that {builds_or_steady}. The {pitch_desc} quality suggests tiredness rather than distress.",
    "The {intensity} cry {duration_desc} — this gentle, {pattern_desc} pattern often means your baby is winding down.",
  ],
  discomfort: [
    "Your baby seems uncomfortable. The {intensity} cry with {pitch_desc} tones {duration_desc}.",
    "I'm detecting discomfort signals — a {pattern_desc} cry with {intensity} energy and {pitch_desc} pitch that {builds_or_steady}.",
    "The recording shows {intensity}, {pattern_desc} fussing with {pitch_desc} undertones. Something may be bothering your baby physically.",
    "{childName} sounds uncomfortable. The {intensity} cry has a {pitch_desc}, intermittent quality — often a sign of physical discomfort.",
    "A {pattern_desc}, {intensity} cry that {builds_or_steady}. The {pitch_desc} quality suggests your baby may need a comfort check.",
    "Short, {intensity} bursts of fussing with {pitch_desc} tones — this {pattern_desc} pattern often signals physical discomfort.",
  ],
  gas: [
    "Your baby's cry has a straining, {intensity} quality with {pitch_desc} tones. The sound {duration_desc}, which can indicate gas.",
    "I'm picking up possible gas signals — a {intensity}, grunting cry with {pitch_desc} pitch that {builds_or_steady}.",
    "The {pattern_desc} cry has a tense, {intensity} quality. The {pitch_desc} tones and the way it {duration_desc} suggest digestive discomfort.",
    "{childName} may have trapped gas. The {intensity} cry with {pitch_desc}, straining tones is a common gas pattern.",
    "A {intensity} cry with a grunting quality that {builds_or_steady}. The {pitch_desc}, {pattern_desc} pattern often accompanies gas.",
    "The sound has a {intensity}, strained character with {pitch_desc} tones — this {pattern_desc} pattern is frequently associated with gas or colic.",
  ],
  pain: [
    "Your baby's cry is {intensity} and sudden with {pitch_desc} tones. The {pattern_desc} sound {duration_desc} — this intensity may indicate pain.",
    "I'm detecting a {intensity}, sharp cry with {pitch_desc} pitch. The way it {builds_or_steady} suggests acute discomfort.",
    "This is a notably {intensity} cry — {pitch_desc} and {pattern_desc}. The sustained intensity warrants a closer look.",
    "{childName} sounds distressed. The {intensity} cry with {pitch_desc} tones and {pattern_desc} pattern suggests possible pain.",
    "A {intensity}, piercing cry that {duration_desc}. The {pitch_desc}, {pattern_desc} quality can signal pain or acute discomfort.",
    "The cry is {intensity} with sudden onset — {pitch_desc} tones that {builds_or_steady}. This intensity pattern is often associated with pain.",
  ],
  burp: [
    "Your baby's cry has a {intensity}, pushing quality with {pitch_desc} tones — often a sign of trapped air after feeding.",
    "I'm hearing short, {intensity} sounds with {pitch_desc} pitch that {builds_or_steady}. This may indicate your baby needs to burp.",
    "The {pattern_desc}, {intensity} cry with {pitch_desc} undertones {duration_desc}. This pushing quality often means trapped air.",
    "{childName} may need to burp. The {intensity}, {pattern_desc} sounds with {pitch_desc} tones are typical after feeding.",
    "A {intensity} cry with a repetitive, pushing character. The {pitch_desc} quality and the way it {builds_or_steady} suggest trapped air.",
    "Short, {intensity} bursts with {pitch_desc} tones — this {pattern_desc} pattern frequently signals the need for burping.",
  ],
  content: [
    "Your baby sounds settled. The {intensity}, {pattern_desc} vocalizations with {pitch_desc} tones don't indicate distress.",
    "I'm picking up soft, {intensity} sounds — {pitch_desc} and {pattern_desc}. Your baby seems calm and content.",
    "The recording shows {intensity}, relaxed vocalizations that {builds_or_steady}. The {pitch_desc} quality sounds positive.",
    "{childName} seems content. The {intensity}, {pattern_desc} sounds with {pitch_desc} tones are calm vocalizations.",
    "A {intensity}, {pattern_desc} vocalization — the {pitch_desc} quality suggests your baby is comfortable and exploring their voice.",
    "Soft, {intensity} sounds that {duration_desc}. The {pitch_desc} quality is calm — your baby doesn't seem to be in distress.",
  ],
};

const CONFIDENCE_MESSAGES = {
  high_experienced: "Strong signal. I'm getting to know {childName}'s patterns well.",
  high_early: "Strong signal, even this early. Keep recording to build accuracy.",
  moderate: "Moderate signal. A few more sessions will sharpen this.",
  low: "Early pattern — I'm still learning {childName}'s unique voice.",
};

/**
 * Fill template slots with narrative data + child name.
 */
function fillTemplate(template, narrativeData, childName) {
  const name = childName || 'your baby';
  const data = narrativeData || {};
  let text = template;
  text = text.replace(/\{childName\}/g, name);
  text = text.replace(/\{intensity\}/g, data.intensity || 'moderate');
  text = text.replace(/\{pitch_desc\}/g, data.pitch_desc || 'mid-range');
  text = text.replace(/\{duration_desc\}/g, data.duration_desc || 'varies in intensity');
  text = text.replace(/\{pattern_desc\}/g, data.pattern_desc || 'rhythmic');
  text = text.replace(/\{builds_or_steady\}/g, data.builds_or_steady || 'varies');
  return text;
}

/**
 * Pick a narrative template that hasn't been shown recently.
 * Tracks last 3 shown per child+emotion in localStorage.
 */
function pickNarrative(emotion, narrativeData, childName, childId) {
  const templates = NARRATIVES[emotion] || NARRATIVES.discomfort;
  const storageKey = `qleam_narr_${childId || 'default'}_${emotion}`;

  let recentIndices = [];
  try {
    recentIndices = JSON.parse(localStorage.getItem(storageKey) || '[]');
  } catch (_) {}

  // Pick from templates not in recent history
  const available = templates
    .map((t, i) => ({ template: t, index: i }))
    .filter(({ index }) => !recentIndices.includes(index));

  const pick = available.length > 0
    ? available[Math.floor(Math.random() * available.length)]
    : { template: templates[Math.floor(Math.random() * templates.length)], index: 0 };

  // Update history (keep last 3)
  const updated = [...recentIndices, pick.index].slice(-3);
  try {
    localStorage.setItem(storageKey, JSON.stringify(updated));
  } catch (_) {}

  return fillTemplate(pick.template, narrativeData, childName);
}

/**
 * Build confidence message based on score and session count.
 */
function buildConfidenceMessage(confidence, sessionCount, childName) {
  const name = childName || 'your baby';
  const pct = Math.round((confidence || 0) * 100);
  let key;

  if (pct >= 60 && sessionCount > 5) key = 'high_experienced';
  else if (pct >= 60) key = 'high_early';
  else if (pct >= 30) key = 'moderate';
  else key = 'low';

  return CONFIDENCE_MESSAGES[key].replace(/\{childName\}/g, name);
}

/**
 * Build "also possible" flowing text for secondary emotions.
 */
function buildAlsoPossibleText(alsoPossible, primaryAction) {
  if (!alsoPossible || alsoPossible.length === 0) return null;
  const second = alsoPossible[0];
  if (!second || !second.score || second.score < 0.10) return null;

  const pct = Math.round(second.score * 100);
  const label = (second.label || second.key || '').toLowerCase();
  const action = primaryAction || 'the primary suggestion';

  return `I'm also picking up ${label} signals (${pct}%) — if ${action} doesn't help, address ${label} next.`;
}

export { NARRATIVES, pickNarrative, fillTemplate, buildConfidenceMessage, buildAlsoPossibleText };
