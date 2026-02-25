"use client";

import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

export function MetricLineChart({ data, xKey, lines, height = 260 }) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 8 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.09)" vertical={false} />
          <XAxis dataKey={xKey} stroke="#cbd5e1" tick={{ fontSize: 12 }} />
          <YAxis stroke="#cbd5e1" tick={{ fontSize: 12 }} />
          <Tooltip
            contentStyle={{
              background: "#020617",
              border: "1px solid rgba(148,163,184,0.25)",
              borderRadius: "10px",
            }}
          />
          {lines.map((line) => (
            <Line
              key={line.key}
              type="monotone"
              dataKey={line.key}
              stroke={line.color}
              strokeWidth={2.5}
              dot={{ r: 2 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
