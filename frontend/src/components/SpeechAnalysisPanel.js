import React from 'react';

const MILESTONE_LABELS = {
  FIRST_MLU_2: 'Two-word combinations',
  FIRST_MLU_3: 'Three-word sentences',
  VOCAB_SIZE_20: '20 confirmed words',
  VOCAB_SIZE_50: '50 confirmed words',
};

const PRAGMATIC_COLORS = {
  declaration: '#4ECDC4',
  request: '#FF6B6B',
  question: '#a29bfe',
  exclamation: '#fdcb6e',
};

function SpeechAnalysisPanel({ data }) {
  if (!data) return null;

  const {
    estimated_mlu,
    mlu_ema,
    vocabulary_size,
    pragmatic_type,
    fluency_score,
    milestones_this_session = [],
  } = data;

  const mluImproving = estimated_mlu > mlu_ema * 1.1;
  const fluencyPct = Math.round((fluency_score || 0) * 100);

  return (
    <div className="speech-analysis-panel">
      <h2>Language Development</h2>

      {/* MLU */}
      <div className="speech-mlu-row">
        <span className="speech-mlu-label">Mean Length of Utterance</span>
        <span className="speech-mlu-value">
          {estimated_mlu?.toFixed(1)}
          {mluImproving && <span className="speech-mlu-delta"> ↑ improving</span>}
        </span>
      </div>

      {/* Vocabulary */}
      <div className="speech-mlu-row">
        <span className="speech-mlu-label">Confirmed words</span>
        <span className="speech-mlu-value">{vocabulary_size}</span>
      </div>

      {/* Pragmatic type */}
      {pragmatic_type && (
        <div className="speech-mlu-row">
          <span className="speech-mlu-label">Utterance type</span>
          <span
            className={`pragmatic-badge pragmatic-${pragmatic_type}`}
            style={{ background: PRAGMATIC_COLORS[pragmatic_type] || '#b2bec3' }}
          >
            {pragmatic_type}
          </span>
        </div>
      )}

      {/* Fluency bar */}
      <div className="fluency-row">
        <span className="speech-mlu-label">Fluency</span>
        <div className="fluency-bar">
          <div className="fluency-bar-fill" style={{ width: `${fluencyPct}%` }} />
        </div>
        <span className="fluency-pct">{fluencyPct}%</span>
      </div>

      {/* Milestones */}
      {milestones_this_session.length > 0 && (
        <div className="speech-milestones">
          <p className="speech-milestones-title">Milestones reached this session</p>
          <div className="speech-milestone-badges">
            {milestones_this_session.map(m => (
              <span key={m} className="speech-milestone-badge">
                {MILESTONE_LABELS[m] || m}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default SpeechAnalysisPanel;
