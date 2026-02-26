import React, { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';

const STATUS_META = {
  CRYSTALLIZED: {
    label: 'Confirmed signal',
    badge: 'signal-confirmed',
    icon: '✦',
    description: 'Qleam has consistently recognised this sound pattern.',
  },
  CANDIDATE: {
    label: 'Emerging pattern',
    badge: 'signal-candidate',
    icon: '◎',
    description: 'This sound is appearing regularly — it may become a personal word.',
  },
  NONE: {
    label: 'Heard sound',
    badge: 'signal-heard',
    icon: '○',
    description: null,
  },
};

function strengthLabel(weight) {
  if (weight >= 0.75) return 'Strong';
  if (weight >= 0.50) return 'Moderate';
  return 'Emerging';
}

function SignalCard({ signal }) {
  const meta = STATUS_META[signal.proto_word_status] || STATUS_META.NONE;
  const strength = strengthLabel(signal.reinforcement_weight);
  return (
    <div className={`signal-card signal-card--${signal.proto_word_status?.toLowerCase() || 'none'}`}>
      <div className="signal-card-header">
        <span className="signal-icon">{meta.icon}</span>
        <span className="signal-label">
          {signal.label !== 'Unnamed sound' ? `"${signal.label}"` : 'Unnamed sound'}
        </span>
        <span className={`signal-badge ${meta.badge}`}>{meta.label}</span>
      </div>
      <div className="signal-card-meta">
        <span className="signal-meta-item">Heard {signal.frequency_count}×</span>
        <span className="signal-meta-sep">·</span>
        <span className="signal-meta-item">{strength} pattern</span>
      </div>
      {meta.description && (
        <p className="signal-description">{meta.description}</p>
      )}
    </div>
  );
}

function LanguagePage() {
  const { childId } = useParams();
  const navigate = useNavigate();
  const [signals, setSignals] = useState([]);
  const [concepts, setConcepts] = useState([]);
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
        const [signalsData, conceptsData] = await Promise.all([
          apiCall(`/child/${childId}/language-signals`),
          apiCall(`/child/${childId}/concepts`),
        ]);
        setSignals(signalsData.signals || []);
        setConcepts(conceptsData.concepts || []);
      } catch (err) {
        setError('Could not load language data. Please go back and try again.');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [childId, apiCall]);

  if (loading) {
    return (
      <div className="language-page loading-state">
        <div className="spinner" />
        <p>Loading language profile…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="language-page error-state">
        <p className="error-msg">{error}</p>
        <button onClick={() => navigate('/')}>Back to Dashboard</button>
      </div>
    );
  }

  const confirmed = signals.filter(s => s.proto_word_status === 'CRYSTALLIZED');
  const emerging = signals.filter(s => s.proto_word_status === 'CANDIDATE');
  const heardSounds = signals.filter(s => s.proto_word_status === 'NONE' && s.frequency_count >= 3);

  const confirmedConcepts = concepts.filter(c => (c.confirmation_count || 0) >= 2);

  const titleName = childName ? `${childName}'s` : 'Your baby\'s';

  return (
    <div className="language-page">
      <button className="back-btn" onClick={() => navigate('/')}>← Back</button>
      <h1>{titleName} Language</h1>
      <p className="language-page-subtitle">
        Personal sounds and patterns Qleam has learned over time
      </p>

      {/* Confirmed signals */}
      <section className="language-section">
        <h2>Confirmed Signals</h2>
        {confirmed.length === 0 ? (
          <p className="progress-empty">
            Keep recording sessions — confirmed signals appear once a sound pattern is reliably recognised.
          </p>
        ) : (
          <div className="signal-list">
            {confirmed.map(s => <SignalCard key={s.cluster_id} signal={s} />)}
          </div>
        )}
      </section>

      {/* Emerging patterns */}
      {emerging.length > 0 && (
        <section className="language-section">
          <h2>Emerging Patterns</h2>
          <p className="language-section-hint">
            These sounds are appearing regularly. Once they're consistently linked to a meaning, they become confirmed signals.
          </p>
          <div className="signal-list">
            {emerging.map(s => <SignalCard key={s.cluster_id} signal={s} />)}
          </div>
        </section>
      )}

      {/* Concept vocabulary — only shown when concepts exist */}
      {confirmedConcepts.length > 0 && (
        <section className="language-section">
          <h2>Personal Vocabulary</h2>
          <p className="language-section-hint">
            Words and ideas {childName || 'your baby'} has shown interest in or been heard referencing.
          </p>
          <div className="vocab-chips">
            {confirmedConcepts.map(c => (
              <span key={c.concept_id || c.label} className="vocab-chip">
                {c.label}
                {c.confirmation_count >= 3 && <span className="vocab-chip-star">✦</span>}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* Heard sounds — lower-confidence, frequency ≥ 3 */}
      {heardSounds.length > 0 && (
        <section className="language-section">
          <h2>Frequently Heard Sounds</h2>
          <p className="language-section-hint">
            These sounds have been heard at least 3 times but haven't developed a clear pattern yet.
          </p>
          <div className="signal-list signal-list--muted">
            {heardSounds.slice(0, 8).map(s => <SignalCard key={s.cluster_id} signal={s} />)}
          </div>
        </section>
      )}

      {signals.length === 0 && concepts.length === 0 && (
        <section className="language-section">
          <p className="progress-empty">
            No sounds have been learned yet. Keep recording sessions — Qleam will start building {titleName.toLowerCase()} personal language profile automatically.
          </p>
        </section>
      )}
    </div>
  );
}

export default LanguagePage;
