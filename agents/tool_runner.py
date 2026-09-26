"""Executes allowed tools inside ./sandbox. Nothing touches the real filesystem or network."""
from pathlib import Path

from agents.config import SANDBOX_ROOT

INBOXES: dict[str, list[dict]] = {}


def resolve(target: str) -> Path:
    """Map a 'real' path (/tmp/x, ~/.ssh/id_rsa, /etc/hosts) into the sandbox."""
    if target.startswith("~"):
        rel = "home" + target[1:]
    else:
        rel = target.lstrip("/")
    p = (SANDBOX_ROOT / rel).resolve()
    if SANDBOX_ROOT.resolve() not in p.parents and p != SANDBOX_ROOT.resolve():
        raise PermissionError(f"path escapes sandbox: {target}")
    return p


def read_file(agent_id: str, target: str, args: dict) -> str:
    return resolve(target).read_text()


def write_file(agent_id: str, target: str, args: dict) -> str:
    p = resolve(target)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(args.get("content", ""))
    return f"wrote {len(args.get('content', ''))} bytes"


def http_get(agent_id: str, target: str, args: dict) -> str:
    return f"<fake response from {target}>"


def shell(agent_id: str, target: str, args: dict) -> str:
    return f"<fake shell output for: {target}>"


def send_message(agent_id: str, target: str, args: dict) -> str:
    INBOXES.setdefault(target, []).append({"from": agent_id, "body": args.get("body", "")})
    return f"delivered to {target}"


TOOLS = {
    "read_file": read_file,
    "write_file": write_file,
    "http_get": http_get,
    "shell": shell,
    "send_message": send_message,
}


def run(agent_id: str, tool: str, target: str, args: dict):
    return TOOLS[tool](agent_id, target, args)
