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
