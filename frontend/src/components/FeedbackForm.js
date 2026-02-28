import { useState, useMemo } from 'react';

/**
 * FeedbackForm — Context-aware feedback for model training.
 *
 * Adapts based on what was detected:
 * - Adult detected → "Was speaker detection correct?" (Adult / Baby / Both)
 * - Cry detected → Emotion feedback (multi-select, age-appropriate)
 * - Speech/laugh/other → Baby language feedback (sound + meaning text fields)
 *
 * Both emotion + language sections feed into self-learning models.
 */

// Age-specific emotion lists matching cry_analyzer.py brackets
const EMOTIONS_0_6M = [
  { key: 'hungry', label: 'Hungry', icon: '🍼' },
  { key: 'tired', label: 'Tired', icon: '😴' },
  { key: 'discomfort', label: 'Uncomfortable', icon: '😟' },
  { key: 'gas', label: 'Gas / Colic', icon: '💨' },
  { key: 'burp', label: 'Needs Burp', icon: '🫧' },
  { key: 'pain', label: 'In Pain', icon: '🩹' },
  { key: 'closeness', label: 'Wants Closeness', icon: '🤗' },
];

const EMOTIONS_6_12M = [
  ...EMOTIONS_0_6M,
  { key: 'frustration', label: 'Frustrated', icon: '😣' },
  { key: 'separation_anxiety', label: 'Separation Anxiety', icon: '😢' },
  { key: 'boredom', label: 'Bored', icon: '😐' },
];

const EMOTIONS_12_18M = [
  ...EMOTIONS_6_12M,
  { key: 'tantrum', label: 'Tantrum', icon: '😤' },
  { key: 'fear', label: 'Scared', icon: '😰' },
];

const EMOTIONS_18_24M = [
  ...EMOTIONS_12_18M,
  { key: 'jealousy', label: 'Jealous', icon: '😒' },
  { key: 'embarrassment', label: 'Embarrassed', icon: '🙈' },
];

const EMOTIONS_24_36M = [
  ...EMOTIONS_18_24M,
  { key: 'excitement', label: 'Excited', icon: '🤩' },
  { key: 'sadness', label: 'Sad', icon: '😢' },
];

function getEmotionsForAge(ageDays) {
  if (!ageDays || ageDays < 0) return EMOTIONS_24_36M;
  const months = ageDays / 30.44;
  if (months < 6) return EMOTIONS_0_6M;
  if (months < 12) return EMOTIONS_6_12M;
  if (months < 18) return EMOTIONS_12_18M;
  if (months < 24) return EMOTIONS_18_24M;
  return EMOTIONS_24_36M;
}

function FeedbackForm({ onSubmit, displayType, detectedEmotion, ageDays, isAdult }) {
  // Determine which tabs are relevant
  const showSpeakerTab = isAdult || displayType === 'speech' || displayType === 'laugh';
  const showEmotionTab = displayType === 'cry' || displayType === 'mixed';
  const showLanguageTab = !isAdult && displayType !== 'silence' && displayType !== 'noise';

  // Pick default active tab based on context
  const defaultTab = isAdult ? 'speaker' : showEmotionTab ? 'emotion' : 'language';

  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState(defaultTab);

  // Speaker feedback state
  const [speakerAnswer, setSpeakerAnswer] = useState('');
  const [speakerNotes, setSpeakerNotes] = useState('');

  // Language feedback state
  const [babySound, setBabySound] = useState('');
  const [parentMeaning, setParentMeaning] = useState('');

  // Cry emotion feedback state
  const [wasCorrect, setWasCorrect] = useState(null);
  const [selectedEmotions, setSelectedEmotions] = useState([]);
  const [emotionNotes, setEmotionNotes] = useState('');

  const emotions = useMemo(() => getEmotionsForAge(ageDays), [ageDays]);

  const canSubmitSpeaker = !!speakerAnswer;
  const canSubmitLanguage = !!(babySound.trim() || parentMeaning.trim());
  const canSubmitEmotion = wasCorrect !== null && (wasCorrect || selectedEmotions.length > 0);

  const canSubmit =
    activeTab === 'speaker' ? canSubmitSpeaker :
    activeTab === 'language' ? canSubmitLanguage :
    canSubmitEmotion;

  const toggleEmotion = (key) => {
    setSelectedEmotions(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key]
    );
  };

  const handleSubmit = () => {
    if (!canSubmit) return;

    if (activeTab === 'speaker') {
      onSubmit({
        feedback_type: 'speaker_verification',
        speaker_answer: speakerAnswer,
        notes: speakerNotes.trim() || undefined,
      });
    } else if (activeTab === 'language') {
      onSubmit({
        feedback_type: 'language',
        baby_sound: babySound.trim(),
        parent_meaning: parentMeaning.trim(),
      });
    } else {
      onSubmit({
        feedback_type: 'cry_emotion',
        was_correct: wasCorrect,
        confirmed_emotions: wasCorrect ? [detectedEmotion] : selectedEmotions,
        notes: emotionNotes.trim() || undefined,
      });
    }

    // Reset and close
    setSpeakerAnswer('');
    setSpeakerNotes('');
    setBabySound('');
    setParentMeaning('');
    setWasCorrect(null);
    setSelectedEmotions([]);
    setEmotionNotes('');
    setOpen(false);
  };

  // Don't show feedback at all for silence/noise with no other tabs
  const hasTabs = showSpeakerTab || showEmotionTab || showLanguageTab;
  if (!hasTabs) return null;

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

  // Count available tabs for tab bar display
  const availableTabs = [];
  if (showSpeakerTab) availableTabs.push('speaker');
  if (showEmotionTab) availableTabs.push('emotion');
  if (showLanguageTab) availableTabs.push('language');

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

        {/* Tab selector — only show if multiple tabs */}
        {availableTabs.length > 1 && (
          <div className="feedback-tabs">
            {showSpeakerTab && (
              <button
                className={`feedback-tab ${activeTab === 'speaker' ? 'active' : ''}`}
                onClick={() => setActiveTab('speaker')}
              >
                🔊 Speaker
              </button>
            )}
            {showEmotionTab && (
              <button
                className={`feedback-tab ${activeTab === 'emotion' ? 'active' : ''}`}
                onClick={() => setActiveTab('emotion')}
              >
                😢 Cry Emotion
              </button>
            )}
            {showLanguageTab && (
              <button
                className={`feedback-tab ${activeTab === 'language' ? 'active' : ''}`}
                onClick={() => setActiveTab('language')}
              >
                🗣️ Baby Language
              </button>
            )}
          </div>
        )}

        {/* Speaker Verification Section */}
        {activeTab === 'speaker' && showSpeakerTab && (
          <div className="feedback-section-inner">
            <p className="feedback-section-desc">
              Was our speaker detection correct? This helps us better separate
              adult and baby voices in recordings.
            </p>

            <div className="feedback-group">
              <label className="feedback-label">Who was speaking in this recording?</label>
              <div className="speaker-selector-grid">
                {[
                  { key: 'adult', label: 'Adult / Parent', icon: '👤' },
                  { key: 'baby', label: 'My Baby', icon: '👶' },
                  { key: 'both', label: 'Both Present', icon: '👨‍👩‍👦' },
                  { key: 'other', label: 'Older Child', icon: '🧒' },
                ].map((opt) => (
                  <button
                    key={opt.key}
                    className={`speaker-option-btn ${speakerAnswer === opt.key ? 'selected' : ''}`}
                    onClick={() => setSpeakerAnswer(opt.key)}
                  >
                    <span className="speaker-option-icon">{opt.icon}</span>
                    <span className="speaker-option-label">{opt.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="feedback-group">
              <label className="feedback-label">
                Anything else? <span className="feedback-optional">(optional)</span>
              </label>
              <textarea
                className="feedback-textarea"
                placeholder="e.g. baby was in background, father was talking..."
                value={speakerNotes}
                onChange={(e) => setSpeakerNotes(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        )}

        {/* Cry Emotion Feedback Section */}
        {activeTab === 'emotion' && showEmotionTab && (
          <div className="feedback-section-inner">
            <p className="feedback-section-desc">
              Was our emotion detection accurate? Select all that apply — your feedback
              trains the model for all children in this age group.
            </p>

            {detectedEmotion && (
              <div className="feedback-group">
                <label className="feedback-label">
                  We detected: <strong>{detectedEmotion}</strong>
                </label>
                <div className="feedback-correct-buttons">
                  <button
                    className={`correct-btn ${wasCorrect === true ? 'selected yes' : ''}`}
                    onClick={() => { setWasCorrect(true); setSelectedEmotions([]); }}
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

            {!detectedEmotion && (
              <div className="feedback-group">
                <label className="feedback-label">
                  What was your baby feeling? (select all that apply)
                </label>
              </div>
            )}

            {(wasCorrect === false || !detectedEmotion) && (
              <div className="feedback-group">
                {detectedEmotion && (
                  <label className="feedback-label">
                    What was your baby actually feeling? (select all that apply)
                  </label>
                )}
                <div className="emotion-selector-grid">
                  {emotions.map((emo) => (
                    <button
                      key={emo.key}
                      className={`emotion-selector-btn ${selectedEmotions.includes(emo.key) ? 'selected' : ''}`}
                      onClick={() => toggleEmotion(emo.key)}
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
                value={emotionNotes}
                onChange={(e) => setEmotionNotes(e.target.value)}
                rows={2}
              />
            </div>
          </div>
        )}

        {/* Baby Language Feedback Section */}
        {activeTab === 'language' && showLanguageTab && (
          <div className="feedback-section-inner">
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
