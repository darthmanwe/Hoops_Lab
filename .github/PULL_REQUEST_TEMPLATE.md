## What and why

<!-- What changed, and what problem it solves. -->

## Checklist

- [ ] `npm run lint && npm run format:check && npm run type && npm run test` passes
- [ ] `npm run ml:lint && npm run ml:type && npm run ml:test` passes
- [ ] The full suite passes **offline, with no credentials set**

If this touches data or models:

- [ ] Every served number traces to real data or a fitted model — no placeholders
- [ ] Model-derived values carry a `model_version` that resolves in the registry
- [ ] Any new dependency bound has a comment explaining the bound
- [ ] Numbers quoted in the README are reproducible by `hoopslab train --all --verify`
- [ ] New network- or credential-dependent tests are marker-gated
