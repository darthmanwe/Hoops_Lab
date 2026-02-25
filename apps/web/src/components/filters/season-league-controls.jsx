"use client";

import { Button } from "../ui/button";

const seasonByLeague = {
  NBA: "NBA_2025",
  EL: "EL_2025",
};

export function SeasonLeagueControls({
  league,
  setLeague,
  season,
  setSeason,
  className = "",
}) {
  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <div className="flex items-center gap-2 rounded-lg border border-white/15 bg-black/20 p-1">
        {["NBA", "EL"].map((option) => (
          <Button
            key={option}
            variant={league === option ? "primary" : "ghost"}
            className="px-2 py-1 text-xs"
            onClick={() => {
              setLeague(option);
              setSeason(seasonByLeague[option]);
            }}
          >
            {option}
          </Button>
        ))}
      </div>

      <label className="flex items-center gap-2 rounded-lg border border-white/15 bg-black/20 px-3 py-2">
        <span className="text-xs uppercase tracking-wide text-slate-300">Season</span>
        <input
          value={season}
          onChange={(e) => setSeason(e.target.value)}
          className="w-24 bg-transparent text-sm text-slate-100 outline-none"
        />
      </label>
    </div>
  );
}
