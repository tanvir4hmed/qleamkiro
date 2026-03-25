import React, { useState } from 'react';

const DUNSTAN_SOUNDS = {
  neh: {
    label: 'Neh',
    emotion: 'Hungry',
    explanation: '"Neh" is a reflexive sound babies make when hungry, caused by the sucking reflex pushing the tongue to the roof of the mouth.',
  },
  owh: {
    label: 'Owh',
    emotion: 'Tired',
    explanation: '"Owh" is a yawn-like reflex sound. The oval mouth shape during a yawn creates this distinctive sound, signaling tiredness.',
  },
  heh: {
    label: 'Heh',
    emotion: 'Discomfort',
    explanation: '"Heh" is triggered by skin or physical discomfort. The breathy quality comes from the body\'s stress response to an irritant.',
  },
  eairh: {
    label: 'Eairh',
    emotion: 'Gas / Colic',
    explanation: '"Eairh" comes from the lower abdomen tensing with trapped gas. The straining, grunting quality is distinctive.',
  },
  eh: {
    label: 'Eh',
    emotion: 'Needs Burp',
    explanation: '"Eh" is caused by trapped air in the chest trying to rise. The short, repetitive pushing sound signals the need to burp.',
  },
};

const CLOUDFRONT_BASE = 'https://d1234567890.cloudfront.net/dunstan';

function DunstanSection({ dunstanSound, dunstanDescription, ageDays }) {
  const [playing, setPlaying] = useState(false);
  const [audioError, setAudioError] = useState(false);

  // Only show for 0-3m babies (up to ~90 days, with buffer to 180)
  if (ageDays !== null && ageDays !== undefined && ageDays > 180) return null;
  if (!dunstanSound) return null;

  const sound = DUNSTAN_SOUNDS[dunstanSound.toLowerCase()];
  if (!sound) return null;

  const description = dunstanDescription || sound.explanation;

  const handlePlay = () => {
    try {
      const audioUrl = `${CLOUDFRONT_BASE}/${dunstanSound.toLowerCase()}.mp3`;
      const audio = new Audio(audioUrl);
      audio.onended = () => setPlaying(false);
      audio.onerror = () => {
        setPlaying(false);
        setAudioError(true);
      };
      setPlaying(true);
      setAudioError(false);
      audio.play().catch(() => {
        setPlaying(false);
        setAudioError(true);
      });
    } catch (_) {
      setAudioError(true);
    }
  };

  return (
    <div className="dunstan-section">
      <div className="dunstan-header">
        <span className="dunstan-icon">🔊</span>
        <span className="dunstan-match">
          Sounds like "<strong>{sound.label}</strong>" ({sound.emotion})
        </span>
      </div>

      <button
        className={`dunstan-play-btn ${playing ? 'playing' : ''}`}
        onClick={handlePlay}
        disabled={playing}
      >
        {playing ? '⏸ Playing...' : '▶ Play reference sound'}
      </button>

      {audioError && (
        <p className="dunstan-audio-error">
          Reference sound not available yet — coming soon.
        </p>
      )}

      <p className="dunstan-explanation">{description}</p>
    </div>
  );
}

export default DunstanSection;
