import { cn } from "../../lib/cn";

export function Button({ className, variant = "primary", children, ...props }) {
  const variants = {
    primary:
      "bg-neon-500 hover:bg-neon-400 text-white border border-neon-300/40",
    secondary:
      "bg-white/10 hover:bg-white/15 text-slate-100 border border-white/20",
    ghost:
      "bg-transparent hover:bg-white/10 text-slate-100 border border-white/10",
    court:
      "bg-court-500 hover:bg-court-400 text-ink-950 border border-court-300/40",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-lg px-3 py-2 text-sm font-medium transition-all disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}
