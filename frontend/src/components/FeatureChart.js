import React from 'react';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts';

function FeatureChart({ features }) {
  const data = [
    { feature: 'Rhythm', value: Math.round((features.rhythm || 0) * 100) },
    { feature: 'Repetition', value: Math.round((features.repetition || 0) * 100) },
    { feature: 'Intensity', value: Math.round((features.emotional_intensity || 0) * 100) },
    { feature: 'Flow', value: Math.round((features.expressive_flow || 0) * 100) },
  ];

  return (
    <div className="feature-chart">
      <ResponsiveContainer width="100%" height={220}>
        <RadarChart data={data}>
          <PolarGrid stroke="#e0e0e0" />
          <PolarAngleAxis dataKey="feature" tick={{ fontSize: 12, fill: '#555' }} />
          <Radar name="Score" dataKey="value" stroke="#4ECDC4" fill="#4ECDC4" fillOpacity={0.35} />
          <Tooltip formatter={(v) => `${v}%`} />
        </RadarChart>
      </ResponsiveContainer>
      <div className="feature-scores-row">
        {data.map(d => (
          <div key={d.feature} className="feature-score-item">
            <span className="fs-label">{d.feature}</span>
            <span className="fs-value">{d.value}%</span>
          </div>
        ))}
      </div>
      {features.deviation && features.deviation !== 'none' && (
        <div className={`deviation-badge deviation-${features.deviation}`}>
          ⚠ Pattern deviation: {features.deviation}
        </div>
      )}
    </div>
  );
}

export default FeatureChart;
