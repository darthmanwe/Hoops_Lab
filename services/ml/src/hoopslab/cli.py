"""Command line entry point.

Commands appear here only once they do something real. A CLI that advertises
``train`` before any model exists is the same category of overclaim as an API
that serves hand-written constants.
"""

from __future__ import annotations

import contextlib
import json
import sys

import typer
from rich.console import Console

from hoopslab import __version__
from hoopslab.config import load_settings
from hoopslab.paths import DataPaths


def _force_utf8_stdout() -> None:
    """Make console output survive a non-UTF-8 Windows code page.

    Python defaults stdout to the legacy ANSI code page on Windows, which is
    cp1252 here. Any table polars renders uses box-drawing characters, and any
    EuroLeague player name uses diacritics, so printing either raises
    UnicodeEncodeError and takes down a run that had already succeeded.
    Replacing unencodable characters is strictly better than losing the output.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            # Not every stream is reconfigurable (a pipe under some
            # runners is not); failing to improve output must never be
            # what breaks a run.
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


_force_utf8_stdout()

app = typer.Typer(
    name="hoopslab",
    help="HoopsLab data and modelling pipeline.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


@app.command()
def version() -> None:
    """Print the package version."""
    console.print(__version__)


@app.command()
def config() -> None:
    """Show the resolved configuration, with secrets redacted."""
    settings = load_settings()
    resolved = settings.model_dump()
    resolved["anthropic_api_key"] = "<set>" if settings.anthropic_api_key else None

    console.print_json(json.dumps(resolved, indent=2, default=str))


@app.command()
def ingest(
    refresh: bool = typer.Option(
        False, "--refresh", help="Refetch even when a payload is already cached."
    ),
    skip_nba: bool = typer.Option(False, "--skip-nba", help="Skip stats.nba.com."),
    skip_euroleague: bool = typer.Option(False, "--skip-euroleague"),
    skip_espn: bool = typer.Option(False, "--skip-espn"),
) -> None:
    """Fetch raw source payloads into the bronze layer.

    Operator-only, and not needed to reproduce any reported result: gold is
    committed, so a clean clone verifies and trains with no network at all.
    This exists to refresh that snapshot.

    stats.nba.com refuses datacenter IP ranges, so this cannot run in CI.
    """
    import logging

    from hoopslab.ingest.run import run_ingest, summarise

    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(message)s")

    paths = DataPaths.discover()
    console.print(f"[bold]Ingesting into[/bold] {paths.bronze}")
    console.print(f"Rate limit: {settings.nba_stats_rate_limit_rps} req/s\n")

    report = run_ingest(
        paths,
        settings,
        refresh=refresh,
        include_nba=not skip_nba,
        include_euroleague=not skip_euroleague,
        include_espn=not skip_espn,
    )

    console.print("\n" + summarise(report))
    if not report.succeeded:
        raise typer.Exit(code=1)


@app.command()
def build(
    write_contracts: bool = typer.Option(
        True, "--contracts/--no-contracts", help="Regenerate the contract sidecars."
    ),
) -> None:
    """Build silver and gold from cached bronze payloads.

    Runs entirely offline. Nothing here touches a data source, so the transform
    logic can be changed and re-run freely.
    """
    import logging

    from hoopslab.transform.build import build_gold, write_gold

    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(message)s")

    paths = DataPaths.discover()
    result = build_gold(paths)

    console.print("\n[bold]Identity resolution[/bold]")
    console.print(result.id_space.render())
    console.print(result.crosswalk_report.render())

    write_gold(result, paths, write_contracts=write_contracts)

    console.print("\n[bold]Gold tables[/bold]")
    for name, count in result.row_counts().items():
        console.print(f"  {name:<20} {count:>8,} rows")

    from hoopslab.transform.gold import summarise_pairs

    pairs = summarise_pairs(result.tables["transition_pairs"])
    console.print("\n[bold]Transition pairs by direction[/bold]")
    console.print(pairs)


@app.command()
def train(
    verify_only: bool = typer.Option(
        False,
        "--verify",
        help="Refit and fail if any metric differs from the committed run log.",
    ),
) -> None:
    """Fit the translation model, backtest it, and record the run.

    Runs offline against committed gold. With ``--verify`` nothing is written:
    the model is refitted and every reported metric is compared to the
    committed run log, so CI can prove the numbers in the README on each push.
    """
    import logging

    from hoopslab.models.train import (
        compare_to_committed,
        latest_run,
        train_all,
        write_run,
    )

    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(message)s")

    paths = DataPaths.discover()
    run, results = train_all(paths, seed=settings.seed)

    console.print(f"[bold]{run.model_version}[/bold]  seed={run.seed}  git={run.git_sha}")
    for result in results:
        console.print(result.render())

    console.print("\n[bold]Selection: how far above their league the movers sat[/bold]")
    console.print(
        "  Positive means the cohort was better than its peers, so the estimate is "
        "conditional on having been\n  selected to move. The two headline directions "
        "are selected oppositely, which is what makes this measurable."
    )
    for row in run.selection:
        console.print(
            f"  {row['direction']:<9} {row['metric']:<8} "
            f"n={row['n_movers']:<4} vs {row['n_league']:<5} peers   "
            f"gap {row['gap_sd']:+.2f} sd"
        )

    if verify_only:
        committed = latest_run(paths)
        if committed is None:
            console.print("[red]No committed run log to verify against.[/red]")
            raise typer.Exit(code=1)

        problems = compare_to_committed(results, committed)
        if problems:
            console.print("\n[red]Metrics differ from the committed run:[/red]")
            for problem in problems:
                console.print(f"  {problem}")
            raise typer.Exit(code=1)

        console.print("\n[green]Committed metrics reproduce exactly.[/green]")
        return

    if run.git_dirty:
        # A run from an uncommitted tree cannot be traced back to anything, so
        # it is written but must not be quoted as a result.
        console.print(
            "\n[yellow]Working tree is dirty; this run is not reproducible "
            "and must not be quoted.[/yellow]"
        )

    console.print(f"\nwrote {write_run(run, paths).name}")


@app.command()
def export(
    demo: bool = typer.Option(
        False,
        "--demo",
        help="Write the smaller slice a free-tier D1 deployment can hold.",
    ),
) -> None:
    """Build the SQL artefact that loads D1.

    Only aggregates are exported. Raw event data stays in parquet: the free
    tier caps a database at 500 MB and row writes at 100,000 a day.

    ``--demo`` writes `load-demo.sql` instead, holding the model cohort in full
    plus recent seasons. The full export is 199,439 rows against that same
    100,000-a-day ceiling, so a hosted deployment has to choose which rows it
    serves; see :class:`hoopslab.serve.d1_export.DemoSlice` for what it keeps
    and why dropping old seasons wholesale would break the front page.
    """
    import logging

    from hoopslab.serve.d1_export import (
        D1_FREE_DAILY_WRITES,
        D1_INDEX_WRITE_MULTIPLIER,
        build_export,
    )

    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(message)s")

    result = build_export(DataPaths.discover(), demo=demo)
    console.print(result.render())

    if demo:
        console.print()
        # The insert count is not what D1 charges for. Each row written to an
        # indexed table is also a write to every index on it, measured at 3.28x
        # on this schema, so quoting the insert count against the daily ceiling
        # reports headroom that is not there — which is exactly what this did
        # until a production seed of 48,423 rows came back billed at 158,890.
        billed = round(result.total * D1_INDEX_WRITE_MULTIPLIER)
        console.print(
            f"  {result.total:,} rows inserted, about {billed:,} billed once "
            f"index writes are counted,\n  against a documented free-tier "
            f"allowance of {D1_FREE_DAILY_WRITES:,} a day."
        )
        if result.total > D1_FREE_DAILY_WRITES:
            # Past this the file is unloadable on any reading of the limit, and
            # would seed most of the way before failing, leaving the database
            # half-populated with no obvious sign of which half.
            console.print(
                f"\n[red]{result.total:,} inserts exceeds the allowance outright. "
                "Tighten DEMO_RECENT_SEASON or DEMO_COMPS_PER_SEASON.[/red]"
            )
            raise typer.Exit(code=1)
        if billed > D1_FREE_DAILY_WRITES:
            # A warning and not an error, deliberately: a slice this size has
            # loaded, so failing the build would assert a limit this repository
            # has not actually observed being enforced.
            console.print(
                "[yellow]  The billed estimate is over the allowance. It has "
                "loaded at this size, so where\n  the wall really sits is "
                "unverified — treat a re-seed as something to plan, not "
                "repeat.[/yellow]"
            )

    # Naming the wrong script here is worse than saying nothing: both files sit
    # in data/d1/ and both load without complaint, so following the hint after a
    # `--demo` export seeds the full snapshot and blows the daily write budget
    # before anyone notices which one ran.
    script = "db:load:demo" if demo else "db:load"
    console.print(f"\n[dim]Apply locally with `npm run {script}`.[/dim]")


@app.command()
def fixture() -> None:
    """Write the deterministic test fixture used by the Worker suite."""
    from hoopslab.serve.d1_export import build_fixture

    paths = DataPaths.discover()
    target = paths.root / "apps" / "api" / "test" / "fixtures" / "seed.sql"
    counts = build_fixture(paths, target)

    console.print(f"wrote {target.relative_to(paths.root)}")
    for table, n in counts.items():
        console.print(f"  {table:<26} {n:>6,} rows")


@app.command()
def report(
    person_id: str = typer.Argument(..., help="Person id of a player who changed league."),
    season: str = typer.Option(
        None, "--season", help="Target season id, e.g. NBA_2018. Defaults to the earliest move."
    ),
    named: bool = typer.Option(
        False,
        "--named",
        help="Include the real name. Groundedness is not independently verifiable in this mode.",
    ),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Permit billed API calls to fill cache misses."
    ),
    max_calls: int = typer.Option(1, "--max-calls", help="Hard ceiling on billed calls."),
) -> None:
    """Write, or replay, one grounded scouting report.

    Costs nothing by default: the response cache is committed, so a cache hit
    needs neither a key nor a network. A miss without ``--refresh-cache`` is an
    error rather than a silent charge.
    """
    from hoopslab.llm.cache import ResponseCache
    from hoopslab.llm.client import CacheMiss, ReportGenerator
    from hoopslab.llm.evidence import BundleSource, actual_outcome, build_bundle
    from hoopslab.llm.groundedness import check_report

    paths = DataPaths.discover()
    source = BundleSource.load(paths)

    target = season or _first_transition(source, person_id)
    bundle = build_bundle(source, person_id, target, anonymized=not named)

    generator = ReportGenerator(
        ResponseCache(paths.llm_cache),
        allow_api=refresh_cache,
        max_calls=max_calls if refresh_cache else 0,
    )

    try:
        cached = generator.generate(bundle)
    except CacheMiss as exc:
        console.print(f"[yellow]{exc}[/yellow]")
        raise typer.Exit(code=1) from exc

    grounded = check_report(cached.report, bundle)

    console.print(f"[bold]{cached.report.headline}[/bold]\n")
    for label, claim in (
        ("Projection", cached.report.projection),
        ("Uncertainty", cached.report.uncertainty),
    ):
        console.print(f"[bold]{label}[/bold]  {claim.text}")
        console.print(f"  [dim]{' '.join(claim.fact_ids)}[/dim]")
    for heading, claims in (("Strengths", cached.report.strengths), ("Risks", cached.report.risks)):
        console.print(f"\n[bold]{heading}[/bold]")
        for claim in claims:
            console.print(f"  - {claim.text}")
            console.print(f"    [dim]{' '.join(claim.fact_ids)}[/dim]")

    console.print(f"\nconfidence: {cached.report.confidence}")
    console.print(f"[bold]{grounded.provenance()}[/bold]")
    for check in grounded.checks:
        console.print(check.render())

    # Held back from the bundle on purpose, so the report was written blind to
    # it. Showing it here is the same move the model page makes: the claim and
    # the check side by side.
    outcome = actual_outcome(source, person_id, target)
    if outcome:
        console.print("\n[bold]What actually happened[/bold] (never shown to the model)")
        for metric, value in outcome.items():
            console.print(f"  {metric:<10} {value:.3f}")

    console.print("\n" + generator.ledger.render())


@app.command(name="report-eval")
def report_eval(
    per_direction: int = typer.Option(10, "--per-direction", help="Reports per move direction."),
    named: bool = typer.Option(False, "--named", help="Evaluate without redacting the subject."),
    refresh_cache: bool = typer.Option(
        False, "--refresh-cache", help="Permit billed API calls to fill cache misses."
    ),
    max_calls: int = typer.Option(0, "--max-calls", help="Hard ceiling on billed calls."),
) -> None:
    """Score every report in the eval set for groundedness.

    Deterministic and offline. The distractor line is the one to read first: a
    groundedness rate means nothing unless swapping in another player's
    evidence makes the same checks fail.
    """
    from hoopslab.llm.harness import run_harness

    paths = DataPaths.discover()
    result = run_harness(
        paths,
        anonymized=not named,
        per_direction=per_direction,
        allow_api=refresh_cache,
        max_calls=max_calls if refresh_cache else 0,
    )

    console.print(result.render())
    if not result.records:
        console.print(
            "\n[yellow]Nothing to score.[/yellow] Populate the response cache with "
            "`hoopslab report-eval --refresh-cache --max-calls 30` and a key set."
        )
        raise typer.Exit(code=1)


@app.command(name="report-prune")
def report_prune(
    delete: bool = typer.Option(False, "--delete", help="Actually remove the stale responses."),
) -> None:
    """List, or remove, cached reports whose evidence has since changed.

    A committed response cache is an asset until the data moves underneath it,
    at which point it holds confident prose about numbers that are no longer
    true. The export already refuses to serve those; this is what stops them
    accumulating on disk where someone might read one and believe it.
    """
    from hoopslab.llm.cache import ResponseCache
    from hoopslab.llm.client import ReportGenerator
    from hoopslab.llm.evidence import BundleSource, build_bundle

    paths = DataPaths.discover()
    cache = ResponseCache(paths.llm_cache)
    if len(cache) == 0:
        console.print("Cache is empty.")
        return

    source = BundleSource.load(paths)
    generator = ReportGenerator(cache)

    live: dict[str, str] = {}
    for entry in cache.entries():
        try:
            bundle = build_bundle(
                source, entry.person_id, entry.target_season_id, anonymized=entry.anonymized
            )
        except KeyError:
            continue
        live[generator.key_for(bundle)] = bundle.digest()

    stale = cache.prune(live, dry_run=not delete)
    if not stale:
        console.print(f"[green]All {len(cache)} cached responses match current evidence.[/green]")
        return

    verb = "removed" if delete else "stale (re-run with --delete)"
    console.print(f"[yellow]{len(stale)} {verb}[/yellow]")
    for entry in stale:
        console.print(f"  {entry.key}  {entry.person_id} -> {entry.target_season_id}")


def _first_transition(source: object, person_id: str) -> str:
    """The earliest scored move for a person, so --season is optional."""
    matches = [key for key in source.transitions() if key[0] == person_id]  # type: ignore[attr-defined]
    if not matches:
        raise typer.BadParameter(
            f"{person_id} has no scored league transition. Only observed moves clearing "
            "the minutes floor have a projection."
        )
    return sorted(matches)[0][1]


@app.command()
def verify() -> None:
    """Check committed gold against its contracts and integrity rules.

    Runs with no network access, so it works on a fresh clone and in CI. Exits
    non-zero when a table's contents no longer match the checksums committed
    alongside it, making silent data drift a failed build rather than a quietly
    changed number in the README.
    """
    import polars as pl

    from hoopslab.transform.build import GOLD_TABLES, verify_gold
    from hoopslab.validate import checks

    paths = DataPaths.discover()

    if not paths.gold.is_dir():
        console.print(
            "[yellow]No gold data yet.[/yellow] Run `hoopslab ingest` then `hoopslab build`."
        )
        raise typer.Exit(code=1)

    console.print("[bold]Contracts[/bold]")
    problems = verify_gold(paths)
    if problems:
        for problem in problems:
            console.print(f"  [red]{problem}[/red]")
    else:
        console.print("  all tables match their committed contracts")

    tables = {
        name: pl.read_parquet(paths.gold / f"{name}.parquet")
        for name in GOLD_TABLES
        if (paths.gold / f"{name}.parquet").is_file()
    }

    console.print("\n[bold]Integrity[/bold]")
    results = checks.run_all(tables) if len(tables) == len(GOLD_TABLES) else []
    for result in results:
        colour = "green" if result.passed else "red"
        console.print(f"  [{colour}]{result.render()}[/{colour}]")

    failed = [r for r in results if not r.passed]
    if problems or failed:
        console.print(
            f"\n[red]{len(problems)} contract differences, {len(failed)} failed checks[/red]"
        )
        raise typer.Exit(code=1)

    console.print("\n[green]Gold data verified.[/green]")


if __name__ == "__main__":  # pragma: no cover
    app()
