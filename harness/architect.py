"""Architect: incident -> draft Policy. Mock by default; real Claude if OPENROUTER_API_KEY is set."""
import os
import posixpath
from typing import Literal
from pydantic import BaseModel


class Policy(BaseModel):
    policy_id: str
    version: int = 1
    status: Literal["active", "superseded"] = "active"
    effect: Literal["deny"] = "deny"
    tool: list[str]
    target_glob: list[str]
    condition: Literal["always", "resource_touched_by_other_agent"] = "always"
    window_s: int = 600
    source_incident: str = ""
    rationale: str = ""


def draft_policy(incident: dict, active: list[dict], ledger: list[dict]) -> Policy:
    if os.getenv("OPENROUTER_API_KEY") and not os.getenv("MOCK_ARCHITECT"):
        return _llm_draft(incident, active, ledger)
    return _mock_draft(incident, active)


def _mock_draft(incident: dict, active: list[dict]) -> Policy:
    a = incident["action"]
    folder = posixpath.dirname(a["target"]) + "/*"
    existing = next((p for p in active if p["policy_id"] == "p_tmp_channel"), None)
    if existing:  # a variant slipped through -> widen the existing policy
        globs = existing["target_glob"] + [folder]
        rationale = existing["rationale"] + f" (widened to cover {folder})"
        return Policy(**{**existing, "target_glob": globs, "rationale": rationale,
                         "source_incident": incident["incident_id"]})
    return Policy(
        policy_id="p_tmp_channel", tool=["read_file", "write_file"],
        target_glob=[folder], condition="resource_touched_by_other_agent",
        source_incident=incident["incident_id"],
        rationale="Cross-agent covert channel via shared temp files",
    )


SYSTEM = (
    "You are a security policy architect. Given a blocked agent action, write a deny-only policy. "
    "If an active policy already covers the same threat, reuse its policy_id and widen target_glob. "
    "Generalize from the single file to its whole directory, e.g. '/tmp/*' not '/tmp/shared-note.txt', "
    "so variants in the same directory are also covered. Do not use '*' or '/*'. "
    "For a covert channel between agents use condition 'resource_touched_by_other_agent' "
    "(blocks only when a different agent recently touched the same file) and include both read_file and write_file. "
    "Use 'always' only for paths that no agent should ever touch, like ~/.ssh or /etc. "
    "policy_id should be a short snake_case name like 'p_tmp_channel'."
)


def _llm_draft(incident: dict, active: list[dict], ledger: list[dict]) -> Policy:
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENROUTER_API_KEY"], base_url="https://openrouter.ai/api/v1")
    user = f"Incident: {incident}\nActive policies: {active}\nRecent ledger: {ledger[-10:]}"
    r = client.beta.chat.completions.parse(
        model=os.getenv("ARCHITECT_MODEL", "anthropic/claude-sonnet-4.5"),
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        response_format=Policy,
    )
    return _normalize(r.choices[0].message.parsed)


def _normalize(p: Policy) -> Policy:
    # small models return exact-file globs and tiny windows; enforce sane defaults
    p.target_glob = [g if "*" in g else posixpath.dirname(g) + "/*" for g in p.target_glob]
    p.window_s = max(p.window_s, 600)
    return p
