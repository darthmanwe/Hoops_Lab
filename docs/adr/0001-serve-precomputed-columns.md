# 1. The Worker serves precomputed columns and does no arithmetic

Accepted.

## Context

The serving layer runs on Cloudflare Workers with a **10 ms CPU budget per
request** on the free tier. The previous version computed cosine similarity
across a season table inside `/players/:id/comps`, and blended lineup metrics
in `lineups.ts`. Against the four hardcoded players that existed at the time,
that was survivable. Against 22,297 real player-seasons it is not.

D1's free tier compounds it: 500 MB per database, 100,000 row writes per day,
and **50 queries per invocation**. A single lineup request in the old code ran
an N+1 loop that spent 18% of the per-invocation query budget.

## Decision

**Every number the API serves is a column produced by Python.** The Worker
selects rows, applies a schema, and attaches provenance. It does not compute.

## Consequences

- Train/serve skew is eliminated by construction rather than by discipline.
  There is no second implementation of a metric to drift.
- Raw event data never enters D1. Three million shot rows exceed the size cap
  on their own and would take a month to seed under the write limit.
- A new served quantity requires a Python change, a migration, and a reload.
  That is slower than computing it in the request, and it is the trade being
  made deliberately.
- One endpoint takes arbitrary user input and cannot precompute — the lineup
  indices. That path is covered by a cross-language golden-vector parity test
  rather than by trusting two implementations to agree.
