"""Architect: Incident -> draft Policy. Mock by default; real Claude if OPENROUTER_API_KEY is set."""
import os
import posixpath
from typing import Literal
from pydantic import BaseModel

from db.schemas import Incident, LedgerEntry, Policy


class PolicyDraft(BaseModel):
    """Loose shape for LLM structured output; converted to the shared Policy."""
    policy_id: str
    tool: list[str]
    target_glob: list[str]
    condition: Literal["always", "resource_touched_by_other_agent"] = "always"
    window_s: int = 600
    rationale: str


def draft_policy(incident: Incident, active: list[Policy], ledger: list[LedgerEntry]) -> Policy:
    if os.getenv("OPENROUTER_API_KEY") and not os.getenv("MOCK_ARCHITECT"):
        return _llm_draft(incident, active, ledger)
    return _mock_draft(incident, active)


def _to_policy(d: PolicyDraft, incident: Incident) -> Policy:
    # small models return exact-file globs and tiny windows; enforce sane defaults
    globs = [g if "*" in g else posixpath.dirname(g) + "/*" for g in d.target_glob]
    other = d.condition == "resource_touched_by_other_agent"
    return Policy(
        policy_id=d.policy_id, tool=tuple(d.tool), target_glob=tuple(globs),
        condition=d.condition, window_s=max(d.window_s, 600) if other else None,
        source_incident=incident.incident_id, rationale=d.rationale or "Drafted by Architect",
    )


def _mock_draft(incident: Incident, active: list[Policy]) -> Policy:
    folder = posixpath.dirname(incident.action.target) + "/*"
    existing = next((p for p in active if p.policy_id == "p_tmp_channel"), None)
    if existing:  # a variant slipped through -> widen the existing policy
        return Policy(**{
            **existing.model_dump(),
            "target_glob": (*existing.target_glob, folder),
            "rationale": f"{existing.rationale} (widened to cover {folder})",
            "source_incident": incident.incident_id, "status": "draft",
        })
    return _to_policy(PolicyDraft(
        policy_id="p_tmp_channel", tool=["read_file", "write_file"], target_glob=[folder],
        condition="resource_touched_by_other_agent",
        rationale="Cross-agent covert channel via shared temp files",
    ), incident)


SYSTEM = (
    "You are a security policy architect. Given a blocked agent action, write a deny-only policy. "
    "If an active policy already covers the same threat, reuse its policy_id and widen target_glob. "
    "Generalize from the single file to its whole directory, e.g. '/tmp/*' not '/tmp/shared-note.txt', "
    "so variants in the same directory are also covered. Do not use '*' or '/*'. "
    "For a covert channel between agents use condition 'resource_touched_by_other_agent' "
    "(blocks only when a different agent recently touched the same file) and include both read_file and write_file. "
    "Use 'always' only for paths that no agent should ever touch, like ~/.ssh or /etc. "
    "policy_id should be a short snake_case name like 'p_tmp_channel'. "
    "Write rationale as one plain sentence: Jev reads it to recognize variants of this rule."
)


def _llm_draft(incident: Incident, active: list[Policy], ledger: list[LedgerEntry]) -> Policy:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
    user = (
        f"Incident: {incident.model_dump(mode='json')}\n"
        f"Active policies: {[p.model_dump(mode='json') for p in active]}\n"
        f"Recent ledger: {[e.model_dump(mode='json') for e in ledger[-10:]]}"
    )
    r = client.beta.chat.completions.parse(
        model=os.getenv("ARCHITECT_MODEL", "anthropic/claude-sonnet-4.5"),
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        response_format=PolicyDraft,
    )
    return _to_policy(r.choices[0].message.parsed, incident)
