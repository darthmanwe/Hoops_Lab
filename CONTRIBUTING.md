# Contributing

Setup and day-to-day commands are in [docs/development.md](docs/development.md).

## The one rule

**Never serve a number that is not traceable to real data or a fitted model.**

This project was rebuilt because the previous version violated it: an ETL
script contained 723 lines of hand-written statistics, and the API served them
behind a UI that labelled them model output. Everything below follows from not
repeating that.

Concretely:

- A metric that cannot be computed yet returns `501` with an explanation, or
  `410` if it can never be computed. It does not return a plausible number.
- Every model-derived value carries the `model_version` that produced it, and
  that version resolves in the model registry.
- Point estimates from the translation model are never served without a
  prediction interval. The schema enforces this: the interval columns are
  `NOT NULL`.
- Coefficients live in fitted artefacts, not in route handlers.

## Where computation belongs

**The Worker does no arithmetic.** Workers get 10 ms of CPU per request on the
free tier, and anything computed at request time can drift from what was
computed at training time. Every served number is a column produced by the
Python package. The Worker filters, sorts and paginates; nothing else.

## Before opening a pull request

```bash
npm run lint && npm run format:check && npm run type && npm run test
npm run ml:lint && npm run ml:type && npm run ml:test
```

All of it must pass offline, with no credentials set. If a change requires
network access or an API key to test, mark the test (`net`, `llm`, `judge`,
`slow`, `repro`) so it is deselected by default.

## Dependencies

- Exact versions in `package.json`; `npm ci` in CI. No `"latest"`, no ranges.
- Python bounds carry a **comment explaining the bound**. An unexplained upper
  bound is cargo cult; an unbounded dependency makes results unreproducible.
- Add a dependency in the phase that first imports it, not in advance.

## Commits

Describe the change and its reason. `v1`, `v2`, `v3` are not commit messages —
the previous history consisted of six of them and is the reason nothing about
that version could be reviewed after the fact.

## Reporting a number in the README

It must be reproducible by `hoopslab train --all --verify`, which refits from
committed data with no network and fails if any metric drifts from the
committed run log. If a number cannot be produced that way, it does not go in
the README.
