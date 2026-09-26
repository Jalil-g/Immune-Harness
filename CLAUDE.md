# MongoDB-Hackathon Project Guidelines

## Context
- **6-hour hackathon** with 4 team members
- Each person works on separate features
- Features merged to main via simple pull/merge (no formal reviews)
- Speed > perfection

## Workflow

### Feature Separation
- **Person A**: Backend/API endpoints
- **Person B**: Database/MongoDB setup
- **Person C**: Frontend/UI
- **Person D**: Integration/Polish/DevOps

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
- **Anthropic SDK** (Jev for fast risk eval, Claude for architect analysis)
- **MongoDB Atlas** (security_policies, action_ledger, attack_signatures, security_incidents)
- **Streamlit or React** (optional: real-time dashboard)

## Project: Immune Harness
A self-evolving security system that learns from AI-agent attacks.

### Core Loop
Observe → Correlate → Block → Analyze → Learn → Protect

### Key Demo: Hugging Face-style Attack
- Agent A writes secret data to `/tmp/shared-message.txt`
- Agent B reads same file
- **Harness detects covert communication**, blocks Agent B
- **Architect proposes policy**: "Block cross-agent tmp-file channels"
- **Next attack variant is blocked from memory**

### Collections in MongoDB
- `security_policies` — active/emergency/validated policies
- `action_ledger` — all proposed actions (allowed & blocked)
- `attack_signatures` — learned attack patterns
- `security_incidents` — decision trails, incident evidence

## Resources & Setup
- GitHub repo: https://github.com/Jalil-g/MongoDB-Hackathon
- PROJECT_STRUCTURE.md — detailed architecture & task division
- Attack scenarios based on real OpenAI Hugging Face incident (July 2026)

## Communication
- Quick decisions: Slack/Discord
- Blockers: Mention immediately
- Merge announcements: "merging X feature to main"
- Status: Quick updates, not detailed

---
**Remember:** It's a 6-hour sprint. Fast > perfect. Ship with what works.
