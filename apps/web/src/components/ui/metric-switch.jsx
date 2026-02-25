import { cn } from "../../lib/cn";

export function MetricSwitch({ options, value, onChange, className }) {
  return (
    <div className={cn("inline-flex rounded-lg border border-white/15 bg-black/20 p-1", className)}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded-md px-3 py-1.5 text-xs font-medium transition",
              active ? "bg-neon-500 text-white" : "text-slate-300 hover:bg-white/10"
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
