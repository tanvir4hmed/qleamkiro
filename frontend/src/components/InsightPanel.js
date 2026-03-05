import React from 'react';

/**
 * InsightPanel — Dynamic display based on new insight_generator output.
 *
 * Only shows sections that have data. No empty labels.
 * Matches: display_type, headline, transcript, words_detected,
 *          word_age_match, emotion, insight_sections,
 *          adult_detected, age_mismatch, also_possible, dunstan_sound
 */

const DISPLAY_COLORS = {
  cry: '#FF6B6B',
  speech: '#4ECDC4',
  laugh: '#7CCB7C',
  silence: '#C7C7C7',
  noise: '#8A8A8A',
  mixed: '#FFE66D',
};

function hasVisibleData(value) {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  if (typeof value === 'string') return value.trim().length > 0;
  return true;
}

function RawDebugSection({ title, value }) {
  if (!hasVisibleData(value)) return null;
  return (
    <div className="raw-debug-block">
      <div className="raw-debug-block-title">{title}</div>
      <pre className="raw-debug-pre">{JSON.stringify(value, null, 2)}</pre>
    </div>
  );
}

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

function InsightPanel({ insight }) {
  if (!insight) return null;

  // ---- NEW data structure from insight_generator ----
  const {
    display_type,
    headline,
    headline_icon,
    description,
    adult_detected,
    // Transcript / words
    words_detected,
    transcript,
    word_age_match,
    // Cry emotion
    emotion,
    emotion_confidence,
    insight_sections,
    dunstan_sound,
    also_possible,
    age_mismatch,
    raw_debug,
    // Disclaimer (handled by parent)
  } = insight;

  // ---- BACKWARD COMPAT: old sessions with probable_intent ----
  const isOldFormat = !display_type && insight.probable_intent;
  if (isOldFormat) {
    return <OldFormatPanel insight={insight} />;
  }

  const borderColor = DISPLAY_COLORS[display_type] || DISPLAY_COLORS.mixed;

  return (
    <div className="insight-panel" style={{ borderLeftColor: borderColor }}>
      {/* Raw debug dump (shown before parent-facing insight) */}
      {raw_debug && (
        <div className="raw-debug-panel">
          <h3 className="raw-debug-title">Raw Extracted Data</h3>
          <RawDebugSection title="Type: Recording" value={raw_debug.recording} />
          <RawDebugSection title="Type: Quality Gate" value={raw_debug.quality_gate} />
          <RawDebugSection title="Type: Routing" value={raw_debug.routing} />
          <RawDebugSection title="Type: Sound Classification" value={raw_debug.sound_classification} />
          <RawDebugSection title="Type: Sound Summary" value={raw_debug.sound_summary} />
          <RawDebugSection title="Type: Acoustic Features" value={raw_debug.sound_features} />
          <RawDebugSection title="Type: Diarization" value={raw_debug.diarization} />
          <RawDebugSection title="Type: Biological" value={raw_debug.biological} />
          <RawDebugSection title="Type: Age Classifier" value={raw_debug.age_classification} />
          <RawDebugSection title="Type: Session Context" value={raw_debug.session_context} />
          <RawDebugSection title="Type: Analysis Output" value={raw_debug.analysis_output} />
          <RawDebugSection title="Type: Cry Model Debug" value={raw_debug.cry_model_debug} />
        </div>
      )}

      {/* Headline */}
      {headline && (
        <div className="insight-headline">
          {headline_icon && <span className="headline-icon">{headline_icon}</span>}
          <h2 className="headline-text">{headline}</h2>
        </div>
      )}

      {/* Description */}
      {description && (
        <p className="insight-description">{description}</p>
      )}

      {/* Adult warning */}
      {adult_detected && (
        <div className="insight-alert insight-alert--adult">
          🔊 Adult voice detected in this recording
        </div>
      )}

      {/* Transcript — always show if words found */}
      {words_detected && transcript && (
        <div className="insight-transcript-section">
          <div className="insight-section-header">
            <span className="section-icon">🗣️</span>
            <h3>Words Detected</h3>
          </div>
          <div className="transcript-text">"{transcript.text}"</div>
          <div className="transcript-meta">
            {transcript.word_count > 0 && (
              <span className="meta-chip">{transcript.word_count} word{transcript.word_count !== 1 ? 's' : ''}</span>
            )}
            {transcript.unique_words > 0 && transcript.unique_words !== transcript.word_count && (
              <span className="meta-chip">{transcript.unique_words} unique</span>
            )}
            {transcript.has_sentences && (
              <span className="meta-chip">sentences formed</span>
            )}
            {transcript.confidence > 0 && (
              <span className="meta-chip">{Math.round(transcript.confidence * 100)}% confidence</span>
            )}
          </div>
        </div>
      )}

      {/* Word age match */}
      {word_age_match && (
        <div className="insight-age-match">
          {word_age_match.speaker && (
            <span className={`speaker-badge speaker-badge--${word_age_match.speaker}`}>
              {word_age_match.speaker === 'adult' ? '👤 Adult speaker' :
               word_age_match.speaker === 'baby' ? '👶 Baby speaker' : '❓ Uncertain speaker'}
            </span>
          )}
          {word_age_match.summary && (
            <p className="age-match-summary">{word_age_match.summary}</p>
          )}
          {word_age_match.mismatch_warning && (
            <div className="insight-alert insight-alert--mismatch">
              ⚠️ {word_age_match.mismatch_warning}
            </div>
          )}
        </div>
      )}

      {/* Cry emotion confidence */}
      {emotion && emotion_confidence > 0 && (
        <div className="insight-emotion-section">
          <ConfidenceBar confidence={emotion_confidence} />
        </div>
      )}

      {/* Also possible emotions */}
      {also_possible && also_possible.length > 0 && (
        <div className="insight-also-possible">
          <span className="also-label">Also possible:</span>
          {also_possible.map((e, i) => (
            <span key={i} className="alt-emotion-chip">
              {e.icon || ''} {e.label} {e.score ? `${Math.round(e.score * 100)}%` : ''}
            </span>
          ))}
        </div>
      )}

      {/* Dunstan sound reference (0-3m runtime scope) */}
      {dunstan_sound && (
        <div className="insight-dunstan">
          <span className="dunstan-label">Dunstan sound:</span>
          <span className="dunstan-value">{dunstan_sound}</span>
        </div>
      )}

      {/* Three insight cards (cry emotion) */}
      {insight_sections && (
        <div className="insight-sections">
          {insight_sections.what_i_hear && (
            <div className="insight-block insight-block--hear">
              <div className="insight-block-header">
                <span className="insight-block-icon">👂</span>
                <h4>What I'm hearing</h4>
              </div>
              <p>{insight_sections.what_i_hear}</p>
            </div>
          )}
          {insight_sections.what_it_means && (
            <div className="insight-block insight-block--means">
              <div className="insight-block-header">
                <span className="insight-block-icon">💭</span>
                <h4>What it might mean</h4>
              </div>
              <p>{insight_sections.what_it_means}</p>
            </div>
          )}
          {insight_sections.what_to_try && insight_sections.what_to_try.length > 0 && (
            <div className="insight-block insight-block--try">
              <div className="insight-block-header">
                <span className="insight-block-icon">✋</span>
                <h4>What you can try</h4>
              </div>
              <ol className="try-list">
                {insight_sections.what_to_try.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      {/* Age mismatch (cry frequency or word) */}
      {age_mismatch && (
        <div className="insight-alert insight-alert--mismatch">
          ⚠️ Age Mismatch: {age_mismatch.message}
        </div>
      )}

    </div>
  );
}

/**
 * Backward compatibility for old sessions that used the previous insight format.
 * Shows basic info so old sessions don't break.
 */
function OldFormatPanel({ insight }) {
  const intent = insight.probable_intent || {};
  const sections = insight.insight_sections;

  return (
    <div className="insight-panel" style={{ borderLeftColor: '#C7C7C7' }}>
      {intent.label && (
        <div className="insight-headline">
          <h2 className="headline-text">{intent.label}</h2>
        </div>
      )}
      {intent.confidence > 0 && (
        <ConfidenceBar confidence={intent.confidence} />
      )}
      {sections && (
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
      )}
      {insight.suggested_response && !sections && (
        <p className="insight-description">{insight.suggested_response}</p>
      )}
    </div>
  );
}

export default InsightPanel;
