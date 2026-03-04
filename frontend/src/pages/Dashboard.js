import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchAuthSession } from 'aws-amplify/auth';
import { API_BASE_URL } from '../aws-config';
import SessionCard from '../components/SessionCard';
import RecordButton from '../components/RecordButton';
import InsightPanel from '../components/InsightPanel';

const SELECTED_CHILD_KEY = 'qleam_selected_child_id';
// const MAX_SUPPORTED_CHILD_AGE_DAYS = 730;
const MAX_SUPPORTED_CHILD_AGE_DAYS = 90;

function getBirthDateBounds() {
  const today = new Date();
  const max = today.toISOString().split('T')[0];
  const minDate = new Date(today);
  minDate.setDate(minDate.getDate() - MAX_SUPPORTED_CHILD_AGE_DAYS);
  const min = minDate.toISOString().split('T')[0];
  return { min, max };
}

function isBirthDateInSupportedRange(dateString) {
  if (!dateString) return false;
  const parsed = new Date(`${dateString}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return false;

  const now = new Date();
  const todayUtcMs = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const birthUtcMs = Date.UTC(parsed.getUTCFullYear(), parsed.getUTCMonth(), parsed.getUTCDate());
  const ageDays = Math.floor((todayUtcMs - birthUtcMs) / 86400000);

  return ageDays >= 0 && ageDays <= MAX_SUPPORTED_CHILD_AGE_DAYS;
}

// ─── Settings Panel ──────────────────────────────────────────────────────────

function SettingsPanel({ children, onClose, onAddChild, onDeleteChild, onSuccess }) {
  const [panel, setPanel] = useState(null); // null | 'add' | 'remove'
  const [addName, setAddName] = useState('');
  const [addDob, setAddDob] = useState('');
  const [deleteChildId, setDeleteChildId] = useState('');
  const [confirmName, setConfirmName] = useState('');
  const [deleteError, setDeleteError] = useState('');
  const [addError, setAddError] = useState('');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const overlayRef = useRef(null);
  const { min: minBirthDate, max: maxBirthDate } = getBirthDateBounds();

  const handleAdd = async () => {
    if (!addName.trim() || !addDob) { setAddError('Name and date of birth are required.'); return; }
    if (!isBirthDateInSupportedRange(addDob)) {
      // setAddError('Only children aged 0-24 months are supported.');
      setAddError('Only babies aged 0-3 months are supported.');
      return;
    }
    setAdding(true);
    setAddError('');
    try {
      const child = await onAddChild(addName.trim(), addDob);
      setAddName(''); setAddDob(''); setPanel(null);
      onSuccess?.(`${child?.name || addName.trim()} added`);
    } catch (e) { setAddError(e.message || 'Failed to add child.'); }
    finally { setAdding(false); }
  };

  const selectedDeleteChild = children.find(c => c.child_id === deleteChildId);

  const handleDelete = async () => {
    setDeleteError('');
    if (!selectedDeleteChild) { setDeleteError('Select a child first.'); return; }
    if (confirmName.trim().toLowerCase() !== selectedDeleteChild.name.trim().toLowerCase()) {
      setDeleteError("Name doesn't match. Please type the child's name exactly.");
      return;
    }
    setDeleting(true);
    const removedName = selectedDeleteChild.name;
    try {
      await onDeleteChild(selectedDeleteChild.child_id);
      setDeleteChildId(''); setConfirmName(''); setPanel(null);
      onSuccess?.(`${removedName} removed`);
    } catch (e) { setDeleteError(e.message || 'Failed to remove child.'); }
    finally { setDeleting(false); }
  };

  const switchPanel = (p) => {
    setPanel(prev => (prev === p ? null : p));
    setAddError(''); setDeleteError('');
  };

  return (
    <div className="settings-overlay" onClick={e => { if (e.target === overlayRef.current) onClose(); }} ref={overlayRef}>
      <div className="settings-panel" role="dialog" aria-label="Settings">
        <div className="settings-header">
          <h2>Settings</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="Close">✕</button>
        </div>

        {/* Toggle buttons — forms revealed on click */}
        <div className="settings-toggle-row">
          <button
            className={`settings-toggle-btn${panel === 'add' ? ' active' : ''}`}
            onClick={() => switchPanel('add')}
          >
            + Add a child
          </button>
          {children.length > 0 && (
            <button
              className={`settings-toggle-btn settings-toggle-btn--danger${panel === 'remove' ? ' active' : ''}`}
              onClick={() => switchPanel('remove')}
            >
              − Remove a child
            </button>
          )}
        </div>

        {/* Add child form */}
        {panel === 'add' && (
          <div className="settings-section">
            <div className="settings-form">
              <input
                type="text"
                placeholder="Child's name"
                value={addName}
                onChange={e => setAddName(e.target.value)}
                className="settings-input"
                autoFocus
              />
              <label className="settings-dob-label">
                Date of birth <span className="birth-date-required">*</span>
                <input
                  type="date"
                  value={addDob}
                  onChange={e => setAddDob(e.target.value)}
                  min={minBirthDate}
                  max={maxBirthDate}
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
        )}

        {/* Remove child form */}
        {panel === 'remove' && children.length > 0 && (
          <div className="settings-section">
            <p className="settings-hint">
              Type the child's name to confirm. Their session history and personal data will be removed.
              Anonymised patterns used for population research are kept — they contain no identifying information.
            </p>
            <div className="settings-form">
              <select
                className="settings-input settings-select"
                value={deleteChildId}
                onChange={e => { setDeleteChildId(e.target.value); setConfirmName(''); setDeleteError(''); }}
              >
                <option value="">— Select child —</option>
                {children.map(c => (
                  <option key={c.child_id} value={c.child_id}>{c.name}</option>
                ))}
              </select>
              {deleteChildId && (
                <>
                  <label className="settings-dob-label">
                    Type <strong>{selectedDeleteChild?.name}</strong>'s name to confirm
                    <input
                      type="text"
                      placeholder={selectedDeleteChild?.name}
                      value={confirmName}
                      onChange={e => { setConfirmName(e.target.value); setDeleteError(''); }}
                      className="settings-input"
                      autoFocus
                    />
                  </label>
                  {deleteError && <p className="settings-error">{deleteError}</p>}
                  <button
                    className="settings-action-btn settings-action-btn--danger"
                    onClick={handleDelete}
                    disabled={deleting || !confirmName}
                  >
                    {deleting ? 'Removing…' : `Remove ${selectedDeleteChild?.name}`}
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
  const [showAddFirst, setShowAddFirst] = useState(false);
  const [newChildName, setNewChildName] = useState('');
  const [newChildBirthDate, setNewChildBirthDate] = useState('');
  const [notification, setNotification] = useState(null);
  const notificationTimerRef = useRef(null);
  const { min: minBirthDate, max: maxBirthDate } = getBirthDateBounds();

  const showNotification = useCallback((msg) => {
    setNotification(msg);
    clearTimeout(notificationTimerRef.current);
    notificationTimerRef.current = setTimeout(() => setNotification(null), 3000);
  }, []);

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

  // Persist selected child ID across navigation and remounts
  const selectChild = useCallback((child) => {
    setSelectedChild(child);
    if (child?.child_id) localStorage.setItem(SELECTED_CHILD_KEY, child.child_id);
    else localStorage.removeItem(SELECTED_CHILD_KEY);
  }, []);

  // Load children — restore saved selection from localStorage
  useEffect(() => {
    const cached = localStorage.getItem('qleam_children');
    const savedId = localStorage.getItem(SELECTED_CHILD_KEY);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        setChildren(parsed);
        if (parsed.length > 0) {
          const toRestore = savedId
            ? (parsed.find(c => c.child_id === savedId) || parsed[0])
            : parsed[0];
          setSelectedChild(toRestore);
        }
      } catch (_) {}
    }

    apiCall('/child')
      .then(data => {
        const fetched = data.children || [];
        setChildren(fetched);
        localStorage.setItem('qleam_children', JSON.stringify(fetched));
        const savedChildId = localStorage.getItem(SELECTED_CHILD_KEY);
        setSelectedChild(prev => {
          const target = savedChildId ? fetched.find(c => c.child_id === savedChildId) : null;
          if (target) return target;
          if (prev && fetched.some(c => c.child_id === prev.child_id)) return prev;
          return fetched.length > 0 ? fetched[0] : null;
        });
      })
      .catch(err => setError(err.message));
  }, [apiCall]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load sessions — cancel stale requests to prevent wrong child's insight bleeding through
  useEffect(() => {
    if (!selectedChild) return;
    let cancelled = false;
    setLoading(true);
    setSessions([]);
    setLatestInsight(null);

    apiCall(`/child/${selectedChild.child_id}/sessions`)
      .then(data => {
        if (cancelled) return;
        const s = data.sessions || [];
        setSessions(s);
        const latest = s.find(sess => sess.insight_summary);
        if (latest) setLatestInsight(latest.insight_summary);
      })
      .catch(err => { if (!cancelled) setError(err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [selectedChild, apiCall]);

  const addChild = useCallback(async (name, birthDate) => {
    if (!isBirthDateInSupportedRange(birthDate)) {
      // throw new Error('Only children aged 0-24 months are supported.');
      throw new Error('Only babies aged 0-3 months are supported.');
    }
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
    selectChild(newChild);
    return newChild;
  }, [apiCall, selectChild]);

  const handleAddFirstChild = async () => {
    if (!newChildName.trim() || !newChildBirthDate) return;
    if (!isBirthDateInSupportedRange(newChildBirthDate)) {
      // setError('Only children aged 0-24 months are supported.');
      setError('Only babies aged 0-3 months are supported.');
      return;
    }
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
      const next = remaining.length > 0 ? remaining[0] : null;
      if (next) localStorage.setItem(SELECTED_CHILD_KEY, next.child_id);
      else localStorage.removeItem(SELECTED_CHILD_KEY);
      return next;
    });
  }, [apiCall, children]);

  const handleSessionComplete = (newSessionId) => {
    if (newSessionId) {
      navigate(`/session/${newSessionId}`);
    } else if (selectedChild) {
      apiCall(`/child/${selectedChild.child_id}/sessions`)
        .then(data => setSessions(data.sessions || []))
        .catch(console.error);
    }
  };

  return (
    <div className="dashboard">
      {/* ── Success toast ── */}
      {notification && (
        <div className="dashboard-toast">{notification}</div>
      )}

      {/* ── Child Selector ── */}
      <section className="child-section">
        <div className="child-section-header">
          <div className="child-selector">
            {children.map(child => (
              <button
                key={child.child_id}
                className={`child-btn${selectedChild?.child_id === child.child_id ? ' active' : ''}`}
                onClick={() => selectChild(child)}
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

        {/* First-child inline add form */}
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
                min={minBirthDate}
                max={maxBirthDate}
              />
            </label>
            <button onClick={handleAddFirstChild} disabled={!newChildName.trim() || !newChildBirthDate}>Add</button>
            <button onClick={() => { setShowAddFirst(false); setNewChildBirthDate(''); }}>Cancel</button>
          </div>
        )}

      </section>

      {/* ── Settings Panel ── */}
      {showSettings && (
        <SettingsPanel
          children={children}
          onClose={() => setShowSettings(false)}
          onAddChild={addChild}
          onDeleteChild={handleDeleteChild}
          onSuccess={(msg) => { showNotification(msg); setShowSettings(false); }}
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
              childBirthDate={selectedChild.birth_date}
              apiCall={apiCall}
              onComplete={handleSessionComplete}
            />
          </section>

          {/* Latest Insight — only shown when there IS a real insight */}
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
