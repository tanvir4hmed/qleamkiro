import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import SessionCard from '../components/SessionCard';
import RecordButton from '../components/RecordButton';
import InsightPanel from '../components/InsightPanel';

// ─── Settings Panel ──────────────────────────────────────────────────────────

function SettingsPanel({ children, onClose, onAddChild, onDeleteChild }) {
  const [addName, setAddName] = useState('');
  const [addDob, setAddDob] = useState('');
  const [deleteChildId, setDeleteChildId] = useState('');
  const [confirmDob, setConfirmDob] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [addError, setAddError] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const overlayRef = useRef(null);

  const handleAdd = async () => {
    if (!addName.trim() || !addDob) { setAddError('Name and date of birth are required.'); return; }
    setAdding(true);
    setAddError('');
    try {
      await onAddChild(addName.trim(), addDob);
      setAddName(''); setAddDob('');
    } catch (e) { setAddError(e.message || 'Failed to add child.'); }
    finally { setAdding(false); }
  };

  const selectedChild = children.find(c => c.child_id === deleteChildId);

  const handleDelete = async () => {
    setDeleteError('');
    if (!selectedChild) { setDeleteError('Select a child first.'); return; }
    if (confirmDob !== selectedChild.birth_date) {
      setDeleteError("Date of birth doesn't match. Please try again.");
      return;
    }
    setDeleting(true);
    try {
      await onDeleteChild(selectedChild.child_id);
      setDeleteChildId(''); setConfirmDob('');
    } catch (e) { setDeleteError(e.message || 'Failed to remove child.'); }
    finally { setDeleting(false); }
  };

  return (
    <div className="settings-overlay" onClick={e => { if (e.target === overlayRef.current) onClose(); }} ref={overlayRef}>
      <div className="settings-panel" role="dialog" aria-label="Settings">
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Add a child */}
        <div className="settings-section">
          <h3>Add a child</h3>
          <div className="settings-form">
            <input
              type="text"
              placeholder="Child's name"
              value={addName}
              onChange={e => setAddName(e.target.value)}
              className="settings-input"
            />
            <label className="settings-dob-label">
              Date of birth <span className="birth-date-required">*</span>
              <input
                type="date"
                value={addDob}
                onChange={e => setAddDob(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
                className="settings-input"
              />
            </label>
            {addError && <p className="settings-error">{addError}</p>}
            <button
              className="settings-action-btn settings-action-btn--primary"
              onClick={handleAdd}
              disabled={adding || !addName.trim() || !addDob}
            >
              {adding ? 'Adding…' : 'Add child'}
            </button>
          </div>
        </div>

        {/* Remove a child */}
        {children.length > 0 && (
          <div className="settings-section">
            <h3>Remove a child</h3>
            <p className="settings-hint">Enter the child's date of birth to confirm. This removes all their data permanently.</p>
            <div className="settings-form">
              <select
                className="settings-input settings-select"
                value={deleteChildId}
                onChange={e => { setDeleteChildId(e.target.value); setConfirmDob(''); setDeleteError(''); }}
              >
                <option value="">— Select child —</option>
                {children.map(c => (
                  <option key={c.child_id} value={c.child_id}>{c.name}</option>
                ))}
              </select>
              {deleteChildId && (
                <>
                  <label className="settings-dob-label">
                    Confirm {selectedChild?.name}'s date of birth
                    <input
                      type="date"
                      value={confirmDob}
                      onChange={e => { setConfirmDob(e.target.value); setDeleteError(''); }}
                      max={new Date().toISOString().split('T')[0]}
                      className="settings-input"
                    />
                  </label>
                  {deleteError && <p className="settings-error">{deleteError}</p>}
                  <button
                    className="settings-action-btn settings-action-btn--danger"
                    onClick={handleDelete}
                    disabled={deleting || !confirmDob}
                  >
                    {deleting ? 'Removing…' : `Remove ${selectedChild?.name}`}
                  </button>
                </>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

function Dashboard() {
  const navigate = useNavigate();
  const [children, setChildren] = useState([]);
  const [selectedChild, setSelectedChild] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [latestInsight, setLatestInsight] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  // Show add-first-child form only when there are no children yet
  const [showAddFirst, setShowAddFirst] = useState(false);
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

  // Load children from API; show cached data immediately while fetching
  useEffect(() => {
    const cached = localStorage.getItem('qleam_children');
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        setChildren(parsed);
        if (parsed.length > 0 && !selectedChild) setSelectedChild(parsed[0]);
      } catch (_) {}
    }

    apiCall('/child')
      .then(data => {
        const fetched = data.children || [];
        setChildren(fetched);
        localStorage.setItem('qleam_children', JSON.stringify(fetched));
        setSelectedChild(prev => {
          // Keep existing selection if still valid; otherwise use first child
          if (prev && fetched.some(c => c.child_id === prev.child_id)) return prev;
          return fetched.length > 0 ? fetched[0] : null;
        });
      })
      .catch(err => setError(err.message));
  }, [apiCall]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load sessions when child selected — clear stale data immediately
  useEffect(() => {
    if (!selectedChild) return;
    setLoading(true);
    setSessions([]);
    setLatestInsight(null); // fix: clear previous child's insight (#12, #20)
    apiCall(`/child/${selectedChild.child_id}/sessions`)
      .then(data => {
        const s = data.sessions || [];
        setSessions(s);
        const latest = s.find(sess => sess.insight_summary);
        if (latest) setLatestInsight(latest.insight_summary);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [selectedChild, apiCall]);

  const addChild = useCallback(async (name, birthDate) => {
    const data = await apiCall('/child', {
      method: 'POST',
      body: JSON.stringify({ name, birth_date: birthDate }),
    });
    const newChild = { child_id: data.child_id, name, birth_date: birthDate };
    setChildren(prev => {
      const updated = [...prev, newChild];
      localStorage.setItem('qleam_children', JSON.stringify(updated));
      return updated;
    });
    setSelectedChild(newChild);
    return newChild;
  }, [apiCall]);

  const handleAddFirstChild = async () => {
    if (!newChildName.trim() || !newChildBirthDate) return;
    try {
      await addChild(newChildName.trim(), newChildBirthDate);
      setNewChildName(''); setNewChildBirthDate(''); setShowAddFirst(false);
    } catch (err) { setError(err.message); }
  };

  const handleDeleteChild = useCallback(async (childId) => {
    await apiCall(`/child/${childId}`, { method: 'DELETE' });
    setChildren(prev => {
      const updated = prev.filter(c => c.child_id !== childId);
      localStorage.setItem('qleam_children', JSON.stringify(updated));
      return updated;
    });
    setSelectedChild(prev => {
      if (prev?.child_id !== childId) return prev;
      const remaining = children.filter(c => c.child_id !== childId);
      return remaining.length > 0 ? remaining[0] : null;
    });
  }, [apiCall, children]);

  const handleSessionComplete = () => {
    if (selectedChild) {
      apiCall(`/child/${selectedChild.child_id}/sessions`)
        .then(data => setSessions(data.sessions || []))
        .catch(console.error);
    }
  };

  return (
    <div className="dashboard">
      {/* ── Child Selector ── */}
      <section className="child-section">
        <div className="child-section-header">
          <div className="child-selector">
            {children.map(child => (
              <button
                key={child.child_id}
                className={`child-btn${selectedChild?.child_id === child.child_id ? ' active' : ''}`}
                onClick={() => setSelectedChild(child)}
              >
                {child.name}
              </button>
            ))}
            {children.length === 0 && (
              <button className="child-btn add-btn" onClick={() => setShowAddFirst(true)}>
                + Add your first child
              </button>
            )}
          </div>
          <button
            className="settings-icon-btn"
            onClick={() => setShowSettings(true)}
            title="Settings"
            aria-label="Open settings"
          >
            ⚙
          </button>
        </div>

        {/* First-child inline add form (shown only when no children exist) */}
        {children.length === 0 && showAddFirst && (
          <div className="add-child-form">
            <input
              type="text"
              placeholder="Child's name (required)"
              value={newChildName}
              onChange={e => setNewChildName(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddFirstChild()}
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
            <button onClick={handleAddFirstChild} disabled={!newChildName.trim() || !newChildBirthDate}>Add</button>
            <button onClick={() => { setShowAddFirst(false); setNewChildBirthDate(''); }}>Cancel</button>
          </div>
        )}

        {/* Child-specific navigation — Journey & Language */}
        {selectedChild && (
          <div className="child-nav-bar">
            <button
              className="child-nav-btn"
              onClick={() => navigate(`/progress/${selectedChild.child_id}`)}
            >
              Journey ↗
            </button>
            <button
              className="child-nav-btn child-nav-btn--language"
              onClick={() => navigate(`/language/${selectedChild.child_id}`)}
            >
              Language ↗
            </button>
          </div>
        )}
      </section>

      {/* ── Settings Panel (modal overlay) ── */}
      {showSettings && (
        <SettingsPanel
          children={children}
          onClose={() => setShowSettings(false)}
          onAddChild={addChild}
          onDeleteChild={handleDeleteChild}
        />
      )}

      {selectedChild ? (
        <>
          {/* Record Section */}
          <section className="record-section">
            <h2>Record a Session</h2>
            <p className="section-subtitle">
              Hold the phone near your baby and record at least 5 seconds of their sounds
            </p>
            <RecordButton
              childId={selectedChild.child_id}
              apiCall={apiCall}
              onComplete={handleSessionComplete}
            />
          </section>

          {/* Latest Insight — only shown when there IS a session */}
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
              <div className="loading">Loading sessions…</div>
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