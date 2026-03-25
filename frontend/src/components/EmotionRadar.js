import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';

const EMOTION_LABELS = {
  hungry: 'Hungry',
  tired: 'Tired',
  discomfort: 'Discomfort',
  gas: 'Gas',
  pain: 'Pain',
  burp: 'Burp',
  content: 'Content',
};

const EMOTION_ORDER = ['hungry', 'tired', 'discomfort', 'gas', 'pain', 'burp', 'content'];
const EMOTION_ALIASES = {
  hunger: 'hungry',
  fatigue: 'tired',
  belly_pain: 'gas',
  normal: 'content',
  happy: 'content',
};

function toRatio(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  if (num > 1) return Math.max(0, Math.min(1, num / 100));
  return Math.max(0, Math.min(1, num));
}

function normalizeEmotionScores(emotionScores) {
  if (!emotionScores || typeof emotionScores !== 'object') return {};

  let source = emotionScores;
  if (source.emotion_scores && typeof source.emotion_scores === 'object') {
    source = source.emotion_scores;
  } else if (source.emotion_probabilities && typeof source.emotion_probabilities === 'object') {
    source = source.emotion_probabilities;
  }

  const normalized = {};
  Object.entries(source || {}).forEach(([rawKey, rawValue]) => {
    const key = EMOTION_ALIASES[rawKey] || rawKey;
    const ratio = toRatio(rawValue);
    if (ratio !== null) normalized[key] = ratio;
  });

  return normalized;
}

function describeEmotionScore(scorePct, isPrimary) {
  if (isPrimary) return `${scorePct}% (top match)`;
  if (scorePct >= 60) return `${scorePct}% (strong signal)`;
  if (scorePct >= 35) return `${scorePct}% (moderate signal)`;
  if (scorePct >= 15) return `${scorePct}% (weak signal)`;
  return `${scorePct}% (very low signal)`;
}

function EmotionRadar({ emotionScores, topEmotions, primaryEmotion }) {
  const normalized = normalizeEmotionScores(emotionScores);
  if (Array.isArray(topEmotions)) {
    topEmotions.forEach((entry) => {
      const key = EMOTION_ALIASES[entry?.key] || entry?.key;
      if (!key || normalized[key] !== undefined) return;
      const ratio = toRatio(entry?.score);
      if (ratio !== null) normalized[key] = ratio;
    });
  }

  if (Object.keys(normalized).length === 0) return null;

  const data = EMOTION_ORDER.map((key) => ({
    emotion: EMOTION_LABELS[key] || key,
    score: Math.round((normalized[key] || 0) * 100),
    key,
  }));
  const descriptions = data.map((item) => ({
    label: item.emotion,
    text: describeEmotionScore(item.score, item.key === primaryEmotion),
  }));

  const accentColor = primaryEmotion === 'pain' ? '#FF6B6B'
    : primaryEmotion === 'tired' ? '#7B68EE'
    : primaryEmotion === 'hungry' ? '#FF9F43'
    : primaryEmotion === 'gas' ? '#54A0FF'
    : '#4ECDC4';

  return (
    <div className="radar-chart-container">
      <h4 className="radar-title">Emotion Match</h4>
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="emotion"
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={false}
            axisLine={false}
          />
          <Radar
            dataKey="score"
            stroke={accentColor}
            fill={accentColor}
            fillOpacity={0.25}
            strokeWidth={2}
          />
          <Tooltip
            formatter={(value) => [`${value}%`, 'Score']}
            contentStyle={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              fontSize: '12px',
            }}
          />
        </RadarChart>
      </ResponsiveContainer>
      <div className="acoustic-descriptions">
        {descriptions.map((d) => (
          <div key={d.label} className="acoustic-desc-row">
            <span className="acoustic-desc-label">{d.label}:</span>
            <span className="acoustic-desc-value">{d.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default EmotionRadar;
