import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import InsightPanel from '../components/InsightPanel';
import FeedbackForm from '../components/FeedbackForm';
import FeatureChart from '../components/FeatureChart';
import DevelopmentalView from '../components/DevelopmentalView';
import SpeechAnalysisPanel from '../components/SpeechAnalysisPanel';

function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [feedbackError, setFeedbackError] = useState(null);

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

  if (loading) {
    return (
      <div className="session-detail loading-state">
        <div className="spinner" />
        <p>Analyzing your baby's sounds...</p>
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

  return (
    <div className="session-detail">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>

      <h1>Session Analysis</h1>
      <p className="session-time">{new Date(session?.timestamp).toLocaleString()}</p>

      {insight && (
        <>
          {/* Feature Chart */}
          {insight.observed_pattern && (
            <section className="feature-section">
              <h2>Acoustic Features</h2>
              <FeatureChart features={insight.observed_pattern} />
            </section>
          )}

          {/* Insight Panel */}
          <section className="insight-section">
            <InsightPanel insight={insight} />
          </section>

          {/* Developmental snapshot (Phase 6) */}
          {session?.developmental_view && (
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

          {/* Concept chips (Phase 6) */}
          {session?.concept_decode?.top_concepts?.length > 0 && (
            <section className="concept-decode-section">
              <h2>Top Concepts Detected</h2>
              <div className="concept-decode-chips">
                {session.concept_decode.top_concepts.map(c => (
                  <span key={c.label} className="concept-decode-chip">
                    {c.label}
                    <span className="concept-conf">
                      {(c.confidence * 100).toFixed(0)}%
                    </span>
                  </span>
                ))}
              </div>
              {session.concept_decode.is_unknown_cluster && (
                <p className="unknown-cluster-msg">
                  {session.concept_decode.unknown_flag_message}
                </p>
              )}
            </section>
          )}

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
