import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';

const MILESTONE_LABELS = {
  FIRST_CANONICAL_BABBLE: 'First canonical babble',
  FIRST_PROTO_WORD_CANDIDATE: 'First proto-word candidate',
  FIRST_CONFIRMED_PROTO_WORD: 'First confirmed proto-word',
  LINGUISTIC_MODE_TRANSITION: 'Entered linguistic mode',
  CONCEPT_GRAPH_10_NODES: '10 confirmed concepts',
  CONCEPT_GRAPH_25_NODES: '25 confirmed concepts',
  FIRST_MLU_2: 'Two-word combinations',
  FIRST_MLU_3: 'Three-word sentences',
  VOCAB_SIZE_20: '20 confirmed words',
  VOCAB_SIZE_50: '50 confirmed words',
};

const STAGE_LABELS = {
  NEWBORN: 'Newborn',
  EARLY_VOCAL: 'Early Vocal',
  CANONICAL_BABBLE: 'Canonical Babble',
  PROTO_WORDS: 'Proto-Words',
  FIRST_WORDS: 'First Words',
  WORD_COMBINATIONS: 'Word Combinations',
  EARLY_SENTENCES: 'Early Sentences',
};

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function ProgressPage() {
  const { childId } = useParams();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const getAuthHeaders = async () => {
    const s = await fetchAuthSession();
    const token = s.tokens?.idToken?.toString();
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  };

  const apiCall = useCallback(async (path) => {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}${path}`, { headers });
    if (!res.ok) throw new Error(`API error ${res.status}`);
    return res.json();
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const [sessionsData, milestonesData] = await Promise.all([
          apiCall(`/child/${childId}/sessions`),
          apiCall(`/child/${childId}/milestones`),
        ]);
        setSessions(sessionsData.sessions || []);
        setMilestones(milestonesData.milestones || []);
      } catch (err) {
        setError('Could not load progress data. Please go back and try again.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [childId, apiCall]);

  if (loading) {
    return (
      <div className="progress-page loading-state">
        <div className="spinner" />
        <p>Loading progress...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="progress-page error-state">
        <p className="error-msg">{error}</p>
        <button onClick={() => navigate('/')}>Back to Dashboard</button>
      </div>
    );
  }

  // Build CBR history from last 10 sessions (most recent at top)
  const cbrHistory = sessions
    .slice(0, 10)
    .map(s => ({
      date: s.timestamp,
      cbr: s.developmental_view?.cbr ?? null,
      stage: s.developmental_view?.current_stage,
    }))
    .filter(s => s.cbr !== null);

  // Last session's developmental snapshot
  const lastDev = sessions[0]?.developmental_view;

  return (
    <div className="progress-page">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>
      <h1>Journey Progress</h1>

      {/* Current snapshot */}
      {lastDev ? (
        <section className="progress-snapshot">
          <h2>Current Snapshot</h2>
          <div className="progress-snapshot-row">
            <span className="stage-badge">{STAGE_LABELS[lastDev.current_stage] || lastDev.current_stage}</span>
            <span className="phi-indicator">{lastDev.phi_label}</span>
          </div>
          <div className="progress-snapshot-row">
            <span className="cbr-snapshot-label">Canonical Babbling Ratio</span>
            <div className="cbr-bar-wrap">
              <div className="cbr-bar-fill" style={{ width: `${Math.min(100, (lastDev.cbr || 0) * 100)}%` }} />
            </div>
            <span className="cbr-snapshot-pct">{((lastDev.cbr || 0) * 100).toFixed(0)}%</span>
          </div>
        </section>
      ) : (
        <section className="progress-snapshot">
          <p className="progress-empty">Record more sessions to see your child's developmental snapshot.</p>
        </section>
      )}

      {/* CBR history chart */}
      <section className="cbr-history-chart">
        <h2>Babbling History</h2>
        {cbrHistory.length === 0 ? (
          <p className="progress-empty">Record more sessions to see your child's journey.</p>
        ) : (
          <div className="cbr-history-rows">
            {cbrHistory.map((row, i) => (
              <div key={i} className="cbr-history-row">
                <span className="cbr-history-label">{formatDate(row.date)}</span>
                <div className="cbr-history-bar-wrap">
                  <div
                    className="cbr-history-bar-fill"
                    style={{ width: `${Math.min(100, (row.cbr || 0) * 100)}%` }}
                  />
                </div>
                <span className="cbr-history-pct">{((row.cbr || 0) * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Milestone log */}
      <section className="milestone-log-section">
        <h2>Milestones</h2>
        {milestones.length === 0 ? (
          <p className="progress-empty">No milestones yet. Keep recording!</p>
        ) : (
          <div className="milestone-log">
            {milestones.map(m => (
              <div key={m.milestone_id} className="milestone-log-item">
                <span className="milestone-log-name">{MILESTONE_LABELS[m.milestone_type] || m.milestone_type}</span>
                <span className="milestone-log-date">{formatDate(m.first_date)}</span>
                {m.description && <p className="milestone-log-desc">{m.description}</p>}
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

export default ProgressPage;
