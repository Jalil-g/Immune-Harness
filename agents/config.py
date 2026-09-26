import os
from pathlib import Path

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8000/evaluate")
# MOCK_GATEWAY=1 -> decide locally, no gateway needed (for dev before Person A's /evaluate is up)
MOCK_GATEWAY = os.getenv("MOCK_GATEWAY", "0") == "1"

SANDBOX_ROOT = Path(__file__).resolve().parent.parent / "sandbox"

ATTACKERS = ["alpha", "beta", "gamma"]
WORKERS = ["worker_1", "worker_2", "worker_3"]
AGENTS = ATTACKERS + WORKERS

# who may send_message to whom (and legitimately share files with)
# set of (sender, recipient) — Person A's gateway imports this as-is
AUTHORIZED_EDGES: set[tuple[str, str]] = {
    ("worker_1", "worker_2"),
    ("worker_2", "worker_1"),
    ("worker_2", "worker_3"),
    ("worker_3", "worker_2"),
}


def is_authorized(sender: str, recipient: str) -> bool:
    return (sender, recipient) in AUTHORIZED_EDGES
