# Deployment

> Live at **<https://hoopslab-web.kutlumizrak.workers.dev>**, served by
> `hoopslab-api-production` over a D1 database holding a curated slice of the
> committed snapshot. `.github/workflows/deploy.yml` runs the sequence below
> after CI passes on `main`; the manual path and the traps in it are in
> [CLAUDE.md](../CLAUDE.md#deploying).
>
> Endpoints still marked `501` or `410` are the ones with no data or no honest
> metric behind them, which is a smaller set than it was: `/` lists every path
> and its state.

## Environments

Bindings are declared per environment in `apps/api/wrangler.toml`, with none at
the top level. `wrangler deploy` without `--env` therefore fails rather than
targeting production, which is what the previous configuration did silently.

| Environment  | D1                 | Purpose               |
| ------------ | ------------------ | --------------------- |
| `dev`        | local miniflare    | `wrangler dev`, tests |
| `staging`    | `hoopslab-staging` | Pull-request previews |
| `production` | `hoopslab-db`      | Live                  |

`hoopslab-dev` and `hoopslab-staging` are created in phase 3 alongside the
first real migrations; their ids are placeholders until then.

## Deploy the API

```bash
npm ci
npx wrangler deploy --env production --config apps/api/wrangler.toml
```

## Migrations

Phase 3 replaces `data/schema/schema.sql` with numbered migrations applied by
`wrangler d1 migrations apply`, which tracks what has been applied.

The current file is a single `CREATE TABLE IF NOT EXISTS` script. That is not a
migration system: re-running it after a schema change is a **silent no-op**, so
adding a column or a constraint to an existing table does nothing and reports
success. Do not add to it.

## Deploy the web app

> The committed Pages configuration does not work. `apps/web/wrangler.toml`
> points at `.vercel/output/static`, which is `@cloudflare/next-on-pages`
> output, but that package is not a dependency of this project and never was.
> Phase 5 migrates to `@opennextjs/cloudflare`; Cloudflare Pages is in
> maintenance mode and `next-on-pages` is the deprecated path.

Environment variable once the Worker is deployed:

```
NEXT_PUBLIC_API_BASE=https://hoopslab-api.<subdomain>.workers.dev
```

## GitHub Actions secrets

| Secret                  | Needed for                                                                                                |
| ----------------------- | --------------------------------------------------------------------------------------------------------- |
| `CLOUDFLARE_API_TOKEN`  | Deploys and D1 operations                                                                                 |
| `CLOUDFLARE_ACCOUNT_ID` | Same. The previous nightly workflow documented this as required and then omitted it from the job's `env`. |

`BALLDONTLIE_API_KEY` has been removed. It was threaded through
`.env.example`, `.dev.vars.example`, the Worker's `Env` type and the ETL
config, and **no code ever read it**.

## What is not automated

Nightly ingestion is deliberately gone rather than fixed.

`stats.nba.com` refuses connections from datacenter IP ranges, and GitHub
Actions runners are hosted on Azure. The old workflow could never have worked;
it also called `wrangler d1 execute` with neither `--remote` nor `--local`, so
it would not have reached the production database even if the fetch had
succeeded.

Ingestion is therefore an **operator-local** task. The reproducible artefact is
the committed data snapshot, and refreshes arrive as a pull request with a diff
summary, so every production data change has an author, a review and a CI run.
