# Security

## Reporting

Open a [private security advisory](https://github.com/darthmanwe/Hoops_Lab/security/advisories/new).
Please do not open a public issue for a vulnerability.

## Scope

This is a public, read-only analytics API over public basketball statistics.
There are no user accounts, no personal data, and no authentication. The most
useful things to report are:

- SQL injection or query construction that is not parameterised
- A path that leaks Cloudflare account topology or binding identifiers
- Denial of service — the free-tier D1 budget is finite and a single unbounded
  query pattern can exhaust the daily read quota

## Credentials

No secrets are committed. `ANTHROPIC_API_KEY` is the only credential the
project ever uses, and it is needed **only** when explicitly refreshing the
scouting-report cache; the committed cache means the demo and the full
evaluation suite run at zero cost without it.

Two independent guards keep tests from spending money:

1. `services/ml/tests/conftest.py` clears the credential environment and
   disables `.env` loading for every test.
2. CI sets `ANTHROPIC_API_KEY: ""` at the workflow level.

Billed and network-dependent tests are additionally marker-gated and
deselected by default.

## Known accepted exposure

`apps/api/wrangler.toml` contains the production D1 database id and KV
namespace id. These are resource identifiers, not credentials — they are
unusable without an account-scoped API token — but they do disclose account
topology, which is why the file is worth reading before it changes.
