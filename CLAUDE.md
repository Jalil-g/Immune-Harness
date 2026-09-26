# MongoDB-Hackathon Project Guidelines

## Context
- **6-hour hackathon** with 4 team members
- Each person works on separate features
- Features merged to main via simple pull/merge (no formal reviews)
- Speed > perfection

## Workflow

### Feature Separation
- **Person A**: Gateway + Sentry (`harness/gateway.py`, `harness/sentry.py`)
- **Person B**: MongoDB Atlas (`db/`, `harness/policy_cache.py`)
- **Person C**: Agents + scenarios (`agents/`, sandbox tool runner)
- **Person D**: Architect + Compiler + Dashboard (`harness/architect.py`, `harness/compiler.py`, `dashboard/`)

### Git Workflow
1. Create feature branch: `git checkout -b feature/your-feature-name`
2. Commit frequently (WIP commits are fine)
3. Push to your branch: `git push origin feature/your-feature-name`
4. Before merging: `git pull origin main` to get latest
5. Merge to main: `git checkout main && git merge feature/your-part && git push origin main`
6. Communicate on Slack/Discord before merging to avoid conflicts

### Key Rules
- **Don't modify files outside your feature area**
- **Keep main deployable** — test before pushing
- **Communicate dependencies** (if your feature needs something from another person)
- **Commit messages can be casual** (`wip`, `fixed it`, etc. is fine for hackathon)

## Code Guidelines
- **No overthinking** — ship it, don't refactor
- **Add comments only if unclear**
- **Consistent style** within your feature area
- **Test your code locally** before pushing

## Tech Stack
- **Python 3.10+** (gateway, sentry, architect)
- **FastAPI** (lightweight API)
- **Pydantic** (shared schemas + Architect structured output)
- **Anthropic SDK** (Jev for fast risk eval, Claude for architect analysis)
- **MongoDB Atlas** (security_policies, action_ledger, security_incidents + change streams)
- **Streamlit** (real-time dashboard)
- **Not using:** vector search/embeddings, correlation aggregation engine, Strands/A2A

## Project: Immune Harness
A self-evolving security system that learns from AI-agent attacks.

### Core Loop
Jev scores action → Block → Architect rewrites policy → Compiler validates → Atlas → Protect

Policies ARE the memory: known attacks are blocked by policy match (~1ms); new attacks or variants are caught by Jev and trigger a new policy or a new version of an existing one.

### Key Demo: Hugging Face-style Attack
- Agent A writes secret data to `/tmp/shared-message.txt`
- Agent B reads same file
- **Jev flags covert communication** (sees Agent A's recent write), blocks Agent B
- **Architect proposes policy**: "Block cross-agent tmp-file channels"
- **Next attempt is blocked by policy**; a variant that slips through gets the policy widened (v2)

### Collections in MongoDB
- `security_policies` — versioned deny rules (active / superseded), hot-reloaded via change stream
- `action_ledger` — all proposed actions (allowed & blocked); context for Jev, replay baseline for Compiler
- `security_incidents` — blocked actions + Jev reasoning; change stream triggers the Architect

## Resources & Setup
- GitHub repo: https://github.com/Jalil-g/MongoDB-Hackathon
- ARCHITECTURE.md — architecture, schemas, folder layout, task division, demo script (source of truth)
- Attack scenarios based on real OpenAI Hugging Face incident (July 2026)

## Communication
- Quick decisions: Slack/Discord
- Blockers: Mention immediately
- Merge announcements: "merging X feature to main"
- Status: Quick updates, not detailed

---
**Remember:** It's a 6-hour sprint. Fast > perfect. Ship with what works.
