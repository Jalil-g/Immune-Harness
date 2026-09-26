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
- MongoDB (database)
- Node.js/Express or similar backend
- React/Vue or vanilla JS frontend
- [Add your actual stack here]

## Resources & Setup
- GitHub repo: https://github.com/Jalil-g/MongoDB-Hackathon
- [Add environment setup steps, API docs, design specs here]

## Communication
- Quick decisions: Slack/Discord
- Blockers: Mention immediately
- Merge announcements: "merging X feature to main"
- Status: Quick updates, not detailed

---
**Remember:** It's a 6-hour sprint. Fast > perfect. Ship with what works.
