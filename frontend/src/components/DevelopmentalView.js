import React, { useState } from 'react';

const STAGE_LABELS = {
  NEWBORN: 'Newborn',
  EARLY_VOCAL: 'Early Vocal',
  CANONICAL_BABBLE: 'Canonical Babble',
  PROTO_WORDS: 'Proto-Words',
  FIRST_WORDS: 'First Words',
  WORD_COMBINATIONS: 'Word Combinations',
  EARLY_SENTENCES: 'Early Sentences',
};

const CBR_LABELS = {
  PRE_CANONICAL: 'Pre-canonical',
  EMERGING_CANONICAL: 'Emerging',
  CANONICAL_ESTABLISHED: 'Established',
};

const MILESTONE_LABELS = {
  FIRST_CANONICAL_BABBLE: 'First canonical babble',
  FIRST_PROTO_WORD_CANDIDATE: 'Proto-word candidate detected',
  FIRST_CONFIRMED_PROTO_WORD: 'Proto-word confirmed',
  LINGUISTIC_MODE_TRANSITION: 'Entered linguistic mode',
  CONCEPT_GRAPH_10_NODES: '10 personal concepts learned',
  CONCEPT_GRAPH_25_NODES: '25 personal concepts learned',
};

function DevelopmentalView({ data }) {
  const [expanded, setExpanded] = useState(false);

  if (!data) return null;

  const {
    current_stage,
    cbr = 0,
    cbr_trend,
    cbr_category,
    phi_label,
    milestones_this_session = [],
  } = data;

  const stageLabel = STAGE_LABELS[current_stage] || current_stage;
  const cbrLabel = CBR_LABELS[cbr_category] || cbr_category;
  const cbrPercent = Math.round(cbr * 100);
  const hasMilestones = milestones_this_session.length > 0;

  return (
    <div className="developmental-view">
      <button
        className="developmental-toggle"
        onClick={() => setExpanded(v => !v)}
        aria-expanded={expanded}
      >
        <span className="developmental-toggle-label">Development snapshot</span>
        {hasMilestones && <span className="milestone-dot" title="New milestone!" />}
        <span className="developmental-toggle-arrow">{expanded ? '▲' : '▼'}</span>
      </button>

      {expanded && (
        <div className="developmental-body">
          {/* Stage badge */}
          <div className="developmental-row">
            <span className="developmental-key">Stage</span>
            <span className="stage-badge">{stageLabel}</span>
          </div>

          {/* CBR bar */}
          <div className="developmental-row">
            <span className="developmental-key">Babble quality</span>
            <div className="cbr-bar-wrap">
              <div className="cbr-bar">
                <div
                  className="cbr-bar-fill"
                  style={{ width: `${cbrPercent}%` }}
                />
              </div>
              <span className="cbr-bar-label">
                {cbrLabel} {cbr_trend === 'RISING' ? '↑' : cbr_trend === 'FALLING' ? '↓' : ''}
              </span>
            </div>
          </div>

          {/* φ indicator */}
          <div className="developmental-row">
            <span className="developmental-key">Language readiness</span>
            <span className="phi-indicator">{phi_label}</span>
          </div>

          {/* Milestones */}
          {hasMilestones && (
            <div className="developmental-row">
              <span className="developmental-key">Milestones</span>
              <div className="milestone-list">
                {milestones_this_session.map(m => (
                  <span key={m} className="milestone-badge">
                    {MILESTONE_LABELS[m] || m}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default DevelopmentalView;
