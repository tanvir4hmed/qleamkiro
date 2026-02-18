import React from 'react';

const DEVIATION_COLORS = { none: '#4ECDC4', low: '#88D8B0', moderate: '#FFE66D', high: '#FF6B6B' };

function SessionCard({ session, onClick }) {
  const ts = session.timestamp ? new Date(session.timestamp) : null;
  const devColor = DEVIATION_COLORS[session.deviation_level] || DEVIATION_COLORS.none;
  const intent = session.insight_summary?.probable_intent;

  return (
    <div className="session-card" onClick={onClick} role="button" tabIndex={0}
      onKeyDown={e => e.key === 'Enter' && onClick()}>
      <div className="session-card-header">
        <span className="session-date">{ts ? ts.toLocaleDateString() : '—'}</span>
        <span className="session-time-small">{ts ? ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}</span>
        <span className="deviation-dot" style={{ backgroundColor: devColor }} title={`Deviation: ${session.deviation_level}`} />
      </div>
      {intent && (
        <div className="session-intent">
          <span className="intent-label">{intent.label}</span>
          <span className="intent-confidence">{Math.round((intent.confidence || 0) * 100)}%</span>
        </div>
      )}
      {session.feature_scores && (
        <div className="feature-mini-bars">
          {Object.entries(session.feature_scores).map(([key, val]) => (
            <div key={key} className="mini-bar-row">
              <span className="mini-bar-label">{key.replace('_', ' ')}</span>
              <div className="mini-bar-track">
                <div className="mini-bar-fill" style={{ width: `${Math.round(val * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default SessionCard;
