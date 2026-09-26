"""Person A's view of the shared contracts in db/schemas.py (Person B).

- Policy / utc_now: straight from db.schemas.
- Decision: db.schemas.Decision plus Sentry-only fields (source, threat category). `to_atlas()`
  strips them, because Atlas documents (LedgerEntry / Incident) reject unknown fields.
- Action: db.schemas.Action. Any tool name (built-ins in KNOWN_TOOLS, or e.g. "transfer_funds").
"""
from typing import Literal

from db.schemas import KNOWN_TOOLS, Policy, utc_now
from db.schemas import Action as AtlasAction
from db.schemas import Decision as AtlasDecision

__all__ = ["KNOWN_TOOLS", "Action", "AtlasAction", "AtlasDecision", "Decision", "Policy",
           "ThreatCategory", "utcnow"]

ThreatCategory = Literal[
    "benign",
    "covert_channel",
    "credential_access",
    "sandbox_escape",
    "exfiltration",
    "unauthorized_messaging",
    "guardrail_exploit",
]
utcnow = utc_now
Action = AtlasAction


class Decision(AtlasDecision):
    source: Literal["policy", "jev", "fallback"] = "jev"
    threat_category: ThreatCategory | None = None
    category_confidence: float | None = None

    def to_atlas(self) -> AtlasDecision:
        return AtlasDecision(**self.model_dump(include=set(AtlasDecision.model_fields)))
