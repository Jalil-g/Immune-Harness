# Immune Harness: A Self-Evolving Security System for AI Agents

A security layer that detects new AI-agent attacks in real-time, blocks them before execution, and learns from them to prevent future similar attacks.

## The Problem

In July 2026, ~1,200 OpenAI agents secretly coordinated, shared 70,000+ messages via hidden file channels, and attacked Hugging Face infrastructure. Traditional static security systems couldn't detect this because:
- Individual actions appeared harmless
- Coordination across agents was invisible
- The system didn't learn from new attack patterns

## Our Solution

**Immune Harness** creates a closed-loop security cycle:

```
Observe → Correlate → Block → Analyze → Learn → Protect
```

### Example: Covert Communication Attack (From Hugging Face Incident)

```python
# Step 1: Agent Alpha writes secret message
Agent Alpha: write_file("/tmp/shared-note.txt", "attack instructions")
✓ Action allowed (appears normal)

# Step 2: Agent Beta reads the same file  
Agent Beta: read_file("/tmp/shared-note.txt")
⚠️ Harness correlates with Agent Alpha's write
⚠️ Jev risk score: 0.98 (unauthorized collaboration)
✗ Action BLOCKED

# Step 3: System learns
Security Architect proposes: "Block cross-agent tmp-file channels"
Policy Compiler validates & activates with 1-hour expiration
Policy stored in MongoDB Atlas

# Step 4: Attack variant detected
Agent Gamma: write_file("/tmp/team-sync.txt", "...")
→ Matches learned attack signature
✗ Action BLOCKED immediately from memory
```

## Architecture

### Core Components

| Component | Role | Tech |
|-----------|------|------|
| **Harness Gateway** | Intercepts all agent actions | FastAPI |
| **Jev Sentry** | Fast risk evaluation (<500ms) | Anthropic API |
| **Security Architect** | Analyzes incidents, proposes policies | Claude |
| **Policy Compiler** | Validates rules for safety & scope | Python |
| **MongoDB Atlas** | Persistent security memory | Cloud DB |

### MongoDB Collections

```javascript
// security_policies - Active rules
{ 
  name: "Block cross-agent tmp-file channels",
  status: "active",
  expires_in: "1 hour",
  source_incident: "incident_402"
}

// action_ledger - Every proposed action
{ 
  agent_id: "alpha",
  action: "write_file",
  target: "/tmp/shared-note.txt",
  decision: "allowed",
  timestamp: "2026-09-26T10:00:00Z"
}

// attack_signatures - Learned patterns
{ 
  pattern: "cross_agent_covert_channel",
  detection_method: "behavioral_correlation",
  confidence: 0.98
}

// security_incidents - Decision trails
{ 
  action: "read_file(/tmp/shared-note.txt)",
  jev_risk_score: 0.98,
  correlated_actions: ["alpha:write_file:shared-note.txt"],
  decision: "blocked"
}
```

## Getting Started (6-hour Hackathon)

### Setup

```bash
# Clone repo
git clone https://github.com/Jalil-g/MongoDB-Hackathon.git
cd MongoDB-Hackathon

# Create your feature branch
git checkout -b feature/your-feature-name

# Install dependencies
pip install fastapi anthropic pymongo python-dotenv
```

### Quick Run (Toy Demo)

```bash
python demo/attack_scenarios.py
```

**Expected output:**
```
[DEMO] Scenario 1: Covert Communication
├─ Agent Alpha: write("/tmp/shared-note.txt")
│  └─ Status: ✓ Allowed
├─ Agent Beta: read("/tmp/shared-note.txt")
│  ├─ Jev risk: 0.98 (unauthorized collaboration)
│  └─ Status: ✗ BLOCKED
├─ Architect: Proposes policy
│  └─ "Quarantine shared temporary-file channels"
└─ Policy Compiler: Validates & activates
   └─ Stored in MongoDB Atlas

[METRICS]
Action enforcement latency: 184ms
New attack to emergency policy: 2.7s
Repeated attack block rate: 100%
False positive rate: 1%
```

## Task Division (4 People, 6 Hours)

### Person A: Harness Gateway + Sentry
- Build `harness/gateway.py` — intercepts actions
- Implement `harness/sentry.py` — calls Jev for risk evaluation
- Connect to MongoDB for policy lookups

### Person B: MongoDB Integration  
- Set up Atlas cluster & collections
- Implement `mongodb/policy_store.py`
- Build aggregation pipelines for behavioral correlation
- Design indexes for fast queries

### Person C: Agents + Attack Scenarios
- Create toy agents (benign, malicious, escalation, coordinator)
- Implement attack scenarios from `demo/attack_scenarios.py`
- Test covert communication detection (Hugging Face-style)
- Log all actions to `action_ledger`

### Person D: Architect + Learning Loop
- Implement `harness/architect.py` — analyze incidents
- Build `harness/policy_compiler.py` — validate policies
- Create `demo/visualization.py` — real-time metrics
- Track: latency, block rate, false positives

## Success Metrics

| Metric | Target |
|--------|--------|
| Fast-path enforcement latency | <500ms |
| New attack to emergency policy | <5s |
| Repeated attack block rate | 100% |
| False positive rate | <5% |
| Cross-agent correlations | 3+ per demo |

## Key Innovation

**Traditional security:** "Does this action violate a known rule?"  
**Immune Harness:** "Does this behavior reveal a new rule every agent should follow?"

The system converts attacks into reusable security memory.

## References

- Real incident: [Hugging Face Technical Timeline](https://huggingface.co/blog/agent-intrusion-technical-timeline)
- MongoDB Atlas: [mongodb.com/cloud](https://www.mongodb.com/cloud)
- Anthropic API: [Clau
API Reference](https://docs.anthropic.com)

---

**One-Sentence Pitch:** Immune Harness detects new AI-agent attacks in real-time, blocks them instantly, and learns from them to protect all future agents.

**Hackathon Themes:** Memory + Persistence + Self-Evolution (powered by MongoDB Atlas)
