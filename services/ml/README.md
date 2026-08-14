# hoopslab — ML service

The data and modelling half of [HoopsLab](../../README.md). Everything the API
serves is produced here; the Cloudflare Worker reads precomputed columns and
performs no arithmetic of its own.

## Why the Worker does no modelling

Workers are capped at **10 ms of CPU per request** on the free tier. The
previous version computed player similarity by loading a whole season table
into Worker memory and sorting it in JavaScript — fine against the four
hardcoded players it shipped with, impossible against six hundred real ones.
Precomputing here and serving columns there removes the CPU problem and
eliminates train/serve skew by construction.

## Layout

| Package      | Responsibility                                                                                                   |
| ------------ | ---------------------------------------------------------------------------------------------------------------- |
| `ingest/`    | Fetch raw payloads into bronze. Operator-only: `stats.nba.com` refuses datacenter IPs, so this cannot run in CI. |
| `transform/` | Normalise bronze into typed silver, resolve identities, join to gold.                                            |
| `validate/`  | Data contracts that gold must satisfy, plus cross-file referential integrity.                                    |
| `features/`  | Model-ready frames. The single entry point for feature construction.                                             |
| `models/`    | Estimators, fitted and serialised with their metadata.                                                           |
| `eval/`      | Backtesting, runtime leakage assertions, calibration reporting.                                                  |
| `serve/`     | Export gold into the D1 tables the Worker reads.                                                                 |

## Data layers

```
data/bronze/   raw as returned          gitignored, regenerable
data/silver/   typed, per-league        gitignored, regenerable
data/gold/     analysis-ready           COMMITTED
```

Committing gold is deliberate and is the opposite of the usual arrangement. It
means a clean clone reproduces every number in the README **with no network
access at all**. `uv run hoopslab verify` re-derives each table's checksum and
diffs it against the committed contract, so silent data drift fails the build.

## Commands

```bash
uv sync --extra dev          # create the environment
uv run hoopslab --help       # only lists commands that do something
uv run pytest                # offline, no credentials, no billed calls
uv run ruff check .
uv run mypy
```

Tests are marker-gated (`net`, `llm`, `judge`, `slow`, `repro`) and all of
those are deselected by default. A bare `pytest` on a machine holding a real
API key still cannot spend money — `tests/conftest.py` clears the credential
environment _and_ disables `.env` loading, because `pydantic-settings` reads
the file in addition to the environment and clearing only one of the two is not
enough.

## Status

Phase 0. The package scaffolding, configuration and path handling are in place;
ingestion lands in phase 1 and the translation model in phase 2. No command
here reports a basketball number yet, because there is no data behind one.
