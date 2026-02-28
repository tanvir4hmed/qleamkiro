import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import InsightPanel from '../components/InsightPanel';
import FeedbackForm from '../components/FeedbackForm';

/**
 * SessionDetail — Clean, simple session analysis page.
 *
 * Shows only what's available:
 * 1. Insight (dynamic based on sound type)
 * 2. Feedback form (cry emotion + baby language, age-appropriate)
 * 3. Disclaimer
 */

function SessionDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [error, setError] = useState(null);
  const [feedbackError, setFeedbackError] = useState(null);

  const getChildName = (childId) => {
    try {
      const cached = JSON.parse(localStorage.getItem('qleam_children') || '[]');
      return cached.find(c => c.child_id === childId)?.name || '';
    } catch (_) { return ''; }
  };

  const getChildAgeDays = (childId) => {
    try {
      const cached = JSON.parse(localStorage.getItem('qleam_children') || '[]');
      const child = cached.find(c => c.child_id === childId);
      if (child?.birth_date) {
        const birth = new Date(child.birth_date);
        const now = new Date();
        return Math.floor((now - birth) / (1000 * 60 * 60 * 24));
      }
    } catch (_) {}
    return null;
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
    let pollTimeout;
    let pollCount = 0;
    const MAX_POLLS = 20;
    let cancelled = false;

    const fetchInsight = async () => {
      try {
        const data = await apiCall(`/session/${sessionId}/insight`);
        if (cancelled) return;

        if (data.status === 'processing') {
          pollCount += 1;
          if (pollCount >= MAX_POLLS) {
            setError('Analysis is taking longer than expected. Please try recording again.');
            setLoading(false);
            return;
          }
          // Progressive backoff: 2s, 2s, 3s, 3s, 4s, 5s...
          const delay = pollCount <= 2 ? 2000 : pollCount <= 4 ? 3000 : Math.min(pollCount * 1000, 5000);
          pollTimeout = setTimeout(fetchInsight, delay);
        } else {
          setSession(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError('Could not load analysis. Please go back and try again.');
          setLoading(false);
        }
      }
    };

    fetchInsight();
    return () => {
      cancelled = true;
      clearTimeout(pollTimeout);
    };
  }, [sessionId, apiCall]);

  const handleFeedback = async (feedbackData) => {
    setFeedbackError(null);
    try {
      await apiCall(`/session/${sessionId}/feedback`, {
        method: 'POST',
        body: JSON.stringify({
          ...feedbackData,
          session_id: sessionId,
        }),
      });
      setFeedbackSubmitted(true);
    } catch (err) {
      setFeedbackError('Could not submit feedback. Please try again.');
    }
  };

  const childName = session?.child_name || getChildName(session?.child_id || '');
  const ageDays = getChildAgeDays(session?.child_id || '');

  if (loading) {
    return (
      <div className="session-detail loading-state">
        <div className="spinner" />
        <p>Analyzing your baby's sounds...</p>
        <p className="loading-sub">This usually takes 10-20 seconds</p>
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
  const displayType = insight?.display_type || 'unknown';
  const hasInsight = insight && (insight.headline || insight.display_type);

  return (
    <div className="session-detail">
      <button className="back-btn" onClick={() => navigate('/')}>
        ← Back
      </button>

      <h1>{childName ? `${childName}'s Session` : 'Session Analysis'}</h1>
      <p className="session-time">
        {new Date(session?.timestamp).toLocaleString()}
      </p>

      {/* Main Insight */}
      {hasInsight ? (
        <>
          <section className="insight-section">
            <InsightPanel insight={insight} />
          </section>

          {/* Feedback */}
          {!feedbackSubmitted ? (
            <section className="feedback-section">
              {feedbackError && (
                <p className="feedback-error">{feedbackError}</p>
              )}
              <FeedbackForm
                onSubmit={handleFeedback}
                displayType={displayType}
                detectedEmotion={insight?.emotion}
                ageDays={ageDays}
                isAdult={insight?.adult_detected || insight?.is_adult || false}
              />
            </section>
          ) : (
            <div className="feedback-thanks">
              ✓ Thank you — your feedback helps Qleam learn!
            </div>
          )}

          {/* Disclaimer */}
          {insight.disclaimer && (
            <p className="disclaimer">{insight.disclaimer}</p>
          )}
        </>
      ) : (
        <div className="no-insight">
          <p>No analysis data available for this session.</p>
        </div>
      )}
    </div>
  );
}

export default SessionDetail;
