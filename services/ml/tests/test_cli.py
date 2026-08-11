"""CLI surface.

The point of these is less "does typer work" than "does the CLI advertise only
what exists". A command that prints a plausible number before the model behind
it has been fitted is the failure mode this whole rebuild exists to remove.
"""

from __future__ import annotations

import json

from typer.testing import CliRunner

from hoopslab import __version__
from hoopslab.cli import app

runner = CliRunner()


def test_version_matches_the_package() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_bare_invocation_shows_help_rather_than_failing() -> None:
    result = runner.invoke(app, [])

    assert "Usage" in result.stdout


def test_config_redacts_the_api_key(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret-value")

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "sk-ant-secret-value" not in result.stdout
    assert "<set>" in result.stdout


def test_config_emits_valid_json() -> None:
    result = runner.invoke(app, ["config"])

    assert json.loads(result.stdout)["seed"] == 20260810


def test_verify_passes_against_the_committed_snapshot() -> None:
    """Gold is committed, so verification works on a clean clone with no network."""
    result = runner.invoke(app, ["verify"])

    assert result.exit_code == 0, result.stdout
    assert "verified" in result.stdout.lower()


def test_cli_advertises_only_commands_that_do_something() -> None:
    """A command appears here only once it is real.

    `train` joined the list in phase 2, when a model existed to fit. `predict`
    and `serve` have not, because nothing behind them is built yet — and a CLI
    that advertises them would be the same overclaim as an API returning
    hand-written constants.
    """
    result = runner.invoke(app, ["--help"])

    for implemented in ("ingest", "build", "verify", "train"):
        assert implemented in result.stdout

    for unimplemented in ("predict", "serve", "export"):
        assert unimplemented not in result.stdout
