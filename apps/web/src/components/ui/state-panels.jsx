export function LoadingPanel({ text = "Loading analytics..." }) {
  return (
    <div className="glass flex min-h-[160px] items-center justify-center p-6">
      <p className="text-sm text-slate-300">{text}</p>
    </div>
  );
}

export function EmptyPanel({ title, description }) {
  return (
    <div className="glass min-h-[160px] p-6">
      <h3 className="text-base font-semibold text-white">{title}</h3>
      <p className="mt-2 text-sm text-slate-300">{description}</p>
    </div>
  );
}

export function ErrorPanel({ error }) {
  return (
    <div className="glass border-red-400/40 bg-red-900/20 p-4">
      <p className="text-sm font-medium text-red-200">Could not load data</p>
      <p className="mt-1 text-xs text-red-100/80">{error || "Unknown error"}</p>
    </div>
  );
}
