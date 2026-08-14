# 3. Gold parquet is committed to the repository

Accepted.

## Context

`stats.nba.com` refuses requests from datacenter IP ranges. GitHub Actions
runners are hosted on Azure, so requests hang rather than fail. **A nightly
ingestion job against that source can never work from CI** — the previous
version's `etl-nightly.yml` could not have succeeded even if its other three
defects were fixed.

## Decision

Ingestion is **operator-local**. The reproducible artefact is the committed
gold snapshot: roughly 30–40 MB of zstd parquet, plus a contract sidecar per
table recording row count, dtypes, per-column null rate, ranges and a content
hash.

## Consequences

- **A clean clone reproduces every reported number with no network at all.**
  `hoopslab verify` and `hoopslab train --verify` both run offline, and CI
  runs them on every push.
- Raw shot coordinates are _not_ committed even though they would fit. Git
  history is permanent and shots are regenerable; zone aggregates are not.
- Refreshing the snapshot is a pull request with a data diff in the body, an
  author, and a CI run — not a silent cron.
- The inversion is worth stating: a comparable project downloads half a
  gigabyte before it can reproduce anything. This one needs zero bytes.
