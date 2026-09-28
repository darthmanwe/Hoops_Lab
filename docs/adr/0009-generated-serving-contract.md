# 9. The serving contract is generated from the app, not written alongside it

Accepted.

## Context

Phase 3 was marked done against "typed routes, OpenAPI, provenance envelope".
`@hono/zod-openapi` was in `package.json` and imported nowhere. `/openapi.json`
and `/docs` both returned 404. `.prettierignore` and `eslint.config.mjs` had
carried the line "Generated. Regenerate with `npm run gen`, never hand-edit"
against four paths since that phase — none of the four files existed, and there
was no `gen` script. The convention was declared and never built, so a
repository whose front page argues that every claim must be checked was
maintaining its serving contract, its TypeScript client and its error catalogue
by hand.

Hand-maintenance of a contract does not fail loudly. It fails by drifting: a
route gains a field, the document does not, and the document keeps looking
authoritative. The same property that makes the roadmap's ✅ marks meaningless
without an artifact behind them makes a hand-written OpenAPI file worse than no
OpenAPI file, because a caller trusts it.

There is a second, sharper failure specific to this migration. Plain `.get()`
handlers keep working on an `OpenAPIHono`. They route, they respond, and every
test stays green — they simply do not appear in the generated document. The
first conversion here documented **fourteen of twenty-nine paths** and the whole
suite passed. A half-finished migration produces a document that is confidently
wrong about which endpoints exist, and nothing about it looks broken.

## Decision

**The document is emitted from the app's own route definitions, and four
artifacts are derived rather than written.** `scripts/gen.ts` imports the Worker
and writes `contracts/openapi.json` from `app.getOpenAPI31Document()`,
`apps/web/src/lib/api/generated/types.ts` from that document, `docs/errors.md`
from `ERROR_CODES`, and `docs/data-dictionary.md` from the Drizzle schema and the
gold contracts. Each file names its source on its first line.

Three consequences of that are decisions in their own right:

1. **A partial migration is a gate failure, not a warning.**
   `apps/api/test/openapi.test.ts` does not ask whether the document parses. It
   asserts that every path the registry declares appears in the served document,
   and that the document contains nothing the registry does not declare — the
   same registry that `registry.test.ts` checks against the router in both
   directions. A surviving `.get()` handler therefore fails a test that names it.

2. **The drift gate checks `git status --porcelain --untracked-files=all`,
   not `git diff --exit-code`.** `git diff` ignores untracked files, so a
   generator that begins emitting a fifth artifact nobody committed would pass.

3. **An out-of-range `limit` returns 422 rather than clamping.** The leaderboard
   parameters were `Math.min(Number(...) || 25, 100)`, which answered a request
   for 9999 rows with 100 and never said so. A silently clamped page is a claim
   about the data that the caller did not make and cannot see — the same failure
   as [ADR 8](0008-silent-drops-fail-loudly.md) wearing HTTP clothes. The ceiling
   is unchanged; only the silence is gone.

## Consequences

- `/openapi.json` and `/docs` (Scalar) exist and are current by construction.
  The `contracts` CI job regenerates and fails on any diff, so a route added
  without a schema, an error code added without an explanation, or a column
  renamed in the Drizzle schema each turn the build red instead of leaving four
  documents describing an API that has moved on.
- The generator writes LF unconditionally. `.gitattributes` normalises, and a
  CRLF write on Windows would fail the drift gate for a file nobody changed.
- It runs under `tsx` rather than Node's type stripping: `engines` allows Node
  22, where stripping needs a flag, and a generator that works on the author's
  machine but not in CI is worse than no generator.
- Callers who relied on a large `limit` being quietly satisfied now get an
  error. That is the intended break, and `docs/errors.md` documents the code.
- The cost is that the document can only describe what the app can express. A
  response shape the route does not model cannot be documented without modelling
  it first, which is the constraint doing the work.
