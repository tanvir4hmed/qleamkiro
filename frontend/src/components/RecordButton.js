import { useState, useRef } from 'react';

const STATES = { IDLE: 'idle', RECORDING: 'recording', UPLOADING: 'uploading', DONE: 'done', ERROR: 'error' };

const MIN_DURATION_S = 5;  // minimum seconds before stop is allowed
const MAX_DURATION_S = 30; // auto-stop at this duration

// ─── Age helpers ─────────────────────────────────────────────────────────────

function ageDaysFromBirthDate(birthDate) {
  if (!birthDate) return null;
  try {
    const diff = Date.now() - new Date(birthDate).getTime();
    return Math.max(0, Math.floor(diff / 86400000));
  } catch (_) { return null; }
}

// Which context groups to show based on age
// NEWBORN  0-90d:  feeding + health only (not mobile, environment irrelevant)
// EARLY    91-180d: feeding + health + environment
// 6m+      181d+:  health + environment (eating patterns less time-critical)
function getContextGroups(ageDays) {
  if (ageDays === null) return ['feeding', 'health', 'environment'];
  if (ageDays < 91)  return ['feeding', 'health'];
  if (ageDays < 181) return ['feeding', 'health', 'environment'];
  return ['health', 'environment'];
}

// ─── Context options (age-adapted) ───────────────────────────────────────────

function getFeedingOptions(ageDays) {
  if (ageDays !== null && ageDays < 91) {
    // Newborns feed every 1.5–3h
    return [
      { label: 'Just fed', value: 15 },
      { label: '1–2 hrs ago', value: 90 },
      { label: 'Over 2 hrs', value: 150 },
    ];
  }
  return [
    { label: 'Under 30 min', value: 15 },
    { label: '30–60 min', value: 45 },
    { label: '1–2 hrs ago', value: 90 },
    { label: 'Over 2 hrs', value: 150 },
  ];
}

const HEALTH_OPTIONS = [
  { label: 'Doing well', value: 'well' },
  { label: 'A bit fussy', value: 'fussy' },
  { label: 'Not feeling well', value: 'sick' },
  { label: 'Tired', value: 'tired' },
];

const ENVIRONMENT_OPTIONS = [
  { label: 'Quiet at home', value: 'quiet' },
  { label: 'A bit noisy', value: 'noisy' },
  { label: 'Travelling', value: 'travel' },
  { label: 'Outdoors', value: 'outdoor' },
];

function getFeedingLabel(ageDays) {
  if (ageDays !== null && ageDays < 91)  return 'When did baby last feed?';
  if (ageDays !== null && ageDays < 181) return 'When did baby last eat or feed?';
  return 'When did baby last eat?';
}

function getHealthLabel(ageDays) {
  if (ageDays !== null && ageDays < 181) return 'How is baby feeling?';
  return 'How are they feeling today?';
}

// ─── ChipGroup ────────────────────────────────────────────────────────────────

function ChipGroup({ options, selected, onChange }) {
  return (
    <div className="context-chips">
      {options.map(opt => (
        <button
          key={opt.value}
          type="button"
          className={`context-chip${selected === opt.value ? ' selected' : ''}`}
          onClick={() => onChange(selected === opt.value ? null : opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

// ─── RecordButton ─────────────────────────────────────────────────────────────

function RecordButton({ childId, childBirthDate, apiCall, onComplete }) {
  const [state, setState] = useState(STATES.IDLE);
  const [duration, setDuration] = useState(0);
  const [tooShort, setTooShort] = useState(false);
  const [error, setError] = useState(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [sessionContext, setSessionContext] = useState({
    feeding_minutes_ago: null,
    health_state: null,
    environment: null,
  });
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const pendingStopRef = useRef(false);

  const ageDays = ageDaysFromBirthDate(childBirthDate);
  const contextGroups = getContextGroups(ageDays);
  const feedingOptions = getFeedingOptions(ageDays);
  const feedingLabel = getFeedingLabel(ageDays);
  const healthLabel = getHealthLabel(ageDays);

  const setCtx = (key, value) => setSessionContext(prev => ({ ...prev, [key]: value }));
  const hasContext = Object.values(sessionContext).some(v => v !== null);

  const doStop = () => {
    clearInterval(timerRef.current);
    pendingStopRef.current = false;
    if (mediaRecorderRef.current?.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
      mediaRecorderRef.current.onstop = () => uploadAudio();
    }
    setState(STATES.UPLOADING);
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];
      pendingStopRef.current = false;

      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mediaRecorder.start(100);
      setState(STATES.RECORDING);
      setDuration(0);
      setTooShort(false);

      timerRef.current = setInterval(() => {
        setDuration(d => {
          const next = d + 1;
          if (next >= MAX_DURATION_S) { doStop(); return next; }
          if (pendingStopRef.current && next >= MIN_DURATION_S) { doStop(); return next; }
          return next;
        });
      }, 1000);
    } catch (err) {
      setError('Microphone access denied. Please allow microphone access.');
      setState(STATES.ERROR);
    }
  };

  const stopRecording = () => {
    setDuration(current => {
      if (current < MIN_DURATION_S) {
        setTooShort(true);
        pendingStopRef.current = true;
        return current;
      }
      doStop();
      return current;
    });
  };

  const uploadAudio = async () => {
    try {
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' });

      const uploadBody = { child_id: childId };
      if (hasContext) {
        const ctx = {};
        if (sessionContext.feeding_minutes_ago !== null && contextGroups.includes('feeding'))
          ctx.feeding_minutes_ago = sessionContext.feeding_minutes_ago;
        if (sessionContext.health_state !== null)
          ctx.health_state = sessionContext.health_state;
        if (sessionContext.environment !== null && contextGroups.includes('environment'))
          ctx.environment = sessionContext.environment;
        if (Object.keys(ctx).length > 0) uploadBody.session_context = ctx;
      }

      // 1. Get presigned URL
      const uploadData = await apiCall('/session/upload', {
        method: 'POST',
        body: JSON.stringify(uploadBody),
      });

      // 2. Upload directly to S3
      await fetch(uploadData.upload_url, {
        method: 'PUT',
        body: blob,
        headers: { 'Content-Type': 'audio/webm' },
      });

      // 3. Start processing pipeline
      await apiCall(`/session/${uploadData.session_id}/start`, { method: 'POST', body: '{}' });

      setState(STATES.DONE);
      onComplete?.(uploadData.session_id);

      setTimeout(() => {
        setState(STATES.IDLE);
        setContextOpen(false);
        setSessionContext({ feeding_minutes_ago: null, health_state: null, environment: null });
      }, 3000);
    } catch (err) {
      setError(err.message);
      setState(STATES.ERROR);
    }
  };

  const reset = () => { setState(STATES.IDLE); setError(null); setDuration(0); };

  return (
    <div className="record-button-container">
      {state === STATES.IDLE && (
        <>
          <div className="context-card">
            <button
              type="button"
              className={`context-toggle${contextOpen ? ' open' : ''}`}
              onClick={() => setContextOpen(o => !o)}
            >
              <span className="context-toggle-icon">{contextOpen ? '▾' : '▸'}</span>
              Add context
              {hasContext && <span className="context-dot" />}
              <span className="context-toggle-hint">helps me understand your baby better</span>
            </button>

            {contextOpen && (
              <div className="context-fields">
                {/* Feeding — only shown when age-relevant */}
                {contextGroups.includes('feeding') && (
                  <div className="context-group">
                    <p className="context-group-label">{feedingLabel}</p>
                    <ChipGroup
                      options={feedingOptions}
                      selected={sessionContext.feeding_minutes_ago}
                      onChange={v => setCtx('feeding_minutes_ago', v)}
                    />
                  </div>
                )}

                {/* Health — always shown */}
                <div className="context-group">
                  <p className="context-group-label">{healthLabel}</p>
                  <ChipGroup
                    options={HEALTH_OPTIONS}
                    selected={sessionContext.health_state}
                    onChange={v => setCtx('health_state', v)}
                  />
                </div>

                {/* Environment — shown from 3m+ */}
                {contextGroups.includes('environment') && (
                  <div className="context-group">
                    <p className="context-group-label">Where are you right now?</p>
                    <ChipGroup
                      options={ENVIRONMENT_OPTIONS}
                      selected={sessionContext.environment}
                      onChange={v => setCtx('environment', v)}
                    />
                  </div>
                )}

                <p className="context-inspire">
                  Sharing this helps me give more personalised insights over time.
                </p>
              </div>
            )}
          </div>

          <button className="record-btn" onClick={startRecording}>
            <span className="record-icon">●</span> Start Recording
          </button>
        </>
      )}
      {state === STATES.RECORDING && (
        <div className="recording-active">
          <div className="recording-indicator">
            <span className="pulse-dot" />
            <span>Recording… {duration}s / {MAX_DURATION_S}s</span>
          </div>
          {tooShort && (
            <p className="recording-min-msg">
              Continuing to {MIN_DURATION_S}s minimum for a useful analysis…
            </p>
          )}
          <button
            className={`stop-btn${duration < MIN_DURATION_S ? ' stop-btn--dim' : ''}`}
            onClick={stopRecording}
          >
            ■ Stop{duration < MIN_DURATION_S ? ` (min ${MIN_DURATION_S}s)` : ''}
          </button>
        </div>
      )}
      {state === STATES.UPLOADING && (
        <div className="uploading-state">
          <div className="spinner-small" />
          <span>Uploading and processing...</span>
        </div>
      )}
      {state === STATES.DONE && (
        <div className="done-state">✓ Session uploaded! Redirecting to your analysis…</div>
      )}
      {state === STATES.ERROR && (
        <div className="error-state">
          <p>{error}</p>
          <button onClick={reset}>Try Again</button>
        </div>
      )}
    </div>
  );
}

export default RecordButton;
