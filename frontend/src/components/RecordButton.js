import React, { useState, useRef } from 'react';

const STATES = { IDLE: 'idle', RECORDING: 'recording', UPLOADING: 'uploading', DONE: 'done', ERROR: 'error' };

const FEEDING_OPTIONS = [
  { label: 'Under 30 min', value: 15 },
  { label: '30–60 min', value: 45 },
  { label: '1–2 hrs ago', value: 90 },
  { label: 'Over 2 hrs', value: 150 },
];

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

function RecordButton({ childId, apiCall, onComplete }) {
  const [state, setState] = useState(STATES.IDLE);
  const [duration, setDuration] = useState(0);
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

  const setCtx = (key, value) => setSessionContext(prev => ({ ...prev, [key]: value }));

  const hasContext = Object.values(sessionContext).some(v => v !== null);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mediaRecorder.start(100);
      setState(STATES.RECORDING);
      setDuration(0);

      timerRef.current = setInterval(() => {
        setDuration(d => {
          if (d >= 30) { stopRecording(); return d; }
          return d + 1;
        });
      }, 1000);
    } catch (err) {
      setError('Microphone access denied. Please allow microphone access.');
      setState(STATES.ERROR);
    }
  };

  const stopRecording = () => {
    clearInterval(timerRef.current);
    if (mediaRecorderRef.current?.state !== 'inactive') {
      mediaRecorderRef.current.stop();
      mediaRecorderRef.current.stream.getTracks().forEach(t => t.stop());
      mediaRecorderRef.current.onstop = () => uploadAudio();
    }
    setState(STATES.UPLOADING);
  };

  const uploadAudio = async () => {
    try {
      const blob = new Blob(chunksRef.current, { type: 'audio/webm' });

      // Build upload body — include context only if any was selected
      const uploadBody = { child_id: childId };
      if (hasContext) {
        const ctx = {};
        if (sessionContext.feeding_minutes_ago !== null) ctx.feeding_minutes_ago = sessionContext.feeding_minutes_ago;
        if (sessionContext.health_state !== null) ctx.health_state = sessionContext.health_state;
        if (sessionContext.environment !== null) ctx.environment = sessionContext.environment;
        uploadBody.session_context = ctx;
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

      // Reset after 3 seconds
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
                <div className="context-group">
                  <p className="context-group-label">When did baby last eat?</p>
                  <ChipGroup
                    options={FEEDING_OPTIONS}
                    selected={sessionContext.feeding_minutes_ago}
                    onChange={v => setCtx('feeding_minutes_ago', v)}
                  />
                </div>
                <div className="context-group">
                  <p className="context-group-label">How are they feeling today?</p>
                  <ChipGroup
                    options={HEALTH_OPTIONS}
                    selected={sessionContext.health_state}
                    onChange={v => setCtx('health_state', v)}
                  />
                </div>
                <div className="context-group">
                  <p className="context-group-label">Where are you right now?</p>
                  <ChipGroup
                    options={ENVIRONMENT_OPTIONS}
                    selected={sessionContext.environment}
                    onChange={v => setCtx('environment', v)}
                  />
                </div>
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
            <span>Recording... {duration}s / 30s</span>
          </div>
          <button className="stop-btn" onClick={stopRecording}>■ Stop</button>
        </div>
      )}
      {state === STATES.UPLOADING && (
        <div className="uploading-state">
          <div className="spinner-small" />
          <span>Uploading and processing...</span>
        </div>
      )}
      {state === STATES.DONE && (
        <div className="done-state">✓ Session uploaded! Processing in background.</div>
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
