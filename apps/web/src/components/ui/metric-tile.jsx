import { cn } from "../../lib/cn";

export function MetricTile({ label, value, hint, className }) {
  return (
    <div className={cn("rounded-xl border border-white/15 bg-black/25 p-3", className)}>
      <p className="text-xs uppercase tracking-wide text-slate-300">{label}</p>
      <p className="metric-value mt-1">{value}</p>
      {hint ? <p className="mt-1 text-xs text-slate-400">{hint}</p> : null}
    </div>
  );
}
