"""Command line entry point.

Commands appear here only once they do something real. A CLI that advertises
``train`` before any model exists is the same category of overclaim as an API
that serves hand-written constants.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console

from hoopslab import __version__
from hoopslab.config import load_settings
from hoopslab.paths import DataPaths

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
def verify() -> None:
    """Check committed gold data against its contract sidecars.

    Exits non-zero when a table's contents no longer match the checksums that
    were committed alongside it, so silent data drift becomes a failed build
    rather than a quietly changed number in the README.
    """
    paths = DataPaths.discover()

    if not paths.gold.is_dir():
        console.print(
            "[yellow]No gold data yet.[/yellow] Ingestion lands in phase 1; "
            "until then there is nothing to verify and nothing is served."
        )
        raise typer.Exit(code=0)

    contracts = sorted(paths.contracts.glob("*.json")) if paths.contracts.is_dir() else []
    if not contracts:
        console.print(
            f"[red]Gold data exists at {paths.gold} but has no contract sidecars.[/red]\n"
            "Every gold table must ship a contract; regenerate with `hoopslab contracts write`."
        )
        raise typer.Exit(code=1)

    # Contract comparison arrives with the ingestion pipeline in phase 1.
    raise NotImplementedError(
        "Contract verification is implemented alongside the phase 1 ingestion pipeline."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
