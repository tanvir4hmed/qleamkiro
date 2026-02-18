import React, { useState } from 'react';

const RESPONSE_TYPES = [
  { key: 'hunger', label: '🍼 Feeding' },
  { key: 'connection', label: '🤗 Comfort & Hold' },
  { key: 'discomfort', label: '🩹 Check Discomfort' },
  { key: 'overstimulation', label: '🤫 Reduce Stimulation' },
  { key: 'fatigue', label: '😴 Sleep Routine' },
  { key: 'exploration', label: '🎵 Vocal Play' },
];

function FeedbackForm({ onSubmit }) {
  const [responseType, setResponseType] = useState('');
  const [effectiveness, setEffectiveness] = useState('');
  const [wordToken, setWordToken] = useState('');

  const canSubmit = responseType && effectiveness;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit({ response_type: responseType, effectiveness, word_token: wordToken });
  };

  return (
    <div className="feedback-form">
      <div className="feedback-group">
        <label>What did you try?</label>
        <div className="response-type-grid">
          {RESPONSE_TYPES.map(rt => (
            <button
              key={rt.key}
              className={`response-type-btn ${responseType === rt.key ? 'selected' : ''}`}
              onClick={() => setResponseType(rt.key)}
            >
              {rt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="feedback-group">
        <label>How did it work?</label>
        <div className="effectiveness-row">
          {['helpful', 'neutral', 'ineffective'].map(e => (
            <button
              key={e}
              className={`effectiveness-btn ${effectiveness === e ? 'selected' : ''} ${e}`}
              onClick={() => setEffectiveness(e)}
            >
              {e === 'helpful' ? '✓ Helped' : e === 'neutral' ? '~ Unsure' : '✗ Didn\'t Help'}
            </button>
          ))}
        </div>
      </div>

      <div className="feedback-group">
        <label>Did you hear a word? (optional)</label>
        <input
          type="text"
          placeholder="e.g. mama, dada, baba"
          value={wordToken}
          onChange={e => setWordToken(e.target.value.toLowerCase())}
          className="word-input"
        />
      </div>

      <button className="submit-feedback-btn" onClick={handleSubmit} disabled={!canSubmit}>
        Submit Feedback
      </button>
    </div>
  );
}

export default FeedbackForm;
