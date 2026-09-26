"""Gateway: POST /evaluate — every agent tool call is checked here before it runs.

Flow: Action -> Sentry (policy match, else Jev) -> log to action_ledger -> if Jev blocked it
(a new attack) -> security_incidents, which triggers the Architect. Policy blocks (incl. baselines)
are ledger-only: the attack is already known, and an incident would loop the Architect.

Fail closed: invalid Action -> 422; policy cache unavailable or Atlas write failed -> 503.
Agents must only execute a tool on HTTP 200 with decision == "allow".
Decision.latency_ms = Sentry decision time (policy match or Jev), excluding persistence.

Run: uv run uvicorn harness.gateway:app --reload
"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pymongo.errors import PyMongoError

from harness.contracts import AtlasAction, Decision
from harness.jev import JevScorer
from harness.policy_cache import PolicyCacheUnavailable
from harness.sentry import Sentry
from harness.store import AtlasStore, MemoryStore, store_from_env

load_dotenv()
log = logging.getLogger("harness.gateway")


# "fallback" = the Jev path while Jev is down/slow (heuristic stand-in), so it still counts as a Jev block.
INCIDENT_SOURCES = ("jev", "fallback")


class EvaluateResponse(Decision):
    incident_id: str | None = None


def load_edges() -> set[tuple[str, str]]:
    """Authorized collaboration edges: agents/config.py (Person C) if present, else AUTHORIZED_EDGES="a>b,b>c"."""
    try:
        from agents.config import AUTHORIZED_EDGES  # type: ignore[import-not-found]
        return set(AUTHORIZED_EDGES)
    except ImportError:
        raw = os.environ.get("AUTHORIZED_EDGES", "")
        return {tuple(x.strip() for x in e.split(">", 1)) for e in raw.split(",") if ">" in e}


def load_guardrails() -> dict[str, list[str]]:
    """Per-agent natural-language guardrails from agents/config.py (Person C): AGENT_GUARDRAILS = {agent_id: [...]}.
    "*" applies to every agent; without it the Sentry's DEFAULT_GUARDRAILS apply."""
    try:
        from agents.config import AGENT_GUARDRAILS  # type: ignore[import-not-found]
        return dict(AGENT_GUARDRAILS)
    except ImportError:
        return {}


def create_app(store: MemoryStore | AtlasStore | None = None, jev: JevScorer | None = None,
               edges: set[tuple[str, str]] | None = None,
               guardrails: dict[str, list[str]] | None = None) -> FastAPI:
    store = store or store_from_env()
    sentry = Sentry(policies=store.active_policies, context=store.recent, jev=jev or JevScorer(),
                    authorized_edges=load_edges() if edges is None else edges,
                    guardrails=load_guardrails() if guardrails is None else guardrails)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.start()
        yield
        await store.close()

    app = FastAPI(title="Immune Harness Gateway", lifespan=lifespan)
    app.state.store, app.state.sentry = store, sentry

    @app.post("/evaluate", response_model=EvaluateResponse)
    async def evaluate(action: AtlasAction) -> EvaluateResponse:
        try:
            decision, rows = await sentry.assess(action)
        except PolicyCacheUnavailable:
            raise HTTPException(503, "policy cache unavailable; do not execute") from None
        try:
            # Awaited (not fire-and-forget): the next agent's check must see this row, or a
            # write->read covert channel could slip through a race.
            await store.log_action(action, decision)
            incident_id = None
            if decision.decision == "block" and decision.source in INCIDENT_SOURCES:
                incident_id = await store.log_incident(action, decision, rows)
                log.warning("incident %s: %s %s %s — %s", incident_id, action.agent_id, action.tool,
                            action.target, decision.reason)
        except PyMongoError as e:
            log.error("persistence failed (%s); failing closed", type(e).__name__)
            raise HTTPException(503, "action ledger unavailable; do not execute") from None
        return EvaluateResponse(**decision.model_dump(), incident_id=incident_id)

    @app.get("/health")
    async def health() -> dict:
        try:
            n_policies = len(store.active_policies())
        except PolicyCacheUnavailable:
            n_policies = None
        return {
            "store": store.kind,
            "policy_cache_healthy": store.healthy,
            "policy_cache_error": getattr(getattr(store, "cache", None), "last_error", None),
            "jev": "openrouter" if sentry.jev.api_key else "fallback-only",
            "active_policies": n_policies,
            "authorized_edges": sorted(f"{a}>{b}" for a, b in sentry.authorized_edges),
            "agents_with_guardrails": sorted(k for k in sentry.guardrails if k != "*"),
        }

    return app


app = create_app()
