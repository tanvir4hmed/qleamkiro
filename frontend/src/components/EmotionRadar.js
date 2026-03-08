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

function EmotionRadar({ emotionScores, primaryEmotion }) {
  if (!emotionScores || Object.keys(emotionScores).length === 0) return null;

  const data = EMOTION_ORDER.map((key) => ({
    emotion: EMOTION_LABELS[key] || key,
    score: Math.round((emotionScores[key] || 0) * 100),
    key,
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
    </div>
  );
}

export default EmotionRadar;
