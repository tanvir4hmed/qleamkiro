import React, { useState, useRef } from 'react';

const STATES = { IDLE: 'idle', RECORDING: 'recording', UPLOADING: 'uploading', DONE: 'done', ERROR: 'error' };

function RecordButton({ childId, apiCall, onComplete }) {
  const [state, setState] = useState(STATES.IDLE);
  const [duration, setDuration] = useState(0);
  const [error, setError] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);

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

      // 1. Get presigned URL
      const uploadData = await apiCall('/session/upload', {
        method: 'POST',
        body: JSON.stringify({ child_id: childId }),
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
      setTimeout(() => setState(STATES.IDLE), 3000);
    } catch (err) {
      setError(err.message);
      setState(STATES.ERROR);
    }
  };

  const reset = () => { setState(STATES.IDLE); setError(null); setDuration(0); };

  return (
    <div className="record-button-container">
      {state === STATES.IDLE && (
        <button className="record-btn" onClick={startRecording}>
          <span className="record-icon">●</span> Start Recording
        </button>
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
