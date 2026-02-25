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

function MiniBar({ value, max, color = 'var(--primary)' }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : Math.min(100, value * 100);
  return (
    <div className="mini-history-bar-wrap">
      <div className="mini-history-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function ProgressPage() {
  const { childId } = useParams();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [milestones, setMilestones] = useState([]);
  const [childName, setChildName] = useState('');
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

  // Resolve child name from localStorage
  useEffect(() => {
    try {
      const cached = JSON.parse(localStorage.getItem('qleam_children') || '[]');
      const child = cached.find(c => c.child_id === childId);
      if (child?.name) setChildName(child.name);
    } catch (_) {}
  }, [childId]);

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
        <p>Loading progress…</p>
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

  // Last session's developmental snapshot
  const lastDev = sessions[0]?.developmental_view;

  // Trend data from last 12 sessions (most recent first from API)
  const trendSessions = sessions.slice(0, 12).reverse(); // oldest→newest for chart

  const cbrHistory = trendSessions
    .map(s => ({ date: s.timestamp, cbr: s.developmental_view?.cbr ?? null, stage: s.developmental_view?.current_stage }))
    .filter(s => s.cbr !== null);

  const vtlHistory = trendSessions
    .map(s => ({ date: s.timestamp, vtl: s.biological?.vtl_cm ?? null }))
    .filter(s => s.vtl !== null && s.vtl > 0);

  const phiHistory = trendSessions
    .map(s => ({ date: s.timestamp, phi: s.developmental_view?.phi ?? null }))
    .filter(s => s.phi !== null);

  // Interleaved timeline: sessions + milestones by date
  const timelineEvents = [
    ...sessions.map(s => ({
      type: 'session',
      date: s.timestamp,
      label: s.insight_summary?.probable_intent?.label || 'Session',
      confidence: s.insight_summary?.probable_intent?.confidence,
      stage: s.developmental_view?.current_stage,
      session_id: s.session_id,
    })),
    ...milestones.map(m => ({
      type: 'milestone',
      date: m.first_date,
      label: MILESTONE_LABELS[m.milestone_type] || m.milestone_type,
      milestone_type: m.milestone_type,
    })),
  ].sort((a, b) => new Date(b.date) - new Date(a.date));

  const titleName = childName ? `${childName}'s` : 'Journey';

  return (
    <div className="progress-page">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>
      <h1>{childName ? `${childName}'s Journey` : 'Journey Progress'}</h1>

      {/* Current snapshot */}
      {lastDev ? (
        <section className="progress-snapshot">
          <h2>Current Snapshot</h2>
          <div className="progress-snapshot-row">
            <span className="stage-badge">{STAGE_LABELS[lastDev.current_stage] || lastDev.current_stage}</span>
            <span className="phi-indicator">{lastDev.phi_label}</span>
          </div>
          <div className="progress-snapshot-row">
            <span className="cbr-snapshot-label">Canonical Babbling</span>
            <div className="cbr-bar-wrap" style={{ flex: 1 }}>
              <div className="cbr-bar">
                <div className="cbr-bar-fill" style={{ width: `${Math.min(100, (lastDev.cbr || 0) * 100)}%` }} />
              </div>
            </div>
            <span className="cbr-snapshot-pct">{((lastDev.cbr || 0) * 100).toFixed(0)}%</span>
          </div>
        </section>
      ) : (
        <section className="progress-snapshot">
          <p className="progress-empty">Record more sessions to see {titleName.toLowerCase()} developmental snapshot.</p>
        </section>
      )}

      {/* CBR trend */}
      {cbrHistory.length > 0 && (
        <section className="trend-chart-section">
          <h2>Babbling Quality</h2>
          <p className="language-section-hint">Canonical Babbling Ratio — how often vocalisations have adult-like consonant-vowel structure</p>
          <div className="trend-rows">
            {cbrHistory.map((row, i) => (
              <div key={i} className="trend-row">
                <span className="trend-label">{formatDate(row.date)}</span>
                <MiniBar value={row.cbr} max={1} />
                <span className="trend-value">{((row.cbr || 0) * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* VTL growth */}
      {vtlHistory.length >= 2 && (
        <section className="trend-chart-section">
          <h2>Vocal Tract Growth</h2>
          <p className="language-section-hint">Estimated vocal tract length (cm) — reflects physical development over time</p>
          <div className="trend-rows">
            {vtlHistory.map((row, i) => (
              <div key={i} className="trend-row">
                <span className="trend-label">{formatDate(row.date)}</span>
                <MiniBar value={row.vtl} max={20} color="#a29bfe" />
                <span className="trend-value">{row.vtl.toFixed(1)} cm</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* φ order parameter trend */}
      {phiHistory.length >= 2 && (
        <section className="trend-chart-section">
          <h2>Language Readiness (φ)</h2>
          <p className="language-section-hint">φ order parameter — composite measure of language emergence (0 = pre-linguistic → 1 = linguistic)</p>
          <div className="trend-rows">
            {phiHistory.map((row, i) => (
              <div key={i} className="trend-row">
                <span className="trend-label">{formatDate(row.date)}</span>
                <MiniBar value={row.phi} max={1} color="#fdcb6e" />
                <span className="trend-value">{row.phi.toFixed(2)}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Interleaved timeline */}
      <section className="timeline-section">
        <h2>Full Timeline</h2>
        {timelineEvents.length === 0 ? (
          <p className="progress-empty">No sessions or milestones recorded yet.</p>
        ) : (
          <div className="timeline">
            {timelineEvents.map((ev, i) => (
              <div
                key={i}
                className={`timeline-event timeline-event--${ev.type}`}
                onClick={ev.type === 'session' ? () => navigate(`/session/${ev.session_id}`) : undefined}
                style={{ cursor: ev.type === 'session' ? 'pointer' : 'default' }}
              >
                <div className="timeline-dot" />
                <div className="timeline-body">
                  <span className="timeline-label">
                    {ev.type === 'milestone' && <span className="timeline-milestone-star">✦ </span>}
                    {ev.label}
                  </span>
                  <div className="timeline-meta">
                    <span className="timeline-date">{formatDate(ev.date)}</span>
                    {ev.stage && (
                      <span className="timeline-stage">{STAGE_LABELS[ev.stage] || ev.stage}</span>
                    )}
                    {ev.confidence != null && (
                      <span className="timeline-conf">{Math.round(ev.confidence * 100)}% confidence</span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Milestone log */}
      {milestones.length > 0 && (
        <section className="milestone-log-section">
          <h2>Milestones</h2>
          <div className="milestone-log">
            {milestones.map(m => (
              <div key={m.milestone_id} className="milestone-log-item">
                <span className="milestone-log-name">{MILESTONE_LABELS[m.milestone_type] || m.milestone_type}</span>
                <span className="milestone-log-date">{formatDate(m.first_date)}</span>
                {m.description && <p className="milestone-log-desc">{m.description}</p>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default ProgressPage;
