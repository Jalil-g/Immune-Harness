"""Gateway: POST /evaluate — every agent tool call is checked here before it runs.

Flow: Action -> Sentry (policy match, else Jev) -> log to action_ledger -> if a novel block
(Jev/fallback, not an existing policy) -> security_incidents, which triggers the Architect.

Run: uv run uvicorn harness.gateway:app --reload
"""
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from harness.contracts import Action, Decision
from harness.jev import JevScorer
from harness.sentry import Sentry
from harness.store import MemoryStore, MongoStore, store_from_env

load_dotenv()
log = logging.getLogger("harness.gateway")


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


def create_app(store: MemoryStore | MongoStore | None = None, jev: JevScorer | None = None,
               edges: set[tuple[str, str]] | None = None) -> FastAPI:
    store = store or store_from_env()
    sentry = Sentry(policies=store.active_policies, context=store.recent, jev=jev or JevScorer(),
                    authorized_edges=load_edges() if edges is None else edges)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await store.start()
        yield
        await store.close()

    app = FastAPI(title="Immune Harness Gateway", lifespan=lifespan)
    app.state.store, app.state.sentry = store, sentry

    @app.post("/evaluate", response_model=EvaluateResponse)
    async def evaluate(action: Action) -> EvaluateResponse:
        decision, rows = await sentry.assess(action)
        # Awaited (not fire-and-forget): the next agent's check must see this row, or a
        # write->read covert channel could slip through a race.
        await store.log_action(action, decision)
        incident_id = None
        if decision.decision == "block" and decision.source != "policy":
            incident_id = await store.log_incident(action, decision, rows)
            log.warning("incident %s: %s %s %s — %s", incident_id, action.agent_id, action.tool,
                        action.target, decision.reason)
        return EvaluateResponse(**decision.model_dump(), incident_id=incident_id)

    @app.get("/health")
    async def health() -> dict:
        return {
            "store": store.kind,
            "jev": "openrouter" if sentry.jev.api_key else "fallback-only",
            "active_policies": len(store.active_policies()),
            "authorized_edges": sorted(f"{a}>{b}" for a, b in sentry.authorized_edges),
        }

    return app


app = create_app()
