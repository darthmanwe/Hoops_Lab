"use client";

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
} from "recharts";

export function MetricRadarChart({ data, dataKey = "value", height = 300 }) {
  return (
    <div className="h-[300px] w-full">
      <ResponsiveContainer width="100%" height={height}>
        <RadarChart data={data}>
          <PolarGrid stroke="rgba(148,163,184,0.35)" />
          <PolarAngleAxis dataKey="metric" tick={{ fill: "#cbd5e1", fontSize: 12 }} />
          <PolarRadiusAxis tick={{ fill: "#94a3b8", fontSize: 10 }} />
          <Radar
            name="Lineup"
            dataKey={dataKey}
            stroke="#5ba0ff"
            fill="#5ba0ff"
            fillOpacity={0.35}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
