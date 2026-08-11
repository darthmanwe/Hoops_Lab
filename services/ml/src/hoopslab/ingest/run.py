"""Orchestrates a full bronze-layer pull.

Cost, at the configured 0.67 requests per second:

| Source                       | Requests | Notes                          |
|------------------------------|----------|--------------------------------|
| NBA player stats (2 measures)| 50       | 25 seasons                     |
| NBA team stats (2 measures)  | 50       |                                |
| NBA player bio               | 25       | replaces ~3,000 per-player calls |
| NBA registry                 | 1        | all players, all time          |
| G League player stats        | 20       | 10 seasons, 2 measures         |
| EuroLeague player stats      | 18       |                                |
| EuroLeague team stats        | 18       |                                |
| ESPN bulk files              | 24       | not rate limited               |

Roughly 180 requests against rate-limited hosts: about five minutes, not the
hour the per-player bio route would have cost.

Everything is cached content-addressed, so re-running is free and an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from hoopslab.config import Settings
from hoopslab.ingest.espn_mirror import DATASETS, ESPNMirrorClient
from hoopslab.ingest.euroleague import EuroLeagueClient
from hoopslab.ingest.nba_stats import NBAStatsClient
from hoopslab.io.bronze import BronzeCache
from hoopslab.io.rate_limit import RateLimiter
from hoopslab.paths import DataPaths
from hoopslab.seasons import seasons_for

log = logging.getLogger(__name__)


@dataclass
class IngestReport:
    """What a run actually did. Printed, and useful when a source misbehaves."""

    fetched: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def ok(self, what: str) -> None:
        self.fetched.append(what)

    def error(self, what: str, why: str) -> None:
        self.failed.append((what, why))
        log.error("ingest failed for %s: %s", what, why)

    @property
    def succeeded(self) -> bool:
        return not self.failed


def run_ingest(
    paths: DataPaths,
    settings: Settings,
    *,
    refresh: bool = False,
    include_espn: bool = True,
    include_nba: bool = True,
    include_euroleague: bool = True,
) -> IngestReport:
    """Populate bronze from every configured source."""
    cache = BronzeCache(paths.bronze)
    limiter = RateLimiter(settings.nba_stats_rate_limit_rps)
    report = IngestReport()

    if include_nba:
        _ingest_nba(NBAStatsClient(cache, limiter), report, refresh=refresh)

    if include_euroleague:
        # A separate limiter: the EuroLeague live API is a different host with
        # its own budget, and it returned 429 during probing.
        el_limiter = RateLimiter(settings.nba_stats_rate_limit_rps)
        _ingest_euroleague(EuroLeagueClient(cache, el_limiter), report, refresh=refresh)

    if include_espn:
        _ingest_espn(ESPNMirrorClient(cache), report, refresh=refresh)

    return report


def _guard(report: IngestReport, what: str, call) -> None:  # type: ignore[no-untyped-def]
    """Run one fetch, recording success or failure without ending the run.

    One unavailable season must not cost the other two hundred requests, but it
    also must not pass silently — every failure lands in the report and the
    caller exits non-zero.
    """
    try:
        call()
        report.ok(what)
    except Exception as exc:
        report.error(what, f"{type(exc).__name__}: {exc}")


def _ingest_nba(client: NBAStatsClient, report: IngestReport, *, refresh: bool) -> None:
    nba_seasons = seasons_for("NBA")
    latest = nba_seasons[-1]

    _guard(
        report,
        "nba/player_registry",
        lambda: client.player_registry(latest, refresh=refresh),
    )

    for season in nba_seasons:
        for measure in ("Base", "Advanced"):
            _guard(
                report,
                f"nba/player_season_stats/{season.season_id}/{measure}",
                lambda s=season, m=measure: client.player_season_stats(s, m, refresh=refresh),
            )
            _guard(
                report,
                f"nba/team_season_stats/{season.season_id}/{measure}",
                lambda s=season, m=measure: client.team_season_stats(s, m, refresh=refresh),
            )
        _guard(
            report,
            f"nba/player_bio_stats/{season.season_id}",
            lambda s=season: client.player_bio_stats(s, refresh=refresh),
        )

    for season in seasons_for("GL"):
        for measure in ("Base", "Advanced"):
            _guard(
                report,
                f"gl/player_season_stats/{season.season_id}/{measure}",
                lambda s=season, m=measure: client.player_season_stats(s, m, refresh=refresh),
            )


def _ingest_euroleague(client: EuroLeagueClient, report: IngestReport, *, refresh: bool) -> None:
    for season in seasons_for("EL"):
        _guard(
            report,
            f"el/player_season_stats/{season.season_id}",
            lambda s=season: client.player_season_stats(s, refresh=refresh),
        )
        _guard(
            report,
            f"el/team_season_stats/{season.season_id}",
            lambda s=season: client.team_season_stats(s, refresh=refresh),
        )


def _ingest_espn(client: ESPNMirrorClient, report: IngestReport, *, refresh: bool) -> None:
    for season in seasons_for("NBA", game_grain=True):
        for dataset in DATASETS:
            _guard(
                report,
                f"espn/{dataset}/{season.season_id}",
                lambda d=dataset, s=season: client.season_file(d, s, refresh=refresh),
            )


def summarise(report: IngestReport) -> str:
    lines = [f"fetched {len(report.fetched)} payloads"]
    if report.failed:
        lines.append(f"FAILED {len(report.failed)}:")
        lines.extend(f"  {what}: {why}" for what, why in report.failed[:20])
        if len(report.failed) > 20:
            lines.append(f"  ... and {len(report.failed) - 20} more")
    return "\n".join(lines)
