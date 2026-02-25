import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import SessionCard from '../components/SessionCard';
import RecordButton from '../components/RecordButton';
import InsightPanel from '../components/InsightPanel';

function Dashboard({ user }) {
  const navigate = useNavigate();
  const [children, setChildren] = useState([]);
  const [selectedChild, setSelectedChild] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [latestInsight, setLatestInsight] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showAddChild, setShowAddChild] = useState(false);
  const [newChildName, setNewChildName] = useState('');
  const [newChildBirthDate, setNewChildBirthDate] = useState('');

  const getAuthHeaders = async () => {
    const session = await fetchAuthSession();
    const token = session.tokens?.idToken?.toString();
    return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
  };

  const apiCall = useCallback(async (path, options = {}) => {
    const headers = await getAuthHeaders();
    const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers: { ...headers, ...options.headers } });
    if (!res.ok) throw new Error(`API error ${res.status}: ${await res.text()}`);
    return res.json();
  }, []);

  // Load children from API (server is source of truth, localStorage is fast-load cache)
  useEffect(() => {
    // Show cached data immediately while fetching
    const cached = localStorage.getItem('qleam_children');
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        setChildren(parsed);
        if (parsed.length > 0) setSelectedChild(parsed[0]);
      } catch (_) {}
    }

    // Always fetch fresh from server
    apiCall('/child')
      .then(data => {
        const fetched = data.children || [];
        setChildren(fetched);
        localStorage.setItem('qleam_children', JSON.stringify(fetched));
        if (fetched.length > 0) setSelectedChild(prev => prev || fetched[0]);
      })
      .catch(err => setError(err.message));
  }, [apiCall]);

  // Load sessions when child selected
  useEffect(() => {
    if (!selectedChild) return;
    setLoading(true);
    apiCall(`/child/${selectedChild.child_id}/sessions`)
      .then(data => {
        setSessions(data.sessions || []);
        const latest = (data.sessions || []).find(s => s.insight_summary);
        if (latest) setLatestInsight(latest.insight_summary);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [selectedChild, apiCall]);

  const handleAddChild = async () => {
    if (!newChildName.trim()) return;
    try {
      const data = await apiCall('/child', {
        method: 'POST',
        body: JSON.stringify({
          name: newChildName.trim(),
          birth_date: newChildBirthDate || '',
        }),
      });
      const newChild = {
        child_id: data.child_id,
        name: newChildName.trim(),
        birth_date: newChildBirthDate || '',
      };
      const updated = [...children, newChild];
      setChildren(updated);
      localStorage.setItem('qleam_children', JSON.stringify(updated));
      setSelectedChild(newChild);
      setNewChildName('');
      setNewChildBirthDate('');
      setShowAddChild(false);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSessionComplete = (sessionId) => {
    // Refresh sessions after upload
    if (selectedChild) {
      apiCall(`/child/${selectedChild.child_id}/sessions`)
        .then(data => setSessions(data.sessions || []))
        .catch(console.error);
    }
  };

  return (
    <div className="dashboard">
      {/* Child Selector */}
      <section className="child-section">
        <div className="child-selector">
          {children.map(child => (
            <button
              key={child.child_id}
              className={`child-btn ${selectedChild?.child_id === child.child_id ? 'active' : ''}`}
              onClick={() => setSelectedChild(child)}
            >
              {child.name}
            </button>
          ))}
          <button className="child-btn add-btn" onClick={() => setShowAddChild(true)}>
            + Add Child
          </button>
          {selectedChild && (
            <button
              className="child-btn journey-btn"
              onClick={() => navigate(`/progress/${selectedChild.child_id}`)}
            >
              Journey
            </button>
          )}
          {selectedChild && (
            <button
              className="child-btn language-btn"
              onClick={() => navigate(`/language/${selectedChild.child_id}`)}
            >
              Language
            </button>
          )}
        </div>

        {showAddChild && (
          <div className="add-child-form">
            <input
              type="text"
              placeholder="Child's name (required)"
              value={newChildName}
              onChange={e => setNewChildName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddChild()}
              autoFocus
            />
            <label className="birth-date-label">
              Date of birth <span className="birth-date-required">*</span>
              <input
                type="date"
                value={newChildBirthDate}
                onChange={e => setNewChildBirthDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
            </label>
            <button onClick={handleAddChild} disabled={!newChildName.trim() || !newChildBirthDate}>Add</button>
            <button onClick={() => { setShowAddChild(false); setNewChildBirthDate(''); }}>Cancel</button>
          </div>
        )}
      </section>

      {selectedChild ? (
        <>
          {/* Record Section */}
          <section className="record-section">
            <h2>Record a Session</h2>
            <p className="section-subtitle">
              Record 5–30 seconds of your baby's vocalizations
            </p>
            <RecordButton
              childId={selectedChild.child_id}
              apiCall={apiCall}
              onComplete={handleSessionComplete}
            />
          </section>

          {/* Latest Insight */}
          {latestInsight && (
            <section className="insight-section">
              <h2>Latest Insight</h2>
              <InsightPanel insight={latestInsight} />
            </section>
          )}

          {/* Session History */}
          <section className="sessions-section">
            <h2>Session History</h2>
            {error && <div className="error-banner">{error}</div>}
            {loading ? (
              <div className="loading">Loading sessions...</div>
            ) : sessions.length === 0 ? (
              <div className="empty-state">
                <p>No sessions yet. Record your first session above!</p>
              </div>
            ) : (
              <div className="sessions-grid">
                {sessions.map(session => (
                  <SessionCard
                    key={session.session_id}
                    session={session}
                    onClick={() => navigate(`/session/${session.session_id}`)}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      ) : (
        <div className="empty-state">
          <h2>Welcome to Qleam</h2>
          <p>Add your child's profile to get started.</p>
        </div>
      )}
    </div>
  );
}

export default Dashboard;
