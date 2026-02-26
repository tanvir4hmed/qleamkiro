import React from 'react';

const INTENT_COLORS = {
  hunger: '#FF6B6B',
  fatigue: '#A8E6CF',
  pain: '#FF4D4D',
  discomfort: '#FFE66D',
  closeness: '#4ECDC4',
  frustration: '#FF8B94',
  happy: '#7CCB7C',
  exploration: '#88D8B0',
  distress_unknown: '#C7C7C7',
  non_baby_spoof_noise: '#8A8A8A',
  // Backward compatibility
  connection: '#4ECDC4',
  overstimulation: '#FF8B94',
  unknown: '#C7C7C7',
};

const INTENT_ICONS = {
  hunger: '🍼',
  fatigue: '😴',
  pain: '🩹',
  discomfort: '😟',
  closeness: '🤗',
  frustration: '😣',
  happy: '😊',
  exploration: '🔍',
  distress_unknown: '📊',
  non_baby_spoof_noise: '🚫',
  // Backward compatibility
  connection: '🤗',
  overstimulation: '😣',
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
      <span className="confidence-label">{pct}% â€” {label}</span>
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
    emotion_profile,
    private_language_signal,
    speaker_gate,
    speaker_warning,
    acoustic_reliability,
    speech_transcript,
  } = insight;

  const intentKey = probable_intent?.key || 'distress_unknown';
  const color = INTENT_COLORS[intentKey] || INTENT_COLORS.distress_unknown;
  const icon = INTENT_ICONS[intentKey] || '📊';
  const sections = insight_sections || null;
  const topEmotions = emotion_profile?.top_states || [];

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

      {speaker_warning?.message && (
        <div className="alt-intents">
          <span className="alt-intents-label">Recording note: </span>
          <span className="alt-intent-chip">
            {speaker_warning.message}
          </span>
        </div>
      )}

      {speaker_gate?.status === 'UNCERTAIN' && (
        <div className="alt-intents">
          <span className="alt-intents-label">Speaker gate: </span>
          <span className="alt-intent-chip">UNCERTAIN</span>
        </div>
      )}

      {/* Emotion profile */}
      {topEmotions.length > 0 && (
        <div className="alt-intents">
          <span className="alt-intents-label">Emotional cues: </span>
          {topEmotions.map((e) => (
            <span key={e.key} className="alt-intent-chip">
              {e.key.replace(/_/g, ' ')} {Math.round((e.score || 0) * 100)}%
            </span>
          ))}
        </div>
      )}

      {/* 3-Section Insight */}
      {sections ? (
        <div className="insight-sections">
          {sections.what_i_hear && (
            <div className="insight-block insight-block--hear">
              <div className="insight-block-header">
                <span className="insight-block-icon">ðŸ‘‚</span>
                <h4>What I'm hearing</h4>
              </div>
              <p>{sections.what_i_hear}</p>
            </div>
          )}

          {sections.what_it_means && (
            <div className="insight-block insight-block--means">
              <div className="insight-block-header">
                <span className="insight-block-icon">ðŸ’­</span>
                <h4>What it might mean</h4>
              </div>
              <p>{sections.what_it_means}</p>
            </div>
          )}

          {sections.what_to_try && sections.what_to_try.length > 0 && (
            <div className="insight-block insight-block--try">
              <div className="insight-block-header">
                <span className="insight-block-icon">âœ‹</span>
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

      {probable_intent?.evidence?.weights && (
        <details className="narrative-details">
          <summary>Why this insight</summary>
          <div className="narrative-grid">
            <div className="narrative-item">
              <span className="narrative-key">Acoustic signal</span>
              <span className="narrative-val">{Math.round((probable_intent.evidence.weights.acoustic || 0) * 100)}%</span>
            </div>
            <div className="narrative-item">
              <span className="narrative-key">Research prior</span>
              <span className="narrative-val">{Math.round((probable_intent.evidence.weights.research || 0) * 100)}%</span>
            </div>
            <div className="narrative-item">
              <span className="narrative-key">Feedback history</span>
              <span className="narrative-val">{Math.round((probable_intent.evidence.weights.feedback || 0) * 100)}%</span>
            </div>
            <div className="narrative-item">
              <span className="narrative-key">Signal reliability</span>
              <span className="narrative-val">{Math.round((acoustic_reliability || probable_intent.evidence.acoustic_reliability || 0) * 100)}%</span>
            </div>
          </div>
        </details>
      )}

      {/* Private language signal */}
      {private_language_signal && (
        <details className="narrative-details">
          <summary>Private language signal</summary>
          <div className="narrative-grid">
            <div className="narrative-item">
              <span className="narrative-key">Status</span>
              <span className="narrative-val">{private_language_signal.level || 'forming'}</span>
            </div>
            <div className="narrative-item">
              <span className="narrative-key">Pattern repeats</span>
              <span className="narrative-val">{private_language_signal.cluster_frequency || 0}</span>
            </div>
            {private_language_signal.word_candidate && (
              <div className="narrative-item">
                <span className="narrative-key">Word candidate</span>
                <span className="narrative-val">{private_language_signal.word_candidate}</span>
              </div>
            )}
            <div className="narrative-item">
              <span className="narrative-key">What this means</span>
              <span className="narrative-val">{private_language_signal.message}</span>
            </div>
          </div>
        </details>
      )}

      {speech_transcript?.text && (
        <details className="narrative-details">
          <summary>Detected speech (AWS Transcribe)</summary>
          <div className="narrative-grid">
            <div className="narrative-item">
              <span className="narrative-key">Language</span>
              <span className="narrative-val">{speech_transcript.language_code || 'unknown'}</span>
            </div>
            <div className="narrative-item">
              <span className="narrative-key">Transcript</span>
              <span className="narrative-val">{speech_transcript.text}</span>
            </div>
          </div>
        </details>
      )}
    </div>
  );
}

export default InsightPanel;

