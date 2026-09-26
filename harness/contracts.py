"""Shared data contracts (mirrors ARCHITECTURE.md).

Temporary home until Person B merges db/schemas.py — then import from there instead.
"""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

# Built-in sandbox tools. Any other tool name is accepted too (e.g. a finance agent's "transfer_funds"),
# so the harness works for agents in other domains; Jev judges them from `args` + the agent's guardrails.
KNOWN_TOOLS = ("read_file", "write_file", "http_get", "shell", "send_message")
Tool = str
ThreatCategory = Literal[
    "benign",
    "covert_channel",
    "credential_access",
    "sandbox_escape",
    "exfiltration",
    "unauthorized_messaging",
    "guardrail_exploit",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Action(BaseModel):
    agent_id: str
    tool: Tool
    target: str  # path, URL, command, recipient agent, or account/resource for custom tools
    args: dict = {}  # tool arguments (e.g. amount, approval) — shown to Jev
    ts: datetime = Field(default_factory=utcnow)


class Decision(BaseModel):
    decision: Literal["allow", "block"]
    reason: str
    risk_score: float | None = None
    policy_id: str | None = None
    latency_ms: float
    # Person A additions (optional, backwards compatible with the ARCHITECTURE.md contract)
    source: Literal["policy", "jev", "fallback"] = "jev"
    threat_category: ThreatCategory | None = None
    category_confidence: float | None = None


class Policy(BaseModel):
    policy_id: str
    version: int = 1
    status: Literal["draft", "active", "superseded"] = "active"  # matches Person B's db/schemas.py
    effect: Literal["deny"] = "deny"
    tool: list[Tool]
    target_glob: list[str]
    condition: Literal[
        "always", "resource_touched_by_other_agent", "rate_exceeds", "unauthorized_recipient"
    ] = "always"
    window_s: int | None = None  # None -> DEFAULT_WINDOW_S for conditions that need a window
    rate_limit: int | None = None  # only for rate_exceeds (name matches db/schemas.py)
    expires_at: datetime | None = None
    source_incident: str | None = None
    rationale: str = ""
