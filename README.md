# Immune Harness: A Self-Evolving Security System for AI Agents

A security layer that detects new AI-agent attacks in real time, blocks them before execution, and rewrites its own guardrails so the same attack — or a variant — is blocked from memory next time.

**Architecture, schemas, folder layout, team split, and demo script: [ARCHITECTURE.md](ARCHITECTURE.md)**

## The Problem

In July 2026, ~1,200 OpenAI agents secretly coordinated, shared 70,000+ messages via hidden file channels, and attacked Hugging Face infrastructure. Static security failed because:
- Individual actions appeared harmless
- Coordination across agents was invisible
- The system didn't learn from new attack patterns

## Our Solution

We replicate this in a toy sandbox with scripted malicious agents and close the loop:

```
Jev scores the action → Block → Architect rewrites policy → Compiler validates → MongoDB Atlas → every agent protected
```

### Example: Covert Communication (Hugging Face-style)

```python
Agent Alpha: write_file("/tmp/shared-note.txt", "attack instructions")
✓ Allowed (looks normal)

Agent Beta: read_file("/tmp/shared-note.txt")
⚠️ Jev risk 0.95 — reads a file another agent just wrote, no authorized edge
✗ BLOCKED → incident

Architect → policy "p_tmp_channel v1": deny cross-agent access to /tmp/*
Compiler → replay vs benign traffic: 0 false positives → active (pushed via Atlas change stream)

Agent Gamma: write_file("/tmp/team-sync.txt", ...)
✗ BLOCKED by policy in ~1ms — no LLM call

Agent Gamma: write_file("/var/tmp/x", ...)
⚠️ Not covered → Jev flags → Architect widens policy to v2 → next attempt blocked
```

## Components

| Component | Role | Tech |
|---|---|---|
| Gateway + Sentry | Intercepts every tool call; policy match, then Jev risk score + threat category | FastAPI, Jev via OpenRouter |
| Architect | Turns incidents into new or updated policies | Claude via OpenRouter + Pydantic structured output |
| Compiler | Deny-only, scope limits, replay vs benign traffic, activate | Python |
| Agents + Tool runner | Scripted attackers and benign workers in a sandbox folder | Python |
| MongoDB Atlas | `security_policies`, `action_ledger`, `security_incidents` + change streams | Atlas |
| Dashboard | Live ledger, incidents, policy versions | Streamlit |

## Setup

```bash
git clone https://github.com/Jalil-g/MongoDB-Hackathon.git
cd MongoDB-Hackathon
git checkout -b feature/your-feature-name
# Package management: uv (not pip). Install: curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync                # creates .venv with Python 3.12 + all deps from uv.lock
cp .env.example .env   # fill OPENROUTER_API_KEY, MONGODB_URI (.env is gitignored)
uv run pytest -q       # run tests
```

Adding a dependency: `uv add <pkg>` (dev-only: `uv add --dev <pkg>`). Commit `pyproject.toml` **and** `uv.lock`.
Run anything through uv: `uv run python ...`, `uv run uvicorn ...`, `uv run streamlit run ...`.

## References

- Incident: [Hugging Face Technical Timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)
- [MongoDB Atlas](https://www.mongodb.com/cloud) · [OpenRouter](https://openrouter.ai) · [TypeSafe Jev docs](https://docs.typesafe.ai)

**One-sentence pitch:** Immune Harness catches new AI-agent attacks, blocks them instantly, and rewrites its own guardrails so every agent is protected next time.

**Hackathon themes:** Memory + Persistence + Self-Evolution (powered by MongoDB Atlas)
