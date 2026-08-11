# Development

## Prerequisites

| Tool   | Version   | Notes                                          |
| ------ | --------- | ---------------------------------------------- |
| Node   | 22–24     | `.nvmrc` pins 24                               |
| npm    | 11+       | Ships with Node 24                             |
| uv     | 0.12+     | Replaces Poetry. `winget install astral-sh.uv` |
| Python | 3.11–3.13 | Let uv manage it: `uv python install 3.12`     |

`make` is **not** required. All tasks are root npm scripts; the `Makefile` is a
thin forwarder for people who prefer `make test`.

### Windows notes

The project is developed on Windows and CI keeps Windows in the matrix
deliberately, because path handling is the most likely thing to work locally
and break on Linux.

- **Do not rely on the Microsoft Store `python`.** It redirects `site-packages`
  into a sandboxed `LocalCache` directory and intermittently breaks editable
  installs. `uv python install 3.12` gives you a real interpreter, and
  `services/ml/.python-version` pins it.
- **Prefer a working copy outside OneDrive.** This repository currently lives
  in a synced folder; OneDrive slows `wrangler dev` file watching and can lock
  files mid-build.
- Enable long paths: `git config --global core.longpaths true`.

## Setup

```bash
npm ci                                  # one root lockfile covers both apps
cd services/ml && uv sync --extra dev   # Python environment
```

## Tasks

| Command                               | Does                                                         |
| ------------------------------------- | ------------------------------------------------------------ |
| `npm run lint`                        | ESLint across both apps                                      |
| `npm run format:check`                | Prettier                                                     |
| `npm run type`                        | `tsc --noEmit` for API and web                               |
| `npm run test`                        | Worker tests, inside workerd, with real D1 and KV bindings   |
| `npm run dev`                         | Worker on `127.0.0.1:8787`, bound to the **dev** environment |
| `npm run dev:web`                     | Next.js dev server                                           |
| `npm run ml:test`                     | Python tests — offline, no credentials                       |
| `npm run ml:lint` / `npm run ml:type` | ruff / mypy                                                  |

Smoke test the API:

```bash
curl http://127.0.0.1:8787/          # service listing, generated from the registry
curl http://127.0.0.1:8787/health    # probes D1 and KV for real
```

## Environments

`wrangler.toml` declares **no bindings at the top level**. Every binding lives
under `[env.dev]`, `[env.staging]` or `[env.production]`, so a bare
`wrangler deploy` fails loudly rather than silently writing to the production
database — which is what the previous single-binding configuration did.

Always pass `--env`:

```bash
npx wrangler dev --env dev
npx wrangler deploy --env production
```

## Tests

Worker tests run **inside workerd** via `@cloudflare/vitest-pool-workers`, with
real D1 and KV bindings rather than mocks, so SQLite semantics and runtime
limits are exercised for real. `remoteBindings` is explicitly disabled: it
defaults to `true` in 0.21, which would let the suite reach live Cloudflare
resources over the network.

Python tests are marker-gated. `net`, `llm`, `judge`, `slow` and `repro` are
all deselected by default, so a bare `pytest` cannot spend money or depend on a
third party. `tests/conftest.py` clears the credential environment **and**
disables `.env` loading — `pydantic-settings` reads the file in addition to the
environment, so clearing only one of the two is not enough.

## What is not here yet

Phase 0 has removed the fabricated data and built the foundations. There is no
ingestion, no model and no data. Every analytics endpoint returns `501` (coming
back) or `410` (permanently withdrawn), each with an explanation of what it
previously did. See the [roadmap](../README.md#roadmap).
