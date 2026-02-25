"use client";

export function SearchInput({ value, onChange, placeholder, className = "" }) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full rounded-lg border border-white/15 bg-black/25 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-400 focus:border-neon-400 ${className}`}
    />
  );
}
