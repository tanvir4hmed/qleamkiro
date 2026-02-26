import React, { useState } from 'react';

// Stage labels with age range context so parents aren't confused
// e.g. "First Words" alone sounds like "we heard a first word in this recording"
const STAGE_LABELS = {
  NEWBORN:           { label: 'Newborn',             age: '0–3 months' },
  EARLY_VOCAL:       { label: 'Early Vocalisation',  age: '3–6 months' },
  CANONICAL_BABBLE:  { label: 'Canonical Babbling',  age: '6–9 months' },
  PROTO_WORDS:       { label: 'Proto-Words',          age: '9–12 months' },
  FIRST_WORDS:       { label: 'Emerging Words',       age: '12–18 months' },
  WORD_COMBINATIONS: { label: 'Word Combinations',    age: '18–24 months' },
  EARLY_SENTENCES:   { label: 'Early Sentences',      age: '24 months+' },
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

  const stageInfo = STAGE_LABELS[current_stage] || { label: current_stage, age: '' };
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
            <span className="stage-badge">
              {stageInfo.label}
              {stageInfo.age && <span className="stage-age-range"> · {stageInfo.age}</span>}
            </span>
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
