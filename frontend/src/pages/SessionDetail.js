import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import InsightPanel from '../components/InsightPanel';
import FeedbackForm from '../components/FeedbackForm';
import FeatureChart from '../components/FeatureChart';
import DevelopmentalView from '../components/DevelopmentalView';
import SpeechAnalysisPanel from '../components/SpeechAnalysisPanel';

const HEALTH_FLAG_LABELS = {
  sick: { label: 'Feeling unwell today', color: '#FF6B6B' },
  fussy: { label: 'A bit fussy today', color: '#FFE66D' },
  tired: { label: 'Tired today', color: '#a29bfe' },
  teething: { label: 'Teething', color: '#fd79a8' },
};

const CONTEXT_LABELS = {
  feeding_minutes_ago: {
    15: 'just ate',
    45: 'ate about 30–60 min ago',
    90: 'ate about an hour ago',
    150: 'it\'s been over 2 hours since eating',
  },
  health_state: { well: 'doing well', sick: 'not feeling well', fussy: 'a bit fussy', tired: 'tired' },
  environment: { quiet: 'at home in a quiet space', noisy: 'in a noisier environment', travel: 'travelling', outdoor: 'outdoors' },
};

function ContextNote({ ctx }) {
  if (!ctx || !Object.keys(ctx).length) return null;
  const parts = [];
  if (ctx.feeding_minutes_ago != null)
    parts.push(CONTEXT_LABELS.feeding_minutes_ago[ctx.feeding_minutes_ago] || `last ate ${ctx.feeding_minutes_ago} min ago`);
  if (ctx.health_state && CONTEXT_LABELS.health_state[ctx.health_state])
    parts.push(CONTEXT_LABELS.health_state[ctx.health_state]);
  if (ctx.environment && CONTEXT_LABELS.environment[ctx.environment])
    parts.push(CONTEXT_LABELS.environment[ctx.environment]);
  if (!parts.length) return null;
  return (
    <div className="context-note">
      <span className="context-note-icon">📌</span>
      Context: {parts.join(', ')}.
    </div>
  );
}

function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [feedbackError, setFeedbackError] = useState(null);

  // Resolve child name from localStorage cache (populated by Dashboard)
  const getChildName = (childId) => {
    try {
      const cached = JSON.parse(localStorage.getItem('qleam_children') || '[]');
      return cached.find(c => c.child_id === childId)?.name || '';
    } catch (_) { return ''; }
  };

  const getAuthHeaders = async () => {
    const s = await fetchAuthSession();
    const token = s.tokens?.idToken?.toString();
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  };

  const apiCall = useCallback(async (path, options = {}) => {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers: { ...headers, ...options.headers } });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, []);

  useEffect(() => {
    let pollInterval;
    let pollCount = 0;
    const MAX_POLLS = 20; // 20 × 3s = 60s max wait

    const fetchInsight = async () => {
      try {
        const data = await apiCall(`/session/${sessionId}/insight`);
        if (data.status === 'processing') {
          pollCount += 1;
          if (pollCount >= MAX_POLLS) {
            setError('Analysis is taking longer than expected. Please record a new session.');
            setLoading(false);
            return;
          }
          // Still processing — poll every 3 seconds
          pollInterval = setTimeout(fetchInsight, 3000);
        } else {
          setSession(data);
          setLoading(false);
        }
      } catch (err) {
        setError('Could not load session analysis. Please go back and try again.');
        setLoading(false);
      }
    };
    fetchInsight();
    return () => clearTimeout(pollInterval);
  }, [sessionId, apiCall]);

  const handleFeedback = async (feedbackData) => {
    setFeedbackError(null);
    try {
      const developmentalStage = session?.insight?.developmental_stage || '';
      const payload = { ...feedbackData };
      if (developmentalStage) payload.developmental_stage = developmentalStage;
      await apiCall(`/session/${sessionId}/feedback`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      setFeedbackSubmitted(true);
    } catch (err) {
      setFeedbackError('Could not submit feedback. Please try again.');
    }
  };

  // Derive child name: from session data (API v2) or localStorage fallback
  const childName = session?.child_name || getChildName(session?.child_id || '');

  if (loading) {
    return (
      <div className="session-detail loading-state">
        <div className="spinner" />
        <p>Analyzing your baby's sounds…</p>
        <p className="loading-sub">This usually takes 10–20 seconds</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="session-detail error-state">
        <p className="error-msg">{error}</p>
        <button onClick={() => navigate('/')}>Back to Dashboard</button>
      </div>
    );
  }

  const insight = session?.insight;
  const sessionCtx = session?.session_context;
  const healthFlag = HEALTH_FLAG_LABELS[sessionCtx?.health_state];

  // Phase 10: stage-aware insight section label
  const sessionTypeLabel = session?.session_type_label || (() => {
    const stage = insight?.developmental_stage || session?.developmental_stage || '';
    if (['EARLY_SENTENCES'].includes(stage)) return 'Language Session';
    if (['FIRST_WORDS', 'WORD_COMBINATIONS'].includes(stage)) return 'Communication Session';
    return 'Vocalization Analysis';
  })();

  return (
    <div className="session-detail">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>

      <h1>{childName ? `${childName}'s Session` : 'Session Analysis'}</h1>
      <p className="session-type-label">{sessionTypeLabel}</p>
      <p className="session-time">{new Date(session?.timestamp).toLocaleString()}</p>

      {/* Health flag — shown when parent reported being unwell / fussy */}
      {healthFlag && (
        <div className="health-flag" style={{ borderColor: healthFlag.color, color: healthFlag.color }}>
          <span className="health-flag-icon">⚠</span> {healthFlag.label} — keep this in mind when interpreting the insight.
        </div>
      )}

      {/* Context acknowledgment */}
      <ContextNote ctx={sessionCtx} />

      {insight && (
        <>
          {/* Feature Chart — show whenever acoustic data was computed (not rejected) */}
          {insight.observed_pattern &&
           insight.insight_sections?.source !== 'quality-rejection' && (
            <section className="feature-section">
              <h2>Acoustic Features</h2>
              <FeatureChart features={insight.observed_pattern} />
            </section>
          )}

          {/* Insight Panel */}
          <section className="insight-section">
            <InsightPanel insight={insight} />
          </section>

          {/* Developmental snapshot — only shown when audio quality passed */}
          {session?.developmental_view &&
           insight.insight_sections?.source !== 'quality-rejection' && (
            <section className="developmental-section">
              <DevelopmentalView data={session.developmental_view} />
            </section>
          )}

          {/* Speech analysis (Phase 7 — LINGUISTIC mode only) */}
          {session?.speech_analysis && (
            <section className="speech-analysis-section">
              <SpeechAnalysisPanel data={session.speech_analysis} />
            </section>
          )}

          {/* Concept chips (Phase 6) — only shown when parent has confirmed evidence */}
          {(() => {
            const cd = session?.concept_decode;
            // Filter to concepts with actual parent-confirmed evidence
            const evidenced = (cd?.top_concepts || []).filter(c => c.evidence_count > 0);
            if (!cd || evidenced.length === 0) return null;
            return (
              <section className="concept-decode-section">
                <h2>Concepts Your Baby May Be Expressing</h2>
                <div className="concept-decode-chips">
                  {evidenced.map(c => (
                    <span key={c.label} className="concept-decode-chip">
                      {c.label}
                      <span className="concept-conf">
                        {(c.confidence * 100).toFixed(0)}%
                      </span>
                    </span>
                  ))}
                </div>
                {cd.is_unknown_cluster && (
                  <p className="unknown-cluster-msg">
                    {cd.unknown_flag_message}
                  </p>
                )}
              </section>
            );
          })()}

          {/* Semantic Alignment */}
          {insight.semantic_alignment && (
            <section className="semantic-section">
              <h2>Word Pattern Detected</h2>
              <div className="semantic-card">
                <span className="word-token">"{insight.semantic_alignment.word_detected}"</span>
                <span className="confidence">
                  Confidence: {(insight.semantic_alignment.alignment_confidence * 100).toFixed(0)}%
                </span>
              </div>
            </section>
          )}

          {/* Feedback — optional, gentle */}
          {!feedbackSubmitted ? (
            <section className="feedback-section">
              {feedbackError && (
                <p className="feedback-error">{feedbackError}</p>
              )}
              <FeedbackForm
                onSubmit={handleFeedback}
                developmentalStage={session?.insight?.developmental_stage}
                intentKey={insight?.probable_intent?.key}
                childId={session?.child_id}
                apiCall={apiCall}
              />
            </section>
          ) : (
            <div className="feedback-thanks">
              ✓ Thank you — this helps Qleam understand your baby better.
            </div>
          )}

          {/* Disclaimer */}
          <p className="disclaimer">{insight.note}</p>
        </>
      )}
    </div>
  );
}

export default SessionDetail;
