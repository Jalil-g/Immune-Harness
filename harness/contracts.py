"""Person A's view of the shared contracts in db/schemas.py (Person B).

- Policy / utc_now: straight from db.schemas.
- Decision: db.schemas.Decision plus Sentry-only fields (source, threat category). `to_atlas()`
  strips them, because Atlas documents (LedgerEntry / Incident) reject unknown fields.
- Action: the gateway's HTTP boundary uses db.schemas.Action (the 5 sandbox tools only).
  The Sentry itself stays domain-agnostic and accepts any tool name via the looser Action here.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from db.schemas import Action as AtlasAction
from db.schemas import Decision as AtlasDecision
from db.schemas import Policy, utc_now

__all__ = ["KNOWN_TOOLS", "Action", "AtlasAction", "AtlasDecision", "Decision", "Policy",
           "ThreatCategory", "utcnow"]

KNOWN_TOOLS = ("read_file", "write_file", "http_get", "shell", "send_message")
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


class Action(BaseModel):
    """Sentry input. Any tool name (e.g. a finance agent's "transfer_funds"); Jev judges it from args."""
    agent_id: str
    tool: str
    target: str  # path, URL, command, recipient agent, or account/resource for custom tools
    args: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utc_now)


class Decision(AtlasDecision):
    source: Literal["policy", "jev", "fallback"] = "jev"
    threat_category: ThreatCategory | None = None
    category_confidence: float | None = None

    def to_atlas(self) -> AtlasDecision:
        return AtlasDecision(**self.model_dump(include=set(AtlasDecision.model_fields)))
