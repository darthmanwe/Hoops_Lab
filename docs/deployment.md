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

| Environment  | D1              | Purpose               |
| ------------ | --------------- | --------------------- |
| `dev`        | local miniflare | `wrangler dev`, tests |
| `production` | `hoopslab-prod` | Live                  |

There are two rows because there are two environments. `[env.staging]` used to
sit between them carrying an all-zero D1 id and an all-zero KV id, so
`--env staging` failed while _looking_ configured — which is worse than not
existing. Nothing deployed to it and no workflow referenced it. It was deleted
rather than provisioned; a second environment is worth having when there are
pull-request previews to point at it.

`hoopslab-db` is **not** production and must not be deployed to. It is the
February database, still holding `nba_gravity`, `game_momentum`,
`team_fatigue_effect` and four hardcoded players. Migrations would apply
cleanly alongside them — the table names do not collide — which is exactly the
hazard: the result would be a production database containing tables named after
the fabrications this rebuild exists to have removed.

## Deploy the API

```bash
npm ci
npm run deploy:api    # wrangler deploy --config apps/api/wrangler.toml --env production
```

## Migrations

Numbered migrations under `apps/api/migrations/`, applied by
`wrangler d1 migrations apply`, which tracks what it has already run:

```bash
npm run db:migrate         # local miniflare
npm run db:migrate:prod    # remote hoopslab-prod
```

They replaced a single `CREATE TABLE IF NOT EXISTS` script, which was not a
migration system: re-running it after a schema change was a **silent no-op**, so
adding a column or a constraint to an existing table did nothing and reported
success.

## Deploy the web app

```bash
npm run deploy:web
```

The web app is a Worker, built by `@opennextjs/cloudflare`. Three things about
that script are load-bearing, and each of them replaces something that failed:

- It clears `.next` and `.open-next` first, because `NEXT_PUBLIC_*` is inlined
  by the compiler rather than read at request time, so a warm build ships
  whichever API URL was current when it was made and gives no sign of it.
- It runs `build:cf` between the clean and the deploy, because
  `opennextjs-cloudflare deploy` does **not** build — it ships whatever is in
  `.open-next`, so a script that cleans and then deploys deploys nothing.
- The deployed pages do not reach the API over the public URL. `apps/web` uses
  the `API` **service binding** declared in `wrangler.jsonc`, because a Worker
  cannot call another Worker on the same account through its `workers.dev`
  address: the subrequest loops back into the caller, which answers 404, while
  `curl` against that same URL returns a clean 200.

`NEXT_PUBLIC_API_BASE` is still set, in the committed `apps/web/.env.production`
— it is the transport under `next dev` and the fallback anywhere the binding is
absent, and omitting it would ship a build pointing at `127.0.0.1`. It lives in
that file rather than in `wrangler.jsonc` under `vars` because the compiler
inlines it at build time; declared as a Worker variable it would look
authoritative and do nothing.

**There is one deploy path, and it is `deploy.yml`.** Two Cloudflare git
integrations left over from February were also attached to this repository — a
Pages project and a Workers Build, both named `hoops-lab` — building on every
push alongside it. The Pages project could not succeed, because nothing here
emits a static site any more, and its last _successful_ build therefore stayed
live at `hoops-lab.pages.dev` serving the fabricated February interface. Both
were deleted on 2026-09-06. If a Cloudflare check ever reappears on a commit
here, something has been reconnected in the dashboard and should be removed
rather than fixed.

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
