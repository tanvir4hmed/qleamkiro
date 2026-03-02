import React from 'react';

/**
 * InsightPanel — Dynamic display based on new insight_generator output.
 *
 * Only shows sections that have data. No empty labels.
 * Includes sound classification graph for visual appeal.
 */

const DISPLAY_COLORS = {
  cry: '#FF6B6B',
  speech: '#4ECDC4',
  laugh: '#7CCB7C',
  silence: '#C7C7C7',
  noise: '#8A8A8A',
  mixed: '#FFE66D',
  adult: '#B0B0B0',
};

const SCORE_LABELS = {
  speech: { label: 'Speech', icon: '🗣️', color: '#4ECDC4' },
  cry: { label: 'Cry', icon: '😢', color: '#FF6B6B' },
  laugh: { label: 'Laugh', icon: '😄', color: '#7CCB7C' },
  silence: { label: 'Silence', icon: '🔇', color: '#C7C7C7' },
  noise: { label: 'Noise', icon: '🔊', color: '#8A8A8A' },
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

/**
 * Sound classification graph — horizontal bars showing what the
 * classifier detected (speech, cry, laugh, silence, noise).
 * Highlights the dominant sound type.
 */
function ClassificationGraph({ scores, dominantType }) {
  if (!scores || Object.keys(scores).length === 0) return null;

  // Sort: dominant first, then by score descending
  const entries = Object.entries(scores)
    .filter(([key]) => SCORE_LABELS[key])
    .sort((a, b) => {
      if (a[0] === dominantType) return -1;
      if (b[0] === dominantType) return 1;
      return b[1] - a[1];
    });

  // Only show bars with score > 0
  const visible = entries.filter(([, val]) => val > 0.01);
  if (visible.length === 0) return null;

  return (
    <div className="classification-graph">
      <div className="classification-graph-header">
        <span className="section-icon">📊</span>
        <h3>Sound Analysis</h3>
      </div>
      <div className="classification-bars">
        {visible.map(([key, val]) => {
          const meta = SCORE_LABELS[key];
          const pct = Math.round(val * 100);
          const isDominant = key === dominantType;
          return (
            <div key={key} className={`class-bar-row ${isDominant ? 'class-bar-dominant' : ''}`}>
              <span className="class-bar-icon">{meta.icon}</span>
              <span className="class-bar-label">{meta.label}</span>
              <div className="class-bar-track">
                <div
                  className="class-bar-fill"
                  style={{
                    width: `${pct}%`,
                    backgroundColor: isDominant ? meta.color : `${meta.color}66`,
                  }}
                />
              </div>
              <span className="class-bar-pct">{pct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function InsightPanel({ insight }) {
  if (!insight) return null;

  const {
    display_type,
    headline,
    headline_icon,
    description,
    adult_detected,
    words_detected,
    transcript,
    word_age_match,
    emotion,
    emotion_confidence,
    insight_sections,
    dunstan_sound,
    also_possible,
    age_mismatch,
    private_language,
    classification_scores,
    sound_type,
    cry_section,
    cry_detected,
  } = insight;

  // Backward compat for old sessions
  const isOldFormat = !display_type && insight.probable_intent;
  if (isOldFormat) {
    return <OldFormatPanel insight={insight} />;
  }

  const borderColor = DISPLAY_COLORS[display_type] || DISPLAY_COLORS.mixed;

  return (
    <div className="insight-panel" style={{ borderLeftColor: borderColor }}>

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

      {/* Adult notice — only show extra alert if display_type is NOT 'adult'
           (when it IS 'adult', the headline already says it) */}
      {adult_detected && display_type !== 'adult' && (
        <div className="insight-alert insight-alert--adult">
          Another person detected in this recording
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

      {/* Dunstan sound reference (0-6m) */}
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

      {/* Private language match */}
      {private_language && private_language.matched && (
        <div className="insight-private-lang">
          <div className="insight-section-header">
            <span className="section-icon">🔤</span>
            <h3>Baby's Own Language</h3>
          </div>
          {private_language.parent_label && (
            <div className="private-lang-item">
              <span className="pl-label">Recognized as:</span>
              <span className="pl-value">"{private_language.parent_label}"</span>
            </div>
          )}
          {private_language.parent_description && (
            <div className="private-lang-item">
              <span className="pl-label">Meaning:</span>
              <span className="pl-value">{private_language.parent_description}</span>
            </div>
          )}
          <div className="private-lang-meta">
            {private_language.times_heard > 0 && (
              <span className="meta-chip">heard {private_language.times_heard} times</span>
            )}
            {private_language.confidence > 0 && (
              <span className="meta-chip">{Math.round(private_language.confidence * 100)}% match</span>
            )}
          </div>
        </div>
      )}

      {/* Cry section for mixed sounds (speech + cry detected together) */}
      {cry_detected && cry_section && (
        <div className="insight-cry-section">
          <div className="insight-section-header">
            <span className="section-icon">{cry_section.emotion_icon || '😢'}</span>
            <h3>Cry Also Detected</h3>
          </div>
          <p className="cry-section-label">{cry_section.emotion_label}</p>
          {cry_section.confidence > 0 && (
            <ConfidenceBar confidence={cry_section.confidence} />
          )}
          {cry_section.what_i_hear && (
            <div className="insight-block insight-block--hear">
              <div className="insight-block-header">
                <span className="insight-block-icon">👂</span>
                <h4>What I'm hearing</h4>
              </div>
              <p>{cry_section.what_i_hear}</p>
            </div>
          )}
          {cry_section.what_it_means && (
            <div className="insight-block insight-block--means">
              <div className="insight-block-header">
                <span className="insight-block-icon">💭</span>
                <h4>What it might mean</h4>
              </div>
              <p>{cry_section.what_it_means}</p>
            </div>
          )}
          {cry_section.what_to_try && cry_section.what_to_try.length > 0 && (
            <div className="insight-block insight-block--try">
              <div className="insight-block-header">
                <span className="insight-block-icon">✋</span>
                <h4>What you can try</h4>
              </div>
              <ol className="try-list">
                {cry_section.what_to_try.map((item, idx) => (
                  <li key={idx}>{item}</li>
                ))}
              </ol>
            </div>
          )}
          {cry_section.dunstan_sound && (
            <div className="insight-dunstan">
              <span className="dunstan-label">Dunstan sound:</span>
              <span className="dunstan-value">{cry_section.dunstan_sound}</span>
            </div>
          )}
        </div>
      )}

      {/* Sound Classification Graph */}
      <ClassificationGraph
        scores={classification_scores}
        dominantType={sound_type || display_type}
      />
    </div>
  );
}

/**
 * Backward compatibility for old sessions.
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
