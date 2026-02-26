export const SEASON_OPTIONS = [
  { value: "NBA_2025", league: "NBA", label: "NBA 2025-2026" },
  { value: "EL_2025", league: "EL", label: "EuroLeague 2025-2026" },
];

export const DEFAULT_SEASON_BY_LEAGUE = {
  NBA: "NBA_2025",
  EL: "EL_2025",
};

export function seasonLabel(value) {
  const match = SEASON_OPTIONS.find((option) => option.value === value);
  return match?.label ?? value;
}

export function seasonsForLeague(league) {
  return SEASON_OPTIONS.filter((option) => option.league === league);
}

export function leagueFromSeason(season) {
  if (!season) return "NBA";
  if (season.startsWith("EL_")) return "EL";
  return "NBA";
}
