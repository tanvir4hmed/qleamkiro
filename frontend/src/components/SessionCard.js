import React from 'react';

const TYPE_COLORS = {
  cry: '#FF6B6B',
  speech: '#4ECDC4',
  laugh: '#7CCB7C',
  silence: '#C7C7C7',
  noise: '#8A8A8A',
  mixed: '#FFE66D',
};

function SessionCard({ session, onClick }) {
  const ts = session.timestamp ? new Date(session.timestamp) : null;
  const summary = session.insight_summary;

  // New format fields
  const displayType = summary?.display_type;
  const headline = summary?.headline;
  const icon = summary?.headline_icon;
  const isAdult = Boolean(summary?.is_adult);
  const hasConfidenceValue = summary?.emotion_confidence !== null && summary?.emotion_confidence !== undefined;
  const rawConfidence = hasConfidenceValue ? Number(summary?.emotion_confidence) : Number.NaN;
  const confidencePct = Number.isFinite(rawConfidence)
    ? Math.round(rawConfidence > 1 ? rawConfidence : rawConfidence * 100)
    : null;

  // Old format fallback
  const oldIntent = summary?.probable_intent;

  const dotColor = displayType
    ? (TYPE_COLORS[displayType] || TYPE_COLORS.mixed)
    : '#C7C7C7';

  return (
    <div className="session-card" onClick={onClick} role="button" tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick()}>
      <div className="session-card-header">
        <span className="session-date">{ts ? ts.toLocaleDateString() : '—'}</span>
        <span className="session-time-small">{ts ? ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
        <span className="deviation-dot" style={{ backgroundColor: dotColor }} title={displayType || 'unknown'} />
      </div>

      {/* New format: headline from insight */}
      {headline ? (
        <div className="session-card-summary">
          {icon && <span className="session-card-icon">{icon}</span>}
          <span className="session-card-headline">{headline}</span>
        </div>
      ) : oldIntent?.label ? (
        /* Old format fallback */
        <div className="session-card-summary">
          <span className="session-card-headline">{oldIntent.label}</span>
        </div>
      ) : summary === null ? (
        <div className="session-card-summary">
          <span className="session-card-headline session-card-processing">Processing...</span>
        </div>
      ) : null}

      {isAdult && (
        <span className="session-card-adult-tag">Adult voice</span>
      )}
      {confidencePct !== null && (
        <div className="intent-confidence">{confidencePct}% confidence</div>
      )}
    </div>
  );
}

export default SessionCard;
