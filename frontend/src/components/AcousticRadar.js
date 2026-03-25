import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip,
} from 'recharts';

const FEATURE_CONFIG = [
  { key: 'pitch_normalized', label: 'Pitch', unit: 'Hz', rawKey: 'pitch_hz' },
  { key: 'energy_normalized', label: 'Energy' },
  { key: 'stability_normalized', label: 'Stability' },
  { key: 'voicing_pct', label: 'Voicing', unit: '%' },
  { key: 'brightness_normalized', label: 'Brightness' },
  { key: 'variation_normalized', label: 'Variation' },
];

function describeFeature(key, value, acousticFeatures) {
  switch (key) {
    case 'pitch_normalized': {
      const hz = acousticFeatures?.pitch_hz || 0;
      if (hz > 500) return `${Math.round(hz)} Hz (high-pitched cry)`;
      if (hz > 300) return `${Math.round(hz)} Hz (typical cry range)`;
      return `${Math.round(hz)} Hz (low pitch)`;
    }
    case 'energy_normalized':
      if (value > 70) return 'strong, intense';
      if (value > 40) return 'moderate, rhythmic';
      return 'gentle, soft';
    case 'stability_normalized':
      if (value > 70) return 'steady (consistent pitch)';
      if (value > 40) return 'some variation';
      return 'erratic (unstable pitch)';
    case 'voicing_pct':
      if (value > 80) return `${value}% voiced (sustained)`;
      if (value > 50) return `${value}% voiced (intermittent)`;
      return `${value}% voiced (mostly silent)`;
    case 'brightness_normalized':
      if (value > 60) return 'bright, sharp tone';
      if (value > 30) return 'moderate tone';
      return 'muffled, low tone';
    case 'variation_normalized':
      if (value > 60) return 'highly variable (waves)';
      if (value > 30) return 'moderate variation';
      return 'consistent energy';
    default:
      return `${value}/100`;
  }
}

function AcousticRadar({ acousticFeatures }) {
  if (!acousticFeatures) return null;

  const data = FEATURE_CONFIG.map((f) => ({
    feature: f.label,
    value: acousticFeatures[f.key] || 0,
    key: f.key,
  }));

  const descriptions = FEATURE_CONFIG.map((f) => ({
    label: f.label,
    desc: describeFeature(f.key, acousticFeatures[f.key] || 0, acousticFeatures),
  }));

  return (
    <div className="radar-chart-container">
      <h4 className="radar-title">Acoustic Analysis</h4>
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
          <PolarGrid stroke="var(--border)" />
          <PolarAngleAxis
            dataKey="feature"
            tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 100]}
            tick={false}
            axisLine={false}
          />
          <Radar
            dataKey="value"
            stroke="#4ECDC4"
            fill="#4ECDC4"
            fillOpacity={0.2}
            strokeWidth={2}
          />
          <Tooltip
            formatter={(value) => [`${value}/100`, 'Level']}
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
            <span className="acoustic-desc-value">{d.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default AcousticRadar;
