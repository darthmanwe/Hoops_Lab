# Committed model responses

Every scouting report the project has ever generated, keyed on a SHA-256 of
everything that determined it: model id, system prompt, rendered evidence
bundle, output schema, and token ceiling. Change any of those and the key
changes, so a stale response can never be replayed for a prompt it was not
produced by.

This directory is committed on purpose. It is what makes `npm run demo:llm` and
the entire groundedness evaluation run at **zero cost, with no API key and no
network**. A reviewer can reproduce every reported groundedness figure from a
clean clone.

## Nothing writes here except a real API call

Files land here one way: `hoopslab report --refresh-cache` or
`hoopslab report-eval --refresh-cache`, with `ANTHROPIC_API_KEY` set and a
`--max-calls` ceiling. Hand-authoring an entry would put text no model produced
behind an interface that says a model produced it — the exact dishonesty this
project was rebuilt to remove.

Test fixtures live in `services/ml/tests/` and are named as fixtures.

## Populating it

```sh
# ~30 reports across the three move directions. Sonnet 5, ~2k tokens each.
npm run ml -- report-eval --refresh-cache --max-calls 30
```

The ceiling is checked *before* each request, so the run cannot overspend it
even if something loops. The measured token cost and prompt-cache hit rate are
printed at the end.

## Reading an entry

Each file is plain JSON: the key, the model, the evidence digest it was written
against, the structured report, and the token usage of the call that produced
it. Open one to see exactly what was asked and what came back.

The export step re-derives each bundle and **drops any entry whose evidence
digest no longer matches** — a report whose evidence cannot be rebuilt cannot
have its numbers checked, and an unauditable report is the one thing the
serving table must not contain.
