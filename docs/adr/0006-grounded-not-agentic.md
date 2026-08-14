# 6. The scouting report is single-turn and grounded, not an agent

Accepted.

## Context

The obvious shape for "ask questions about basketball data" is a tool-using
agent over the database. It demos well.

It also cannot be evaluated. A chatbot's output has no fixed admissible fact
set, so there is nothing to check a claim against.

## Decision

**Retrieval is a `SELECT`, executed before the model is called.** For a given
person and direction the admissible fact set is fixed and knowable, so it is
fetched whole and passed in one turn. No tool use, no loop.

An agent here would add latency, cost and nondeterminism, and would introduce
the one failure mode being engineered out: _not_ retrieving something and
filling the gap from pretraining.

Three properties follow:

1. **The name is withheld during evaluation.** A model told it is looking at a
   particular player writes a fluent report from memory. Anonymised mode
   redacts the subject and the clubs; naming any of them is an automatic
   failure.
2. **Citations are structural.** `Claim.fact_ids` has `min_length=1`, so a claim
   without a citation is not a report the parser accepts.
3. **The outcome is never in the bundle.** Reports are written from the
   projection and its interval alone; what actually happened is shown beside
   them.

## Consequences

- Groundedness becomes machine-checkable, offline, at zero cost.
- Responses are content-addressed and committed, so the demo and the whole
  evaluation run with no key and no network.
- The limit is stated rather than glossed: anonymisation removes the name and
  the teams, not the identity. A reader who knows the era could still work out
  who some subjects are, so the anonymised figure bounds recall-leakage from
  below rather than ruling it out.
