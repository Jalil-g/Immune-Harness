"""Shared wire and BSON contracts for teams A, B, C, and D.

Use model_dump(mode="json") for HTTP/LLM JSON and to_mongo() for database writes.
MongoDB TTLs require BSON datetimes, not ISO strings.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

# Built-in sandbox tools. Any other nonempty tool name is valid too (e.g. a finance agent's
# "transfer_funds"), so the harness covers agents in other domains; Jev judges those from args.
KNOWN_TOOLS = ("read_file", "write_file", "http_get", "shell", "send_message")
NonEmptyStr = Annotated[str, Field(min_length=1)]
Tool = NonEmptyStr
Condition = Literal[
    "always", "resource_touched_by_other_agent", "rate_exceeds", "unauthorized_recipient"
]
PolicyStatus = Literal["draft", "active", "superseded"]
PositiveInt = Annotated[int, Field(gt=0, strict=True)]
UTCDateTime = Annotated[AwareDatetime, AfterValidator(lambda value: value.astimezone(UTC))]
RiskScore = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


def utc_now() -> datetime:
    return datetime.now(UTC)


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def to_mongo(self) -> dict[str, Any]:
        """Keep datetime objects so PyMongo can encode BSON dates."""
        return self.model_dump(mode="python")

    @classmethod
    def from_mongo(cls, document: dict[str, Any]) -> Self:
        """Strip only MongoDB's generated _id; reject other unknown fields."""
        return cls.model_validate({key: value for key, value in document.items() if key != "_id"})


class Action(DocumentModel):
    agent_id: NonEmptyStr
    tool: Tool
    target: NonEmptyStr
    args: dict[str, Any] = Field(default_factory=dict)
    ts: UTCDateTime = Field(default_factory=utc_now)


class Decision(DocumentModel):
    decision: Literal["allow", "block"]
    reason: NonEmptyStr
    risk_score: RiskScore | None = None
    policy_id: NonEmptyStr | None = None
    latency_ms: float = Field(ge=0, allow_inf_nan=False)


class Policy(DocumentModel):
    # Tuples plus frozen fields make cached policy instances safe to share.
    # They are still arrays in JSON and BSON.
    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: NonEmptyStr
    version: PositiveInt = 1
    status: PolicyStatus = "draft"
    effect: Literal["deny"] = "deny"
    tool: tuple[Tool, ...] = Field(min_length=1)
    target_glob: tuple[NonEmptyStr, ...] = Field(min_length=1)
    condition: Condition = "always"
    window_s: PositiveInt | None = None
    rate_limit: PositiveInt | None = None
    expires_at: UTCDateTime | None = None
    source_incident: NonEmptyStr | None = None
    rationale: NonEmptyStr

    @model_validator(mode="after")
    def validate_condition_parameters(self) -> Self:
        if self.condition in {"resource_touched_by_other_agent", "rate_exceeds"}:
            if self.window_s is None:
                raise ValueError(f"{self.condition} requires window_s")
        if self.condition == "rate_exceeds" and self.rate_limit is None:
            raise ValueError("rate_exceeds requires rate_limit")
        if self.condition != "rate_exceeds" and self.rate_limit is not None:
            raise ValueError("rate_limit is only valid for rate_exceeds")
        if self.condition == "unauthorized_recipient" and set(self.tool) != {"send_message"}:
            raise ValueError("unauthorized_recipient only applies to send_message")
        return self


class LedgerEntry(Action, Decision):
    """Flat action + decision, supporting the required (target, ts) index."""

    action_id: NonEmptyStr = Field(default_factory=lambda: f"act_{uuid4().hex}")

    @classmethod
    def from_action(cls, action: Action, decision: Decision) -> Self:
        return cls(**action.model_dump(), **decision.model_dump())


class Incident(DocumentModel):
    incident_id: NonEmptyStr = Field(default_factory=lambda: f"inc_{uuid4().hex}")
    action: Action
    decision: Decision
    context: list[LedgerEntry] = Field(default_factory=list)
    policy_id: NonEmptyStr | None = None  # Resulting policy; filled by Architect.
    ts: UTCDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_block(self) -> Self:
        if self.decision.decision != "block":
            raise ValueError("Only blocked actions create security incidents")
        return self
