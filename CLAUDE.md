# Working in this repository

## Deploying

Live: **https://hoopslab-web.kutlumizrak.workers.dev** (web) →
**https://hoopslab-api-production.kutlumizrak.workers.dev** (API).

The order below is not arbitrary — each step depends on the one before it, and
three of them fail in ways that look like something else.

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

### The five things that have actually gone wrong

**A Worker cannot call another Worker on the same account via `workers.dev`.**
The subrequest never leaves the runtime; it loops back into the caller, which
has no `/models` route and answers 404. `curl` against the same URL returns 200,
so the symptom points at the address and the address is fine. `apps/web` reaches
the API through the `API` **service binding** in `wrangler.jsonc`, not through
`NEXT_PUBLIC_API_BASE`. That variable still exists and is still correct — it is
the fallback for `next dev` and would be what a browser used if any page ever
became a client component.

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

**`DATA_SNAPSHOT` must match the seed that was actually loaded.** It prefixes
every cache key, so a stale value serves the previous snapshot's rows out of KV
until the TTL expires. The response says which snapshot it came from, in
`meta.snapshot` — but only to someone reading it. It lives in
`apps/api/wrangler.toml` under `[env.production]`.

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

## House rules

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

**Heredocs mangle backslashes here.** Git Bash on this machine strips one level
inside `<<'PY'`, so `"\\n"` arrives as a real newline. Avoid backslashes in
heredoc'd Python, or use the Edit tool.
