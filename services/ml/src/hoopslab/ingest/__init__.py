"""Fetch raw source payloads into the bronze layer.

Operator-only. `stats.nba.com` refuses connections from datacenter IP ranges
and GitHub Actions runners are hosted on Azure, so this cannot run in CI and
is not needed to reproduce any reported result — the gold layer is committed.

Every module here imports its client library lazily, because those libraries
live in the optional ``ingest`` extra and the rest of the package must import
without them.
"""
