import React from 'react';

const INTENT_COLORS = {
  hunger: '#FF6B6B',
  connection: '#4ECDC4',
  discomfort: '#FFE66D',
  overstimulation: '#FF8B94',
  fatigue: '#A8E6CF',
  exploration: '#88D8B0',
  unknown: '#C7C7C7',
};

function ConfidenceBar({ confidence }) {
  const pct = Math.round((confidence || 0) * 100);
  const color = pct >= 60 ? '#4ECDC4' : pct >= 30 ? '#FFE66D' : '#C7C7C7';
  return (
    <div className="confidence-bar-container">
      <div className="confidence-bar-wrapper">
        <div className="confidence-bar" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="confidence-label">{pct}% confidence</span>
    </div>
  );
}

function InsightPanel({ insight }) {
  if (!insight) return null;
  const { probable_intent, suggested_response } = insight;
  const intentKey = probable_intent?.key || 'unknown';
  const color = INTENT_COLORS[intentKey] || INTENT_COLORS.unknown;

  return (
    <div className="insight-panel" style={{ borderLeftColor: color }}>
      {probable_intent && (
        <div className="intent-section">
          <div className="intent-badge" style={{ backgroundColor: color }}>
            {probable_intent.label}
          </div>
          <ConfidenceBar confidence={probable_intent.confidence} />
        </div>
      )}
      {suggested_response && (
        <div className="suggested-response">
          <h3>Suggested Response</h3>
          <p>{suggested_response}</p>
        </div>
      )}
    </div>
  );
}

export default InsightPanel;
