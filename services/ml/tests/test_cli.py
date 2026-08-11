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


def test_verify_exits_cleanly_when_there_is_no_gold_data_yet() -> None:
    """Phase 0 ships no data. Saying so plainly beats inventing a green check."""
    result = runner.invoke(app, ["verify"])

    assert result.exit_code == 0
    assert "phase 1" in result.stdout.lower()


def test_cli_exposes_no_modelling_commands_yet() -> None:
    """Guards against advertising `train`/`predict` before a model exists."""
    result = runner.invoke(app, ["--help"])

    for unimplemented in ("train", "predict", "backtest", "ingest"):
        assert unimplemented not in result.stdout
