"""Content-addressed store of model responses.

Every response is keyed on a hash of everything that determined it — model id,
system prompt, rendered evidence, output schema and token ceiling. Change any
of them and the key changes, so a stale response can never be served for a
prompt it was not produced by. That is the difference between a cache and a
directory of files that used to be right.

The store is **committed**, which is what makes the demo and the whole
evaluation suite run at zero cost and with no key. It is also why the entries
are readable JSON rather than a pickle: a reviewer can open one and see exactly
what the model was asked and what it said.

Nothing writes here except a real API call. Hand-authoring an entry would put
text that no model produced behind an interface that says a model produced it,
which is the specific dishonesty this project was rebuilt to remove. Test
fixtures live in ``tests/`` and are named as fixtures.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hoopslab.llm.schemas import ScoutingReport

#: Bumped when the stored shape changes, so old entries are ignored rather than
#: misread. Part of the key, so a bump is a clean cache miss.
CACHE_VERSION = 1


def cache_key(
    *,
    model: str,
    system: str,
    evidence: str,
    schema: str,
    max_tokens: int,
) -> str:
    """Hash of every input that determines the response."""
    digest = hashlib.sha256()
    payload = json.dumps(
        {
            "version": CACHE_VERSION,
            "model": model,
            "system": system,
            "evidence": evidence,
            "schema": schema,
            "max_tokens": max_tokens,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    digest.update(payload.encode("ascii"))
    return digest.hexdigest()[:24]


@dataclass(frozen=True)
class CachedResponse:
    """A stored response and the provenance needed to trust it."""

    key: str
    model: str
    created_at: str
    person_id: str
    target_season_id: str
    anonymized: bool
    evidence_digest: str
    report: ScoutingReport
    usage: dict[str, int]

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "model": self.model,
            "created_at": self.created_at,
            "person_id": self.person_id,
            "target_season_id": self.target_season_id,
            "anonymized": self.anonymized,
            "evidence_digest": self.evidence_digest,
            "usage": self.usage,
            "report": self.report.model_dump(),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> CachedResponse:
        return cls(
            key=payload["key"],
            model=payload["model"],
            created_at=payload["created_at"],
            person_id=payload["person_id"],
            target_season_id=payload["target_season_id"],
            anonymized=payload["anonymized"],
            evidence_digest=payload["evidence_digest"],
            report=ScoutingReport.model_validate(payload["report"]),
            usage=payload.get("usage", {}),
        )


class ResponseCache:
    """A directory of content-addressed responses."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> CachedResponse | None:
        path = self.path_for(key)
        if not path.is_file():
            return None
        return CachedResponse.from_json(json.loads(path.read_text(encoding="utf-8")))

    def put(self, response: CachedResponse) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(response.key)
        path.write_text(
            json.dumps(response.to_json(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return path

    def entries(self) -> list[CachedResponse]:
        if not self.directory.is_dir():
            return []
        return [
            CachedResponse.from_json(json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(self.directory.glob("*.json"))
        ]

    def __len__(self) -> int:
        return len(list(self.directory.glob("*.json"))) if self.directory.is_dir() else 0

    def prune(self, live_digests: dict[str, str], *, dry_run: bool = True) -> list[CachedResponse]:
        """Find, and optionally delete, responses whose evidence has moved on.

        A committed cache is an asset until the data changes underneath it, at
        which point it becomes a directory of confident prose about numbers
        that are no longer true. The export already refuses to serve those, so
        nothing incorrect reaches the API — but leaving them on disk invites
        someone to read one and believe it.

        ``live_digests`` maps a response key to the digest of the evidence
        rebuilt from current gold. A key that is absent is stale too: its
        transition no longer scores at all.
        """
        stale = [
            entry
            for entry in self.entries()
            if live_digests.get(entry.key) != entry.evidence_digest
        ]
        if not dry_run:
            for entry in stale:
                self.path_for(entry.key).unlink(missing_ok=True)
        return stale


def now_iso() -> str:
    return datetime.now(UTC).isoformat()
