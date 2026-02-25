"use client";

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

export function MetricBarChart({ data, xKey, bars, height = 260 }) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 8 }}>
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
          {bars.map((bar) => (
            <Bar key={bar.key} dataKey={bar.key} fill={bar.color} radius={[6, 6, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
