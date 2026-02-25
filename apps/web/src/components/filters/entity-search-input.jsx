"use client";

import { useEffect, useId, useMemo, useState } from "react";
import { apiGet } from "../../lib/api";

function endpointForType(type) {
  if (type === "team") return "/teams/search";
  return "/players/search";
}

function formatOptionLabel(type, row) {
  if (type === "team") {
    const suffix = [row.abbrev, row.league_id].filter(Boolean).join(" · ");
    return `${row.name}${suffix ? ` (${suffix})` : ""}`;
  }
  const suffix = [row.position, row.league_id].filter(Boolean).join(" · ");
  return `${row.name}${suffix ? ` (${suffix})` : ""}`;
}

export function EntitySearchInput({
  value,
  onChange,
  placeholder,
  type = "player",
  className = "",
}) {
  const listId = useId().replace(/:/g, "_");
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  const query = value.trim();
  useEffect(() => {
    let cancelled = false;
    if (query.length < 2) {
      setResults([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const handle = setTimeout(async () => {
      try {
        const endpoint = endpointForType(type);
        const response = await apiGet(`${endpoint}?q=${encodeURIComponent(query)}`);
        if (!cancelled) setResults(response?.results ?? []);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }, 220);

    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [query, type]);

  const helperText = useMemo(() => {
    if (query.length < 2) return "Type at least 2 characters";
    if (loading) return "Searching...";
    if (results.length === 0) return "No matches";
    return `${results.length} match${results.length === 1 ? "" : "es"}`;
  }, [loading, query.length, results.length]);

  return (
    <div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        list={listId}
        className={`w-full rounded-lg border border-white/15 bg-black/25 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-400 focus:border-neon-400 ${className}`}
      />
      <datalist id={listId}>
        {results.map((row) => {
          const idValue = type === "team" ? row.team_id : row.player_id;
          return <option key={idValue} value={idValue} label={formatOptionLabel(type, row)} />;
        })}
      </datalist>
      <p className="mt-1 text-xs text-slate-400">{helperText}</p>
    </div>
  );
}
