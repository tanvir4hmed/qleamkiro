import { useState } from 'react';

// 7-class emotion taxonomy matching cry_analyzer.py / emotion_classifier.py
const EMOTIONS = [
  { key: 'hungry', label: 'Hungry', icon: '🍼' },
  { key: 'tired', label: 'Tired', icon: '😴' },
  { key: 'discomfort', label: 'Uncomfortable', icon: '😟' },
  { key: 'gas', label: 'Gas / Colic', icon: '💨' },
  { key: 'burp', label: 'Needs Burp', icon: '🫧' },
  { key: 'pain', label: 'In Pain', icon: '🩹' },
  { key: 'content', label: 'Content / Settling', icon: '😊' },
];

function FeedbackForm({ onSubmit, displayType, detectedEmotion, ageDays }) {
  const [open, setOpen] = useState(false);
  const [wasCorrect, setWasCorrect] = useState(null);
  const [selectedEmotion, setSelectedEmotion] = useState('');
  const [notes, setNotes] = useState('');

  const showEmotionFeedback = displayType === 'cry' || displayType === 'mixed';
  const emotions = EMOTIONS;
  const confirmedEmotion = wasCorrect ? detectedEmotion : selectedEmotion;
  const canSubmit = !!confirmedEmotion;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit({
      feedback_type: 'cry_emotion',
      was_correct: !!wasCorrect,
      confirmed_emotion: confirmedEmotion,
      notes: notes.trim() || undefined,
    });

    setWasCorrect(null);
    setSelectedEmotion('');
    setNotes('');
    setOpen(false);
  };

  if (!showEmotionFeedback) return null;

  if (!open) {
    return (
      <div className="feedback-reveal">
        <button className="feedback-reveal-btn" onClick={() => setOpen(true)}>
          <span>Help Qleam learn</span>
          <span className="feedback-reveal-hint">Your feedback improves cry detection</span>
        </button>
      </div>
    );
  }

  return (
    <div
      className="feedback-modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div className="feedback-modal">
        <div className="feedback-form-header">
          <span className="feedback-form-title">Help Qleam Learn</span>
          <button className="feedback-skip-btn" onClick={() => setOpen(false)}>
            Close
          </button>
        </div>

        <div className="feedback-section-inner">
          <p className="feedback-section-desc">
            Was our emotion detection accurate? Your feedback improves cry analysis.
          </p>

          {detectedEmotion && (
            <div className="feedback-group">
              <label className="feedback-label">
                We detected: <strong>{detectedEmotion}</strong>
              </label>
              <div className="feedback-correct-buttons">
                <button
                  className={`correct-btn ${wasCorrect === true ? 'selected yes' : ''}`}
                  onClick={() => {
                    setWasCorrect(true);
                    setSelectedEmotion('');
                  }}
                >
                  ✓ Yes, correct
                </button>
                <button
                  className={`correct-btn ${wasCorrect === false ? 'selected no' : ''}`}
                  onClick={() => setWasCorrect(false)}
                >
                  ✗ No, it was different
                </button>
              </div>
            </div>
          )}

          {(wasCorrect === false || !detectedEmotion) && (
            <div className="feedback-group">
              <label className="feedback-label">
                What was your baby actually feeling?
              </label>
              <div className="emotion-selector-grid">
                {emotions.map((emo) => (
                  <button
                    key={emo.key}
                    className={`emotion-selector-btn ${selectedEmotion === emo.key ? 'selected' : ''}`}
                    onClick={() => setSelectedEmotion(emo.key)}
                  >
                    <span className="emotion-icon">{emo.icon}</span>
                    <span className="emotion-label">{emo.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="feedback-group">
            <label className="feedback-label">
              Anything else to add? <span className="feedback-optional">(optional)</span>
            </label>
            <textarea
              className="feedback-textarea"
              placeholder="e.g. baby was also teething, just woke up from nap..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        <button
          className="submit-feedback-btn"
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          Submit Feedback
        </button>
      </div>
    </div>
  );
}

export default FeedbackForm;
