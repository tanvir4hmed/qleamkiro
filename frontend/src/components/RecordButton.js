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
function getContextGroups(ageDays) {
  if (ageDays === null) return ['feeding', 'health', 'sleep', 'behavioral_cues', 'environment'];
  const groups = [];
  if (ageDays < 181) groups.push('feeding');
  groups.push('health');
  if (ageDays >= 91)  groups.push('sleep');
  groups.push('behavioral_cues');
  if (ageDays >= 91)  groups.push('environment');
  if (ageDays >= 365) groups.push('trigger');
  return groups;
}

// Which behavioral cue flags to show (age-gated)
function getBehavioralCues(ageDays) {
  const cues = [];
  if (ageDays === null || ageDays < 120) cues.push('rooting_flag');      // 0–4m
  if (ageDays === null || ageDays < 270) cues.push('hand_to_mouth_flag'); // 0–9m
  cues.push('eye_rub_flag');                                               // all ages
  if (ageDays !== null && ageDays >= 365) cues.push('tantrum_body_flag'); // 12m+
  return cues;
}

// ─── Context options ──────────────────────────────────────────────────────────

function getFeedingOptions(ageDays) {
  if (ageDays !== null && ageDays < 91) {
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
  { label: 'Doing well', value: 'healthy' },
  { label: 'A bit fussy', value: 'other' },
  { label: 'Not feeling well', value: 'sick' },
  { label: 'Teething', value: 'teething' },
];

const ENVIRONMENT_OPTIONS = [
  { label: 'Quiet at home', value: 'home_quiet' },
  { label: 'A bit noisy', value: 'home_noisy' },
  { label: 'Travelling', value: 'car' },
  { label: 'Outdoors', value: 'outdoor' },
];

const SLEEP_OPTIONS = [
  { label: 'Just woke', value: 0 },
  { label: 'Well rested', value: 1 },
  { label: 'Getting tired', value: 2 },
  { label: 'Overtired', value: 3 },
];

// Trigger options (shown 12m+)
const TRIGGER_OPTIONS = [
  { label: 'Nothing obvious', value: 0 },
  { label: 'Just woke up', value: 1 },
  { label: 'Hungry / feeding', value: 2 },
  { label: 'Activity stopped', value: 3 },
  { label: 'Toy taken away', value: 4 },
  { label: 'I left the room', value: 5 },
  { label: 'Too much going on', value: 6 },
  { label: 'Big change / transition', value: 7 },
  { label: 'Hurt or in pain', value: 8 },
];

const BEHAVIORAL_CUE_LABELS = {
  rooting_flag:       'Rooting / searching for feed',
  hand_to_mouth_flag: 'Hand to mouth / sucking',
  eye_rub_flag:       'Rubbing eyes',
  tantrum_body_flag:  'Stiffening / arching back',
};

function getFeedingLabel(ageDays) {
  if (ageDays !== null && ageDays < 91)  return 'When did baby last feed?';
  if (ageDays !== null && ageDays < 181) return 'When did baby last eat or feed?';
  return 'When did baby last eat?';
}

function getHealthLabel(ageDays) {
  if (ageDays !== null && ageDays < 181) return 'How is baby feeling?';
  return 'How are they feeling today?';
}

function getChildTerm(ageDays) {
  if (ageDays === null || ageDays < 365) return 'baby';
  if (ageDays < 730) return 'toddler';
  return 'child';
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

// Toggle chip — single tap to mark as observed, tap again to clear
function ToggleChip({ label, active, onChange }) {
  return (
    <button
      type="button"
      className={`context-chip behavioral-chip${active ? ' selected' : ''}`}
      onClick={() => onChange(!active)}
    >
      {active ? '✓ ' : ''}{label}
    </button>
  );
}

// ─── Empty context object ─────────────────────────────────────────────────────

function emptyContext() {
  return {
    feeding_minutes_ago: null,
    health_state: null,
    environment: null,
    sleep_status: null,
    rooting_flag: false,
    hand_to_mouth_flag: false,
    eye_rub_flag: false,
    tantrum_body_flag: false,
    trigger_code: null,
  };
}

// ─── RecordButton ─────────────────────────────────────────────────────────────

function RecordButton({ childId, childBirthDate, apiCall, onComplete }) {
  const [state, setState] = useState(STATES.IDLE);
  const [duration, setDuration] = useState(0);
  const [tooShort, setTooShort] = useState(false);
  const [error, setError] = useState(null);
  const [contextOpen, setContextOpen] = useState(false);
  const [sessionContext, setSessionContext] = useState(emptyContext());
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const pendingStopRef = useRef(false);

  const ageDays = ageDaysFromBirthDate(childBirthDate);
  const contextGroups = getContextGroups(ageDays);
  const behavioralCues = getBehavioralCues(ageDays);
  const feedingOptions = getFeedingOptions(ageDays);
  const feedingLabel = getFeedingLabel(ageDays);
  const healthLabel = getHealthLabel(ageDays);
  const childTerm = getChildTerm(ageDays);

  const setCtx = (key, value) => setSessionContext(prev => ({ ...prev, [key]: value }));

  const hasContext = (
    sessionContext.feeding_minutes_ago !== null ||
    sessionContext.health_state !== null ||
    sessionContext.environment !== null ||
    sessionContext.sleep_status !== null ||
    sessionContext.rooting_flag ||
    sessionContext.hand_to_mouth_flag ||
    sessionContext.eye_rub_flag ||
    sessionContext.tantrum_body_flag ||
    sessionContext.trigger_code !== null
  );

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
        // Original fields
        if (sessionContext.feeding_minutes_ago !== null && contextGroups.includes('feeding'))
          ctx.feeding_minutes_ago = sessionContext.feeding_minutes_ago;
        if (sessionContext.health_state !== null)
          ctx.health_state = sessionContext.health_state;
        if (sessionContext.environment !== null && contextGroups.includes('environment'))
          ctx.environment = sessionContext.environment;
        // New: sleep status
        if (sessionContext.sleep_status !== null && contextGroups.includes('sleep'))
          ctx.sleep_status = sessionContext.sleep_status;
        // New: behavioral flags — only include when observed (1); omit when not observed (unknown)
        for (const flag of ['rooting_flag', 'hand_to_mouth_flag', 'eye_rub_flag', 'tantrum_body_flag']) {
          if (sessionContext[flag]) ctx[flag] = 1;
        }
        // New: trigger code
        if (sessionContext.trigger_code !== null && contextGroups.includes('trigger'))
          ctx.trigger_code = sessionContext.trigger_code;

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
        setSessionContext(emptyContext());
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
              <span className="context-toggle-hint">helps me understand your {childTerm} better</span>
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

                {/* Sleep status — shown from 3m+ */}
                {contextGroups.includes('sleep') && (
                  <div className="context-group">
                    <p className="context-group-label">How long have they been awake?</p>
                    <ChipGroup
                      options={SLEEP_OPTIONS}
                      selected={sessionContext.sleep_status}
                      onChange={v => setCtx('sleep_status', v)}
                    />
                  </div>
                )}

                {/* Behavioral cues — age-gated, shown if any cues apply */}
                {behavioralCues.length > 0 && (
                  <div className="context-group">
                    <p className="context-group-label">What did you notice? <span className="context-group-hint">(tap all that apply)</span></p>
                    <div className="context-chips">
                      {behavioralCues.map(flag => (
                        <ToggleChip
                          key={flag}
                          label={BEHAVIORAL_CUE_LABELS[flag]}
                          active={sessionContext[flag]}
                          onChange={v => setCtx(flag, v)}
                        />
                      ))}
                    </div>
                  </div>
                )}

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

                {/* Trigger — shown from 12m+ */}
                {contextGroups.includes('trigger') && (
                  <div className="context-group">
                    <p className="context-group-label">What was happening before?</p>
                    <ChipGroup
                      options={TRIGGER_OPTIONS}
                      selected={sessionContext.trigger_code}
                      onChange={v => setCtx('trigger_code', v)}
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
