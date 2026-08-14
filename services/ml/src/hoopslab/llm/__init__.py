"""Grounded scouting reports.

The one product feature in this repository that a language model writes, built
so that the claim "it did not make anything up" is *checked* rather than
asserted.

Three design choices carry that:

1. **Retrieval is a ``SELECT``, not an agent.** The admissible fact set for a
   player-season is fixed and knowable in advance, so it is fetched up front
   and passed whole. An agent would add latency, cost and nondeterminism, and
   would introduce the one failure mode being engineered out — *not* retrieving
   something and filling the gap from pretraining.

2. **The name is withheld during evaluation.** A model that is told it is
   looking at Luka Dončić writes a fluent, confident, entirely ungrounded
   report from memory, and every groundedness metric measured that way is
   meaningless. See :mod:`hoopslab.llm.evidence`.

3. **Citations are structural, not requested.** Every claim carries at least
   one fact id because the schema cannot represent a claim without one, and
   each id is resolved against the bundle after parsing. A prompt that asks
   politely for citations gets them most of the time; a schema gets them or
   fails loudly.

The outcome of the transition is deliberately *not* in the bundle. The report
is written from the projection and its uncertainty alone, and what actually
happened is shown beside it — the same separation the rest of the project uses
between what a model claims and how it did.
"""

from __future__ import annotations

from hoopslab.llm.schemas import Claim, EvidenceBundle, Fact, ScoutingReport

__all__ = ["Claim", "EvidenceBundle", "Fact", "ScoutingReport"]
