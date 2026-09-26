"""Shared data contracts (mirrors ARCHITECTURE.md).

Temporary home until Person B merges db/schemas.py — then import from there instead.
"""
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Tool = Literal["read_file", "write_file", "http_get", "shell", "send_message"]
ThreatCategory = Literal[
    "benign",
    "covert_channel",
    "credential_access",
    "sandbox_escape",
    "exfiltration",
    "unauthorized_messaging",
]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Action(BaseModel):
    agent_id: str
    tool: Tool
    target: str  # path, URL, command, or recipient agent
    args: dict = {}
    ts: datetime = Field(default_factory=utcnow)


class Decision(BaseModel):
    decision: Literal["allow", "block"]
    reason: str
    risk_score: Optional[float] = None
    policy_id: Optional[str] = None
    latency_ms: float
    # Person A additions (optional, backwards compatible with the ARCHITECTURE.md contract)
    source: Literal["policy", "jev", "fallback"] = "jev"
    threat_category: Optional[ThreatCategory] = None
    category_confidence: Optional[float] = None


class Policy(BaseModel):
    policy_id: str
    version: int = 1
    status: Literal["active", "superseded", "proposed", "rejected"] = "active"
    effect: Literal["deny"] = "deny"
    tool: list[Tool]
    target_glob: list[str]
    condition: Literal[
        "always", "resource_touched_by_other_agent", "rate_exceeds", "unauthorized_recipient"
    ] = "always"
    window_s: int = 600
    max_count: Optional[int] = None  # only for rate_exceeds
    expires_at: Optional[datetime] = None
    source_incident: Optional[str] = None
    rationale: str = ""
