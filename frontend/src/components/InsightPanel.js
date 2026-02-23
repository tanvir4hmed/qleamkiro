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

const INTENT_ICONS = {
  hunger: '🍼',
  connection: '💛',
  discomfort: '😟',
  overstimulation: '🌀',
  fatigue: '😴',
  exploration: '🔍',
  unknown: '📊',
};

function ConfidenceBar({ confidence }) {
  const pct = Math.round((confidence || 0) * 100);
  const color = pct >= 60 ? '#4ECDC4' : pct >= 30 ? '#FFE66D' : '#C7C7C7';
  const label = pct >= 60 ? 'strong signal' : pct >= 30 ? 'emerging pattern' : 'early pattern';
  return (
    <div className="confidence-bar-container">
      <div className="confidence-bar-wrapper">
        <div className="confidence-bar" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="confidence-label">{pct}% — {label}</span>
    </div>
  );
}

function NarrativeGrid({ narrative }) {
  const labels = {
    emotional_tone: 'Tone',
    sound_pattern: 'Pattern',
    repetition: 'Sounds',
    continuity: 'Duration',
    vs_baseline: 'vs. Usual',
  };
  return (
    <div className="narrative-grid">
      {Object.entries(narrative).map(([key, val]) => (
        <div key={key} className="narrative-item">
          <span className="narrative-key">{labels[key] || key}</span>
          <span className="narrative-val">{val}</span>
        </div>
      ))}
    </div>
  );
}

function InsightPanel({ insight }) {
  if (!insight) return null;

  const {
    probable_intent,
    insight_sections,
    feature_narrative,
    suggested_response,
  } = insight;

  const intentKey = probable_intent?.key || 'unknown';
  const color = INTENT_COLORS[intentKey] || INTENT_COLORS.unknown;
  const icon = INTENT_ICONS[intentKey] || '📊';
  const sections = insight_sections || null;

  // Alt intents (excluding top one)
  const altIntents = probable_intent?.top_intents?.slice(1, 3) || [];

  return (
    <div className="insight-panel" style={{ borderLeftColor: color }}>

      {/* Intent + Confidence */}
      {probable_intent && (
        <div className="intent-section">
          <div className="intent-badge" style={{ backgroundColor: color }}>
            <span className="intent-icon">{icon}</span>
            {probable_intent.label}
          </div>
          <ConfidenceBar confidence={probable_intent.confidence} />

          {altIntents.length > 0 && (
            <div className="alt-intents">
              <span className="alt-intents-label">Also possible: </span>
              {altIntents.map((i) => (
                <span key={i.key} className="alt-intent-chip">
                  {INTENT_ICONS[i.key] || ''} {i.label} {Math.round(i.weight * 100)}%
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3-Section Insight */}
      {sections ? (
        <div className="insight-sections">
          {sections.what_i_hear && (
            <div className="insight-block insight-block--hear">
              <div className="insight-block-header">
                <span className="insight-block-icon">👂</span>
                <h4>What I'm hearing</h4>
              </div>
              <p>{sections.what_i_hear}</p>
            </div>
          )}

          {sections.what_it_means && (
            <div className="insight-block insight-block--means">
              <div className="insight-block-header">
                <span className="insight-block-icon">💭</span>
                <h4>What it might mean</h4>
              </div>
              <p>{sections.what_it_means}</p>
            </div>
          )}

          {sections.what_to_try && sections.what_to_try.length > 0 && (
            <div className="insight-block insight-block--try">
              <div className="insight-block-header">
                <span className="insight-block-icon">✋</span>
                <h4>What you can try</h4>
              </div>
              <ol className="try-list">
                {sections.what_to_try.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      ) : suggested_response ? (
        <div className="suggested-response">
          <h3>Suggested Response</h3>
          <p>{suggested_response}</p>
        </div>
      ) : null}

      {/* Audio Characteristics (collapsible) */}
      {feature_narrative && (
        <details className="narrative-details">
          <summary>Audio characteristics</summary>
          <NarrativeGrid narrative={feature_narrative} />
        </details>
      )}
    </div>
  );
}

export default InsightPanel;
