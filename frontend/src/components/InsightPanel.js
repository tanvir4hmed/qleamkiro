import React, { useState, useEffect, useMemo } from 'react';
import EmotionRadar from './EmotionRadar';
import AcousticRadar from './AcousticRadar';
import DunstanSection from './DunstanSection';
import { pickNarrative, buildConfidenceMessage, buildAlsoPossibleText } from '../data/narratives';
import { pickSuggestions } from '../data/suggestions';

/**
 * InsightPanel — Phase 5 Dynamic UI
 *
 * Flowing narrative layout replacing the old static 3-card template.
 * Progressive reveal animation, radar charts, context-aware suggestions.
 */

const DISPLAY_COLORS = {
  cry: '#FF6B6B',
  speech: '#4ECDC4',
  laugh: '#7CCB7C',
  silence: '#C7C7C7',
  noise: '#8A8A8A',
  mixed: '#FFE66D',
};

// Primary action per emotion (for "also possible" text)
const PRIMARY_ACTIONS = {
  hungry: 'feeding',
  tired: 'a sleep routine',
  discomfort: 'a comfort check',
  gas: 'tummy massage',
  pain: 'checking for pain sources',
  burp: 'burping',
  content: 'what you\'re doing',
};

function stripDuplicateIconFromHeadline(headline, icon) {
  if (!headline || !icon || typeof headline !== 'string') return headline || '';
  if (!headline.startsWith(icon)) return headline;
  return headline.slice(icon.length).replace(/^[\s\-–—:]+/, '');
}

function hasVisibleData(value) {
  if (value === null || value === undefined) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  if (typeof value === 'string') return value.trim().length > 0;
  return true;
}

// Progressive reveal hook — sections appear sequentially
function useReveal(sectionCount, baseDelay = 150) {
  const [revealed, setRevealed] = useState(0);
  useEffect(() => {
    if (revealed >= sectionCount) return;
    const timer = setTimeout(() => setRevealed((r) => r + 1), baseDelay);
    return () => clearTimeout(timer);
  }, [revealed, sectionCount, baseDelay]);
  return revealed;
}

function ConfidenceBar({ confidence, message }) {
  const raw = Number(confidence);
  if (!Number.isFinite(raw)) return null;
  const normalized = raw > 1 ? raw / 100 : raw;
  const pct = Math.max(0, Math.min(100, Math.round(normalized * 100)));
  const color = pct >= 60 ? '#4ECDC4' : pct >= 30 ? '#FFE66D' : '#C7C7C7';
  return (
    <div className="confidence-section">
      <div className="confidence-bar-container">
        <div className="confidence-bar-wrapper">
          <div className="confidence-bar confidence-bar--animated" style={{ '--target-width': `${pct}%`, backgroundColor: color }} />
        </div>
        <span className="confidence-label">{pct}% confidence</span>
      </div>
      {message && <p className="confidence-message">{message}</p>}
    </div>
  );
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

// ---- CRY INSIGHT (full dynamic layout) ----
function CryInsight({ insight, childName, childId, ageDays, sessionCount }) {
  const {
    emotion,
    emotion_confidence,
    emotion_scores,
    top_emotions,
    acoustic_features,
    narrative_data,
    also_possible,
    dunstan_sound,
    dunstan_description,
    insight_sections,
  } = insight;

  const revealed = useReveal(8, 200);

  // Dynamic narrative (memoized so it doesn't re-pick on re-render)
  const narrative = useMemo(
    () => pickNarrative(emotion || 'discomfort', narrative_data, childName, childId),
    [emotion, narrative_data, childName, childId]
  );

  const confidenceMsg = useMemo(
    () => buildConfidenceMessage(emotion_confidence, sessionCount || 0, childName),
    [emotion_confidence, sessionCount, childName]
  );

  const alsoPossibleText = useMemo(
    () => buildAlsoPossibleText(also_possible, PRIMARY_ACTIONS[emotion] || 'the primary suggestion'),
    [also_possible, emotion]
  );

  // Context-aware suggestions
  const suggestions = useMemo(
    () => pickSuggestions(emotion || 'discomfort', { ageDays, childId, sessionCountToday: sessionCount || 0 }),
    [emotion, ageDays, childId, sessionCount]
  );

  return (
    <>
      {/* 1. Narrative text */}
      <div className={`insight-reveal ${revealed >= 1 ? 'revealed' : ''}`}>
        <p className="insight-narrative">{narrative}</p>
      </div>

      {/* 2. Confidence bar */}
      <div className={`insight-reveal ${revealed >= 2 ? 'revealed' : ''}`}>
        <ConfidenceBar confidence={emotion_confidence} message={confidenceMsg} />
      </div>

      {/* 3. Suggestions */}
      <div className={`insight-reveal ${revealed >= 3 ? 'revealed' : ''}`}>
        <div className="suggestion-section">
          <h4 className="suggestion-title">Try this</h4>
          <ul className="suggestion-list">
            {suggestions.map((s, i) => (
              <li key={i} className="suggestion-item">{s}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* 4. Also possible (woven into narrative) */}
      {alsoPossibleText && (
        <div className={`insight-reveal ${revealed >= 4 ? 'revealed' : ''}`}>
          <p className="insight-also-text">{alsoPossibleText}</p>
        </div>
      )}

      {/* 5. Radar charts */}
      <div className={`insight-reveal ${revealed >= 5 ? 'revealed' : ''}`}>
        <div className="radar-charts-row">
          <EmotionRadar
            emotionScores={emotion_scores}
            topEmotions={top_emotions}
            primaryEmotion={emotion}
          />
          <AcousticRadar acousticFeatures={acoustic_features} />
        </div>
      </div>

      {/* 6. Dunstan section */}
      <div className={`insight-reveal ${revealed >= 6 ? 'revealed' : ''}`}>
        <DunstanSection
          dunstanSound={dunstan_sound}
          dunstanDescription={dunstan_description}
          ageDays={ageDays}
        />
      </div>

      {/* 7. Fallback: static insight cards (if narrative_data missing — old sessions) */}
      {!narrative_data && insight_sections && (
        <div className={`insight-reveal ${revealed >= 7 ? 'revealed' : ''}`}>
          <StaticInsightCards sections={insight_sections} />
        </div>
      )}
    </>
  );
}

// ---- NON-CRY TYPES (speech, laugh, silence, noise, mixed) ----
function GenericInsight({ insight }) {
  const {
    description,
    words_detected,
    transcript,
    word_age_match,
    insight_sections,
  } = insight;

  return (
    <>
      {description && <p className="insight-description">{description}</p>}

      {/* Transcript */}
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
            {transcript.has_sentences && <span className="meta-chip">sentences formed</span>}
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
          {word_age_match.summary && <p className="age-match-summary">{word_age_match.summary}</p>}
          {word_age_match.mismatch_warning && (
            <div className="insight-alert insight-alert--mismatch">
              ⚠️ {word_age_match.mismatch_warning}
            </div>
          )}
        </div>
      )}

      {/* Static insight cards if present */}
      {insight_sections && <StaticInsightCards sections={insight_sections} />}
    </>
  );
}

// ---- Static 3-card fallback (backward compat + non-cry) ----
function StaticInsightCards({ sections }) {
  if (!sections) return null;
  return (
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
  );
}

// ---- MAIN COMPONENT ----
function InsightPanel({ insight, childName, childId, ageDays, sessionCount }) {
  if (!insight) return null;

  const { display_type, headline, headline_icon, adult_detected, raw_debug } = insight;
  const displayHeadline = stripDuplicateIconFromHeadline(headline, headline_icon);
  const showRawData = false;

  // Backward compat for old sessions
  const isOldFormat = !display_type && insight.probable_intent;
  if (isOldFormat) return <OldFormatPanel insight={insight} />;

  const borderColor = DISPLAY_COLORS[display_type] || DISPLAY_COLORS.mixed;
  const isCry = display_type === 'cry';

  return (
    <div className="insight-panel" style={{ borderLeftColor: borderColor }}>
      {showRawData && raw_debug && <DebugPanel raw_debug={raw_debug} />}

      {/* Headline badge */}
      {displayHeadline && (
        <div className="insight-headline insight-headline--animated">
          {headline_icon && <span className="headline-icon">{headline_icon}</span>}
          <h2 className="headline-text">{displayHeadline}</h2>
        </div>
      )}

      {/* Adult warning */}
      {adult_detected && (
        <div className="insight-alert insight-alert--adult">
          🔊 Adult voice detected in this recording
        </div>
      )}

      {/* Cry: full dynamic layout. Others: generic. */}
      {isCry && !adult_detected ? (
        <CryInsight
          insight={insight}
          childName={childName}
          childId={childId}
          ageDays={ageDays}
          sessionCount={sessionCount}
        />
      ) : (
        <GenericInsight insight={insight} />
      )}
    </div>
  );
}

// ---- Debug panel (collapsed by default) ----
function DebugPanel({ raw_debug }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="raw-debug-panel">
      <button className="debug-toggle-btn" onClick={() => setOpen(!open)}>
        {open ? '▾ Hide' : '▸ Show'} Raw Data
      </button>
      {open && (
        <div className="raw-debug-content">
          <RawDebugSection title="Recording" value={raw_debug.recording} />
          <RawDebugSection title="Quality Gate" value={raw_debug.quality_gate} />
          <RawDebugSection title="Routing" value={raw_debug.routing} />
          <RawDebugSection title="Sound Classification" value={raw_debug.sound_classification} />
          <RawDebugSection title="Sound Summary" value={raw_debug.sound_summary} />
          <RawDebugSection title="Acoustic Features" value={raw_debug.sound_features} />
          <RawDebugSection title="Diarization" value={raw_debug.diarization} />
          <RawDebugSection title="Biological" value={raw_debug.biological} />
          <RawDebugSection title="Age Classifier" value={raw_debug.age_classification} />
          <RawDebugSection title="Session Context" value={raw_debug.session_context} />
          <RawDebugSection title="Analysis Output" value={raw_debug.analysis_output} />
          <RawDebugSection title="Cry Model Debug" value={raw_debug.cry_model_debug} />
        </div>
      )}
    </div>
  );
}

// ---- Backward compat for very old sessions ----
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
      {sections && <StaticInsightCards sections={sections} />}
      {insight.suggested_response && !sections && (
        <p className="insight-description">{insight.suggested_response}</p>
      )}
    </div>
  );
}

export default InsightPanel;
