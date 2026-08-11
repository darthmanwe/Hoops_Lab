# API errors

Every non-2xx response is [RFC 9457](https://www.rfc-editor.org/rfc/rfc9457)
`application/problem+json`. Branch on `code`, never on prose.

```json
{
  "type": "https://github.com/darthmanwe/Hoops_Lab/blob/main/docs/errors.md#under-reconstruction",
  "title": "Endpoint under reconstruction",
  "status": 501,
  "code": "UNDER_RECONSTRUCTION",
  "detail": "...",
  "endpoint": "/players/{playerId}/translation",
  "will_serve": "...",
  "blocked_on": "phase-2-translation-model",
  "previously": "..."
}
```

Every response, success or failure, carries an `X-Request-Id` header. Quote it
when reporting a problem.

---

## under-reconstruction

**501.** The endpoint exists in the design and is coming back, but is not yet
backed by real data or a fitted model.

The previous version of this API answered these paths with values hand-written
into an ETL script and displayed by the UI as model output. They were removed
rather than left in place, so the response body states what the endpoint used
to do (`previously`), what it will do (`will_serve`), and which roadmap phase
unblocks it (`blocked_on`).

## metric-withdrawn

**410.** The underlying metric cannot be computed from available data, so the
endpoint is not on the roadmap either.

This is distinct from `501` on purpose. Promising a gravity metric in a roadmap
would be the same overclaim as serving a fabricated one, just slower. The body
carries `reason` — why the metric cannot exist — and `instead`, pointing at the
nearest honestly computable thing.

Currently withdrawn: `/leaderboards/gravity`, `/leaderboards/clutch`,
`/games/{gameId}/momentum`.

## route-not-found

**404.** No registered route matches. Distinct from `410`: "withdrawn" and
"never existed" are different answers and callers are told which one they hit.
`GET /` lists every registered path.

## internal-error

**500.** Unexpected failure. The body carries `request_id`; the corresponding
structured log line carries the path and stack.

The previous version registered no error handler at all, so a D1 or KV failure
surfaced as an unhandled Worker exception — an opaque 500 with no body, no
request id, and nothing useful in the logs.
