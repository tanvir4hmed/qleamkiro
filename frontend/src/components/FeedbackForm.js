import { useState, useEffect } from 'react';

// MASTER_INDEX.md §7-8 — five-stage feedback schema
// Base response types — labels adapt per mode below
const BASE_RESPONSE_TYPES = [
  { key: 'hunger',         labels: { INFANT: '🍼 Tried feeding',       BABBLE: '🍼 Tried feeding',    PROTO: '🍼 Gave food or drink', TODDLER: '🍼 Gave food or snack' } },
  { key: 'connection',     labels: { INFANT: '🤗 Held & comforted',    BABBLE: '🤗 Held & played',    PROTO: '🤗 Played together',    TODDLER: '🤗 Gave attention & play' } },
  { key: 'discomfort',     labels: { INFANT: '🩹 Checked for pain',    BABBLE: '🩹 Checked discomfort', PROTO: '🩹 Checked for pain',  TODDLER: '🩹 Checked & comforted' } },
  { key: 'overstimulation',labels: { INFANT: '🤫 Quieted the space',  BABBLE: '🤫 Reduced stimulation', PROTO: '🤫 Took a calm break', TODDLER: '🤫 Took a quiet break' } },
  { key: 'fatigue',        labels: { INFANT: '😴 Started sleep routine', BABBLE: '😴 Started nap routine', PROTO: '😴 Tried to nap',    TODDLER: '😴 Put down for nap' } },
  { key: 'exploration',    labels: { INFANT: '🎵 Sang & talked',       BABBLE: '🎵 Played & explored', PROTO: '🎵 Explored together', TODDLER: '🎵 Read / played together' } },
];

// Get response type list with mode-appropriate labels
function getResponseTypes(mode) {
  return BASE_RESPONSE_TYPES.map(rt => ({
    key: rt.key,
    label: rt.labels[mode] || rt.labels.INFANT,
  }));
}

// Reorder response types so the intent-matched option appears first
function orderByIntent(types, intentKey) {
  if (!intentKey) return types;
  const idx = types.findIndex(t => t.key === intentKey);
  if (idx <= 0) return types;
  return [types[idx], ...types.slice(0, idx), ...types.slice(idx + 1)];
}

const EFFECTIVENESS_OPTIONS = [
  { key: 'helpful',     label: '✓ Helped' },
  { key: 'neutral',     label: '~ Hard to tell' },
  { key: 'ineffective', label: '✗ Didn\'t help' },
];

/**
 * Five feedback modes per MASTER_INDEX.md §7-8:
 *
 *  INFANT   0–6m   NEWBORN, EARLY_VOCAL
 *  BABBLE   6–12m  CANONICAL_BABBLE
 *  PROTO    12–18m PROTO_WORDS
 *  TODDLER  18–24m FIRST_WORDS, WORD_COMBINATIONS
 *  LANGUAGE 24m+   EARLY_SENTENCES
 */
function getMode(developmentalStage) {
  switch (developmentalStage) {
    case 'NEWBORN':
    case 'EARLY_VOCAL':
      return 'INFANT';
    case 'CANONICAL_BABBLE':
      return 'BABBLE';
    case 'PROTO_WORDS':
      return 'PROTO';
    case 'FIRST_WORDS':
    case 'WORD_COMBINATIONS':
      return 'TODDLER';
    case 'EARLY_SENTENCES':
      return 'LANGUAGE';
    default:
      return 'BABBLE'; // safe fallback
  }
}

const STAGE_VERSION = { INFANT: 1, BABBLE: 2, PROTO: 3, TODDLER: 4, LANGUAGE: 5 };

const SOUND_FIELD_LABEL = {
  INFANT:   'Heard any sounds like \'baba\' or \'dada\'?',
  BABBLE:   'What sound did they make?',
  PROTO:    'What sound did they make?',
  TODDLER:  'What did they say?',
  LANGUAGE: 'Write exactly what they said',
};

const SOUND_FIELD_PLACEHOLDER = {
  INFANT:   'e.g. baba, dada, mama',
  BABBLE:   'e.g. da, ba, ga',
  PROTO:    'e.g. baba, dada',
  TODDLER:  'e.g. mama, more, up',
  LANGUAGE: 'e.g. I want milk, more juice please',
};

// Concept picker enabled from PROTO (12m+)
const SHOWS_CONCEPTS = new Set(['PROTO', 'TODDLER', 'LANGUAGE']);
// Effectiveness question absent for LANGUAGE (24m+)
const SHOWS_EFFECTIVENESS = new Set(['INFANT', 'BABBLE', 'PROTO', 'TODDLER']);
// Notes absent for INFANT (0–6m) per spec §8
const SHOWS_NOTES = new Set(['BABBLE', 'PROTO', 'TODDLER', 'LANGUAGE']);

function FeedbackForm({ onSubmit, developmentalStage, intentKey, childId, apiCall }) {
  const [open, setOpen] = useState(false);
  const [responseType, setResponseType] = useState('');
  const [effectiveness, setEffectiveness] = useState('');
  const [wordToken, setWordToken] = useState('');
  const [transcription, setTranscription] = useState('');
  const [notes, setNotes] = useState('');
  const [concepts, setConcepts] = useState([]);
  const [selectedConcepts, setSelectedConcepts] = useState([]);

  const mode = getMode(developmentalStage);
  const isLanguage = mode === 'LANGUAGE';
  const orderedResponseTypes = orderByIntent(getResponseTypes(mode), intentKey);
  const showConcepts = SHOWS_CONCEPTS.has(mode);
  const showEffectiveness = SHOWS_EFFECTIVENESS.has(mode);
  const showNotes = SHOWS_NOTES.has(mode);

  // Fetch personal concept graph when picker is needed
  useEffect(() => {
    if (!open || !showConcepts || !childId || !apiCall) return;
    apiCall(`/child/${childId}/concepts`)
      .then(data => setConcepts((data.concepts || []).slice(0, 8)))
      .catch(() => {});
  }, [open, showConcepts, childId, apiCall]);

  // LANGUAGE: submit requires transcript or notes; others require response_type
  const canSubmit = isLanguage
    ? !!(transcription.trim() || notes.trim() || wordToken.trim())
    : !!responseType;

  const handleSubmit = () => {
    if (!canSubmit) return;
    const payload = {};

    if (responseType)          payload.response_type = responseType;
    if (effectiveness)         payload.effectiveness  = effectiveness;
    if (wordToken.trim())      payload.word_token     = wordToken.trim().toLowerCase();
    if (transcription.trim())  payload.transcription  = transcription.trim();

    // Merge concept selections into notes
    let notesText = notes.trim();
    if (selectedConcepts.length > 0) {
      const tag = `[Concepts: ${selectedConcepts.join(', ')}]`;
      notesText = notesText ? `${notesText} ${tag}` : tag;
    }
    if (notesText) payload.notes = notesText;

    payload.stage_version = STAGE_VERSION[mode] || 0;
    onSubmit(payload);
  };

  const toggleConcept = (label) =>
    setSelectedConcepts(prev =>
      prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
    );

  if (!open) {
    return (
      <div className="feedback-reveal">
        <button className="feedback-reveal-btn" onClick={() => setOpen(true)}>
          <span>What happened next?</span>
          <span className="feedback-reveal-hint">Share what you tried — helps Qleam learn</span>
        </button>
      </div>
    );
  }

  return (
    <div className="feedback-modal-overlay" onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
      <div className="feedback-modal">
      <div className="feedback-form-header">
        <span className="feedback-form-title">What happened next?</span>
        <button className="feedback-skip-btn" onClick={() => setOpen(false)}>Skip</button>
      </div>

      {/* What did you try — absent for LANGUAGE (24m+): child expressed clearly */}
      {!isLanguage && (
        <div className="feedback-group">
          <label className="feedback-label">
            {mode === 'TODDLER' ? 'What did you do?' : 'What did you try?'}
          </label>
          <div className="response-type-grid">
            {orderedResponseTypes.map(rt => (
              <button
                key={rt.key}
                type="button"
                className={`response-type-btn${responseType === rt.key ? ' selected' : ''}`}
                onClick={() => setResponseType(v => v === rt.key ? '' : rt.key)}
              >
                {rt.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* How did it go — absent for LANGUAGE per spec §8 */}
      {showEffectiveness && (
        <div className="feedback-group">
          <label className="feedback-label">
            How did it go? <span className="feedback-optional">(optional)</span>
          </label>
          <div className="effectiveness-row">
            {EFFECTIVENESS_OPTIONS.map(e => (
              <button
                key={e.key}
                type="button"
                className={`effectiveness-btn${effectiveness === e.key ? ` selected ${e.key}` : ''}`}
                onClick={() => setEffectiveness(v => v === e.key ? '' : e.key)}
              >
                {e.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Concept picker — starts at PROTO (12m+) per spec §8 */}
      {showConcepts && concepts.length > 0 && (
        <div className="feedback-group">
          <label className="feedback-label">
            {isLanguage ? 'What were they talking about?' : 'Things they may be interested in?'}
            <span className="feedback-optional"> (optional)</span>
          </label>
          <div className="concept-chips-row">
            {concepts.map(c => (
              <button
                key={c.concept_id}
                type="button"
                className={`concept-chip${selectedConcepts.includes(c.label) ? ' selected' : ''}`}
                onClick={() => toggleConcept(c.label)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* LANGUAGE: transcription is primary input; others: word/sound field */}
      {isLanguage ? (
        <div className="feedback-group">
          <label className="feedback-label">{SOUND_FIELD_LABEL.LANGUAGE}</label>
          <textarea
            className="transcript-input"
            placeholder={SOUND_FIELD_PLACEHOLDER.LANGUAGE}
            value={transcription}
            onChange={e => setTranscription(e.target.value)}
            rows={2}
          />
          <p className="transcript-primary-hint">What did they actually say?</p>
        </div>
      ) : (
        <div className="feedback-group">
          <label className="feedback-label">
            {SOUND_FIELD_LABEL[mode]}
            <span className="feedback-optional"> (optional)</span>
          </label>
          <input
            type="text"
            className="word-input"
            placeholder={SOUND_FIELD_PLACEHOLDER[mode]}
            value={wordToken}
            onChange={e => setWordToken(e.target.value)}
          />
        </div>
      )}

      {/* Notes — absent for INFANT (0–6m) per spec §8 */}
      {showNotes && (
        <div className="feedback-group">
          <label className="feedback-label">
            What did you notice?
            <span className="feedback-optional">
              {mode === 'PROTO' || isLanguage ? '' : ' (optional)'}
            </span>
          </label>
          <textarea
            className="notes-input"
            placeholder={
              isLanguage
                ? 'e.g. They seemed very excited, pointed at the dog…'
                : 'e.g. Baby calmed down quickly, seemed hungry after all…'
            }
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
          />
        </div>
      )}

      <button
        className="submit-feedback-btn"
        onClick={handleSubmit}
        disabled={!canSubmit}
      >
        Share feedback
      </button>
      </div>
    </div>
  );
}

export default FeedbackForm;
