import React, { useState, useEffect } from 'react';

const RESPONSE_TYPES = [
  { key: 'hunger', label: '🍼 Tried feeding' },
  { key: 'connection', label: '🤗 Comforted & held' },
  { key: 'discomfort', label: '🩹 Checked for discomfort' },
  { key: 'overstimulation', label: '🤫 Reduced stimulation' },
  { key: 'fatigue', label: '😴 Started sleep routine' },
  { key: 'exploration', label: '🎵 Played & talked' },
];

// Map developmental_stage string → UI mode
function getMode(developmentalStage) {
  if (!developmentalStage) return 'transition';
  if (['NEWBORN', 'EARLY_VOCAL'].includes(developmentalStage)) return 'pre_linguistic';
  if (['CANONICAL_BABBLE', 'PROTO_WORDS'].includes(developmentalStage)) return 'transition';
  return 'linguistic'; // FIRST_WORDS, WORD_COMBINATIONS, EARLY_SENTENCES
}

const STAGE_VERSION = { pre_linguistic: 1, transition: 2, linguistic: 3 };

const WORD_FIELD_LABELS = {
  pre_linguistic: 'Heard any sounds like \'baba\' or \'dada\'?',
  transition: 'Did you hear a word?',
  linguistic: 'What did your baby say?',
};

function FeedbackForm({ onSubmit, developmentalStage, childId, apiCall }) {
  const [open, setOpen] = useState(false);
  const [responseType, setResponseType] = useState('');
  const [effectiveness, setEffectiveness] = useState('');
  const [wordToken, setWordToken] = useState('');
  const [notes, setNotes] = useState('');
  const [concepts, setConcepts] = useState([]);
  const [selectedConcepts, setSelectedConcepts] = useState([]);

  const mode = getMode(developmentalStage);
  const isLinguistic = mode === 'linguistic';

  // Fetch personal concepts for LINGUISTIC stage when form opens
  useEffect(() => {
    if (!open || !isLinguistic || !childId || !apiCall) return;
    apiCall(`/child/${childId}/concepts`)
      .then(data => setConcepts((data.concepts || []).slice(0, 8)))
      .catch(() => {/* non-fatal — concept picker just won't appear */});
  }, [open, isLinguistic, childId, apiCall]);

  const canSubmit = !!responseType;

  const handleSubmit = () => {
    if (!canSubmit) return;
    const payload = { response_type: responseType };
    if (effectiveness) payload.effectiveness = effectiveness;
    if (wordToken.trim()) payload.word_token = wordToken.trim().toLowerCase();

    // Merge selected concept labels into notes
    let notesText = notes.trim();
    if (selectedConcepts.length > 0) {
      const conceptNote = `[Concepts: ${selectedConcepts.join(', ')}]`;
      notesText = notesText ? `${notesText} ${conceptNote}` : conceptNote;
    }
    if (notesText) payload.notes = notesText;

    payload.stage_version = STAGE_VERSION[mode] || 0;
    onSubmit(payload);
  };

  const toggleConcept = (label) => {
    setSelectedConcepts(prev =>
      prev.includes(label) ? prev.filter(l => l !== label) : [...prev, label]
    );
  };

  if (!open) {
    return (
      <div className="feedback-reveal">
        <button className="feedback-reveal-btn" onClick={() => setOpen(true)}>
          What happened next?
          <span className="feedback-reveal-hint">Share what you tried — helps me learn</span>
        </button>
      </div>
    );
  }

  return (
    <div className="feedback-form">
      <div className="feedback-form-header">
        <span className="feedback-form-title">What happened next?</span>
        <button className="feedback-skip-btn" onClick={() => setOpen(false)}>Skip</button>
      </div>

      {/* What did you try */}
      <div className="feedback-group">
        <label className="feedback-label">What did you try?</label>
        <div className="response-type-grid">
          {RESPONSE_TYPES.map(rt => (
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

      {/* How did it work — optional */}
      <div className="feedback-group">
        <label className="feedback-label">How did it go? <span className="feedback-optional">(optional)</span></label>
        <div className="effectiveness-row">
          {[
            { key: 'helpful', label: '✓ Helped' },
            { key: 'neutral', label: '~ Hard to tell' },
            { key: 'ineffective', label: '✗ Didn\'t help' },
          ].map(e => (
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

      {/* Concept picker — LINGUISTIC stage only, when concepts are available */}
      {isLinguistic && concepts.length > 0 && (
        <div className="feedback-group">
          <label className="feedback-label">
            Things baby may be interested in?
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

      {/* Word / sound field — label varies by stage */}
      <div className="feedback-group">
        <label className="feedback-label">
          {WORD_FIELD_LABELS[mode]}
          <span className="feedback-optional"> (optional)</span>
        </label>
        <input
          type="text"
          placeholder={mode === 'pre_linguistic' ? 'e.g. baba, dada, mama' : 'e.g. mama, more, up'}
          value={wordToken}
          onChange={e => setWordToken(e.target.value)}
          className="word-input"
        />
      </div>

      {/* Notes — optional */}
      <div className="feedback-group">
        <label className="feedback-label">What did you notice? <span className="feedback-optional">(optional)</span></label>
        <textarea
          className="notes-input"
          placeholder="e.g. Baby calmed down quickly, seemed hungry after all..."
          value={notes}
          onChange={e => setNotes(e.target.value)}
          rows={2}
        />
      </div>

      <button
        className="submit-feedback-btn"
        onClick={handleSubmit}
        disabled={!canSubmit}
      >
        Share feedback
      </button>
    </div>
  );
}

export default FeedbackForm;
