# Working in this repository

## Deploying

Live: **https://hoopslab-web.kutlumizrak.workers.dev** (web) →
**https://hoopslab-api-production.kutlumizrak.workers.dev** (API).

`.github/workflows/deploy.yml` does this on every CI-green push to `main`, and
re-seeds only when the snapshot id has moved. The manual sequence below is for
when that is not what you want. The order is not arbitrary — each step depends
on the one before it, and three of them fail in ways that look like something
else.

```bash
npm run ml -- export --demo   # 1. the slice, and it refuses to write one that would not fit
npm run db:migrate:prod       # 2. migrations -> remote D1 (hoopslab-prod)
npm run db:load:prod          # 3. seed, ~14 minutes, one pass
npm run deploy:api            # 4. API Worker
npm run deploy:web            # 5. Next.js via @opennextjs/cloudflare
```

Then check `/health` reports `"d1": {"ok": true}` and the snapshot id you meant
to ship, and load `/projections` in a real browser — not curl. Every page is a
server component, so curl against the web Worker returns 200 and a page shell
whether or not the data behind it arrived.

### The things that have actually gone wrong

**A Worker cannot call another Worker on the same account via `workers.dev`.**
The subrequest never leaves the runtime; it loops back into the caller, which
has no `/models` route and answers 404. `curl` against the same URL returns 200,
so the symptom points at the address and the address is fine. `apps/web` reaches
the API through the `API` **service binding** in `wrangler.jsonc`, not through
`NEXT_PUBLIC_API_BASE`.

That binding is skipped under `next dev`, and must be. OpenNext's dev context
reads `wrangler.jsonc` and materialises the bindings declared there, so
`env.API` exists locally too — bound to a Worker that is not running, which
answers every request 503. The whole site then renders its "could not reach the
API" card while the real dev Worker sits on 8710 answering curl and logging no
requests at all, which points at the backend and is nothing to do with it.

**D1 rejects `BEGIN TRANSACTION` on remote.** It runs remote statements through
Durable Object storage, which coalesces writes atomically on its own and refuses
to be told how. The local miniflare executor has no such objection, so the
wrapper passed every test and failed the first time it met production. The seed
file no longer emits one; `wrangler d1 execute --file` provides the same
guarantee and says so before it starts.

**`NEXT_PUBLIC_*` is inlined by the compiler**, not read at request time. A warm
`.next` ships whichever API URL was current when it was built and gives no sign
of it. `deploy:web` deletes `.next` and `.open-next` first, for this reason
only. The value lives in `apps/web/.env.production`, which is committed —
without it a fresh clone's deploy silently ships a site pointing at 127.0.0.1.

**`opennextjs-cloudflare deploy` does not build.** It deploys whatever is in
`.open-next`, so a script that cleans and then deploys deploys nothing. The
root `deploy:web` runs `build:cf` between the two.

**`DATA_SNAPSHOT` must match the seed that was actually loaded.** It is what
`/health` reports, and `deploy.yml` reads it back from there to decide whether
to re-seed. Stale, and the deploy re-seeds needlessly — ~159,000 billed row
writes against a 100,000/day allowance. Advanced without a matching seed, and it
skips a re-seed that was needed. It lives in `apps/api/wrangler.toml` under
`[env.production]`, and `hoopslab snapshot` prints the value it should hold.

`meta.snapshot` on a response is read from the `data_snapshots` table, not from
this variable, so the two disagreeing is how a mismatch shows itself.

**There is no response cache, whatever the older comments said.** `apps/api`
binds a KV namespace, `/health` probes it with a key nothing writes, and that is
the entire use. Anything claiming a snapshot-prefixed cache key, a TTL, or KV
staleness is describing something that was never built — corrected in the
README, `wrangler.toml` and `lib/snapshot.ts`, but worth knowing before you go
looking for a purge step that does not exist.

### Databases

`hoopslab-prod` (`60c8efd8-4ba4-413f-b357-0746c902c0a8`) is production.
`hoopslab-db` (`f942bd6f-…`) is the February database and still holds the
schema this rebuild deleted — `nba_gravity`, `game_momentum`,
`team_fatigue_effect`, four hardcoded players. Migrations would have applied
cleanly alongside them, since the table names do not collide, but the result
would have been a production database containing tables named after the exact
fabrications the project exists to have removed. It is left in place rather
than dropped: it costs nothing and it is the only remaining evidence of what
the previous version served.

Uploading `docs/social-preview.png` is manual — GitHub exposes no API or `gh`
flag for the social preview image. Settings → General → Social preview.

## Regenerating

```bash
npm run gen        # contracts/openapi.json, the web client types,
                   # docs/errors.md, docs/data-dictionary.md
npm run e2e        # Playwright: 64 tests, both colour schemes, axe + contrast
npm run shots      # README screenshots (needs both dev servers up)
```

`shots` photographs whatever is in the local D1, and `db:load` and
`db:load:fixture` write to the same database. Run `db:load` first or the README
gets pictures of the sixty-person test fixture. It also pins `colorScheme:
"dark"`: headless Chromium asks for light, which did not matter while the site
was dark-only and silently re-rendered every README image the first time it ran
after the light theme landed.

Everything `gen` writes is derived and must never be hand-edited; the
`contracts` CI job regenerates and fails on any diff. It checks
`git status --porcelain` rather than `git diff --exit-code`, because the latter
ignores untracked files and would pass a generator that started emitting a
fifth artifact nobody committed.

The e2e suite needs a seeded local D1:

```bash
npm run db:migrate && npm run db:load:fixture
```

Playwright starts both dev servers itself. Both are needed: every page is a
server component that fetches during render, and a failed fetch renders an
explanation card rather than an error — so a suite pointed at a dead API gets
HTTP 200 and a complete-looking page on every route and passes while proving
nothing. Each spec asserts on content only a real response produces.

**If the e2e job fails, check whether the API Worker was still alive.** Twice —
4 Sep and 7 Sep 2026 — `wrangler dev` came up, passed the health check
Playwright waits on, then exited mid-run printing an empty `✘ [ERROR]`. Every
test after that failed on missing page content, so the report described
sixty-four broken pages and nothing described the one dead process behind them.
`e2e/global-teardown.ts` now says so in one line, the job prints the Worker's
own log on failure and uploads it as `wrangler-logs`, and the job runs with
`WRANGLER_LOG=debug` so that log has something in it.

It has since happened a third time, on Dependabot PR #1 — a bump to
`astral-sh/setup-uv`, which the e2e job does not use at all, so the failure
could not have come from the change under test. That is the shape to watch for:
without the teardown line the obvious reading is "this PR broke the browser
tests", and a valid dependency bump gets closed.

What the captured log shows is mostly what it does not. On every occurrence the
last entry is a routine inspector heartbeat two or three seconds before the
process exits; wrangler logged nothing about its own death. That points away
from an error wrangler raised and towards the process being killed, and the
likeliest killer is memory — workerd, `next dev` compiling routes on demand,
and Chromium, on a 7 GB runner. The job now prints `free -m` and greps `dmesg`
for an OOM kill on failure, which will confirm or rule that out.

Acting on that hypothesis without waiting for it: `e2e/global-setup.ts` now
requests every route once, sequentially, before Playwright launches a browser.
`next dev` compiles a route the first time it is asked for, so the compiler used
to run beside Chromium; warming moves the largest allocation in the job to a
moment when nothing else is running, and costs a few seconds that were the first
test's latency anyway.

**Serving the web app from `next build && next start` instead would be worse,
and the reason is worth keeping.** Next prerenders what it can at build time, so
pages that fetch during render would have their data baked into the bundle. The
suite would then pass against a build rather than against a running API — which
destroys the one property this harness exists for, that a suite pointed at a
dead API must fail. `next dev` re-renders per request, and that is why it stays.

Warming also pins the suite to the fixture. Every page prints the snapshot id it
was served, and `hoopslab fixture` writes `fixture01`, so `global-setup.ts` fails
if no page reports it. Without that check a `NEXT_PUBLIC_API_BASE` resolving to
the deployed Worker — the value sitting in the committed
`apps/web/.env.production` — would have this suite quietly grade the live site
and pass while testing nothing local.

Two things deliberately not done about it. There are **no retries** — Playwright
does not restart a `webServer` that died, so a retry would fail against the same
dead process while turning real regressions into flakes that pass on the second
attempt. And the suite runs **one worker in CI**, where it used to run two: the
config's own note says parallel workers against a single miniflare D1 file
produced flaky reads, and that reason does not stop applying on a runner. The
suite takes about forty seconds either way.

`e2e/servers.ts` probes with `node:http` rather than `fetch`, and that is not a
style choice. Called from `globalTeardown`, `fetch` leaves undici's pool alive
into Playwright's shutdown and Node on Windows aborts with
`Assertion failed: !(handle->flags & UV_HANDLE_CLOSING)` — sixty-four passing
tests and then exit 127.

## House rules

**The test counts are checked against each other, not against reality.**
`test_the_badge_total_is_the_sum_of_its_parts` asserts the README badge equals
the Worker + Python figures in the commands table, and it says why it stops
there: 116 test functions expand to 255 tests through parametrisation, so
counting `def test_` would pin the wrong number confidently. The consequence is
that all three can be consistently wrong together, which is what happened — they
sat at 411 for several commits' worth of new tests before anyone re-ran the
count. After adding tests, run `pytest --collect-only -q` and `npm test` and
update all three by hand.

**Numbers are checked, not remembered.** `services/ml/tests/test_readme_numbers.py`
parses the README, the model card and the ADRs and compares every figure to the
committed run log. A retrain that moves a metric turns the docs red. Do not
quote a number from memory or from an earlier version of a document.

**Tests cannot spend money.** `services/ml/tests/conftest.py` has an autouse
fixture that deletes `ANTHROPIC_API_KEY` and `HOOPSLAB_ANTHROPIC_API_KEY` and
sets `Settings.model_config["env_file"] = None`, so a bare `pytest` cannot
authenticate even with a populated `.env`. Billed calls additionally require
`allow_api=True` and a `max_calls` ceiling checked before each request. Nothing
writes to `data/llm_cache/` except a real API call.

**Run tools the way the config expects.** `npx vitest run` from the repo root
picks the wrong config and fails on `cloudflare:test` — use `npm test`. `mypy`
with an explicit path bypasses `[tool.mypy]` — use `npm run ml:type`, or
`cd services/ml && uv run mypy`.

**Two dependency bumps are declined on purpose**, both recorded in
`.github/dependabot.yml` next to the `ignore` entry that blocks them.
_TypeScript 7_ passes `tsc --noEmit` and the Worker suite, but typescript-eslint
refuses to load under it — "typescript-eslint does not support TS 7.0" — so
`npm run lint` cannot run at all; drop the ignore once typescript-eslint#10940
lands. _pandas 3_ is declined because pandas is used only at the ingest
boundary, and ingestion cannot run in CI, so a major there is an unverifiable
change to the one path no gate exercises. Don't re-run either experiment
without reading those comments first.

**Heredocs mangle backslashes here.** Git Bash on this machine strips one level
inside `<<'PY'`, so `"\\n"` arrives as a real newline. Avoid backslashes in
heredoc'd Python, or use the Edit tool.
