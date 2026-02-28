import { useState } from 'react';

/**
 * FeedbackForm — Two-section feedback for model training.
 *
 * Section 1: Baby's Own Language
 *   "What sound did your baby make?" (text)
 *   "What do you think they meant?" (text)
 *
 * Section 2: Cry Emotion Feedback
 *   "Was our detection correct?" (yes/no)
 *   "What was your baby feeling?" (emotion selector)
 *
 * Both sections feed into self-learning models.
 */

const CRY_EMOTIONS = [
  { key: 'hungry', label: 'Hungry', icon: '🍼' },
  { key: 'tired', label: 'Tired', icon: '😴' },
  { key: 'discomfort', label: 'Uncomfortable', icon: '😟' },
  { key: 'pain', label: 'In Pain', icon: '🩹' },
  { key: 'gas', label: 'Gas / Colic', icon: '💨' },
  { key: 'burp', label: 'Needs Burp', icon: '🫧' },
  { key: 'closeness', label: 'Wants Closeness', icon: '🤗' },
  { key: 'frustration', label: 'Frustrated', icon: '😣' },
  { key: 'fear', label: 'Scared', icon: '😰' },
  { key: 'boredom', label: 'Bored', icon: '😐' },
  { key: 'separation_anxiety', label: 'Separation Anxiety', icon: '😢' },
  { key: 'tantrum', label: 'Tantrum', icon: '😤' },
];

function FeedbackForm({ onSubmit, displayType, detectedEmotion }) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState(
    displayType === 'cry' ? 'emotion' : 'language'
  );

  // Language feedback state
  const [babySound, setBabySound] = useState('');
  const [parentMeaning, setParentMeaning] = useState('');

  // Cry emotion feedback state
  const [wasCorrect, setWasCorrect] = useState(null);
  const [selectedEmotion, setSelectedEmotion] = useState('');

  const showLanguageTab = displayType !== 'silence' && displayType !== 'noise';
  const showEmotionTab = displayType === 'cry' || displayType === 'mixed';

  const canSubmitLanguage = !!(babySound.trim() || parentMeaning.trim());
  const canSubmitEmotion = wasCorrect !== null && (wasCorrect || selectedEmotion);
  const canSubmit = activeTab === 'language' ? canSubmitLanguage : canSubmitEmotion;

  const handleSubmit = () => {
    if (!canSubmit) return;

    if (activeTab === 'language') {
      onSubmit({
        feedback_type: 'language',
        baby_sound: babySound.trim(),
        parent_meaning: parentMeaning.trim(),
      });
    } else {
      onSubmit({
        feedback_type: 'cry_emotion',
        was_correct: wasCorrect,
        confirmed_emotion: wasCorrect ? detectedEmotion : selectedEmotion,
      });
    }

    // Reset and close
    setBabySound('');
    setParentMeaning('');
    setWasCorrect(null);
    setSelectedEmotion('');
    setOpen(false);
  };

  if (!open) {
    return (
      <div className="feedback-reveal">
        <button className="feedback-reveal-btn" onClick={() => setOpen(true)}>
          <span>Help Qleam learn</span>
          <span className="feedback-reveal-hint">
            Your feedback improves detection accuracy
          </span>
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

        {/* Tab selector */}
        {showLanguageTab && showEmotionTab && (
          <div className="feedback-tabs">
            <button
              className={`feedback-tab ${activeTab === 'language' ? 'active' : ''}`}
              onClick={() => setActiveTab('language')}
            >
              🗣️ Baby Language
            </button>
            <button
              className={`feedback-tab ${activeTab === 'emotion' ? 'active' : ''}`}
              onClick={() => setActiveTab('emotion')}
            >
              😢 Cry Emotion
            </button>
          </div>
        )}

        {/* Language Feedback Section */}
        {activeTab === 'language' && showLanguageTab && (
          <div className="feedback-section">
            <p className="feedback-section-desc">
              Help us understand your baby's unique sounds. Over time, Qleam will
              learn to recognize what your baby is trying to say.
            </p>

            <div className="feedback-group">
              <label className="feedback-label">
                What sound did your baby make?
              </label>
              <input
                type="text"
                className="feedback-input"
                placeholder='e.g. "ba ba ba", "neh neh", "da da"'
                value={babySound}
                onChange={(e) => setBabySound(e.target.value)}
              />
            </div>

            <div className="feedback-group">
              <label className="feedback-label">
                What do you think they meant?
              </label>
              <input
                type="text"
                className="feedback-input"
                placeholder='e.g. "want milk", "pick me up", "play with me"'
                value={parentMeaning}
                onChange={(e) => setParentMeaning(e.target.value)}
              />
            </div>
          </div>
        )}

        {/* Cry Emotion Feedback Section */}
        {activeTab === 'emotion' && showEmotionTab && (
          <div className="feedback-section">
            <p className="feedback-section-desc">
              Was our emotion detection correct? Your feedback helps us better
              understand baby cries across all ages.
            </p>

            {detectedEmotion && (
              <div className="feedback-group">
                <label className="feedback-label">
                  We detected: <strong>{detectedEmotion}</strong>
                </label>
                <div className="feedback-correct-buttons">
                  <button
                    className={`correct-btn ${wasCorrect === true ? 'selected yes' : ''}`}
                    onClick={() => { setWasCorrect(true); setSelectedEmotion(''); }}
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
                  {CRY_EMOTIONS.map((emo) => (
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
          </div>
        )}

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
