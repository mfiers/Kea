"""One agent per project: who the running agent is, and the lease that keeps a second one out.

Two Claude sessions working on the same project (folding the same comments, editing the same pages, releasing
over each other) must never happen. Every command that writes to the review record (reply, status, cycle,
watch, apply-suggestion, publish) first takes or renews the project's lease; a different agent is refused.

Agent identity (agent_id): KEA_AGENT_ID if set, else the Claude Code session (CLAUDE_CODE_SESSION_ID), else
the nearest ancestor process called claude, else this shell's session. Background jobs of a session (the
watcher) inherit its identity.

Where the lease lives:
    local project   data/feedback/agent_lease.json (not in git), with the holder's process for a liveness check
    hub project     on the hub (kea hub: POST /p/<name>/hub/lease); see feedback.backend

A lease is free when nobody holds it, when the holder is the same agent, when it expired (TTL after the last
renewal; the watcher renews it on every poll), or (local only) when the holder's process on this host is gone.
Taking a lease from a live holder needs --force, which the skill allows only on the owner's word.
"""
from __future__ import annotations

import fcntl
import json
import os
import socket
import time
from pathlib import Path

from kea.config import FEEDBACK_DIR, PROJECT_ROOT

TTL = 2 * 3600                          # seconds a lease lasts after its last renewal


class LeaseHeld(Exception):
    """Another agent holds the project's lease."""

    def __init__(self, holder: dict):
        self.holder = holder
        super().__init__(describe_refusal(holder))


def _ancestor_claude_pid() -> int | None:
    pid = os.getppid()
    for _ in range(12):
        if pid <= 1:
            return None
        try:
            name = Path(f"/proc/{pid}/comm").read_text().strip()
            status = Path(f"/proc/{pid}/status").read_text()
        except OSError:
            return None
        if name == "claude":
            return pid
        pid = int(next((line.split()[1] for line in status.splitlines() if line.startswith("PPid:")), "0"))
    return None


def agent_pid() -> int:
    """The process whose life is the agent's life (the Claude session if found, else this process's parent)."""
    for variable in ("CLAUDE_PID",):
        if os.environ.get(variable, "").isdigit():
            return int(os.environ[variable])
    return _ancestor_claude_pid() or os.getppid()


def agent_id() -> str:
    if os.environ.get("KEA_AGENT_ID"):
        return os.environ["KEA_AGENT_ID"].strip()[:120]
    if os.environ.get("CLAUDE_CODE_SESSION_ID"):
        return "claude-session:" + os.environ["CLAUDE_CODE_SESSION_ID"].strip()[:100]
    claude = _ancestor_claude_pid()
    if claude:
        return f"claude-pid:{socket.gethostname()}:{claude}"
    return f"shell:{socket.gethostname()}:{os.getsid(0)}"


def agent_info() -> dict:
    return {"agent": agent_id(), "host": socket.gethostname(), "pid": agent_pid(), "path": str(PROJECT_ROOT)}


def describe_refusal(holder: dict) -> str:
    renewed = holder.get("renewed_at") or holder.get("since") or "?"
    return (f"another agent works on this project: {holder.get('agent', '?')} on {holder.get('host', '?')} "
            f"({holder.get('path', '?')}), since {holder.get('since', '?')}, last renewed {renewed}"
            f"{', watching' if holder.get('watching') else ''}. Only one agent may work on a project. Stop and tell "
            "the owner; take over (kea lease take --force) only when the owner says that session is finished.")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _epoch(iso: str) -> float:
    import calendar
    try:
        return float(calendar.timegm(time.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")))
    except (TypeError, ValueError):
        return 0.0


def is_free_for(holder: dict | None, agent: str, now: float | None = None, check_process: bool = True) -> bool:
    """May `agent` take this lease? (No holder, the same agent, expired, or a dead process on this host.)"""
    if not holder or not holder.get("agent"):
        return True
    if holder["agent"] == agent:
        return True
    now = time.time() if now is None else now
    if _epoch(holder.get("renewed_at") or holder.get("since", "")) + float(holder.get("ttl", TTL)) < now:
        return True
    if check_process and holder.get("host") == socket.gethostname() and holder.get("pid"):
        try:
            os.kill(int(holder["pid"]), 0)
        except ProcessLookupError:
            return True
        except (PermissionError, ValueError):
            return False
    return False


def holder_ended_here(holder: dict) -> bool:
    """True when the lease holder ran on this host and its process is gone (its session has ended)."""
    if holder.get("host") != socket.gethostname() or not holder.get("pid"):
        return False
    try:
        os.kill(int(holder["pid"]), 0)
    except ProcessLookupError:
        return True
    except (PermissionError, ValueError):
        return False
    return False


def lease_path() -> Path:
    return FEEDBACK_DIR / "agent_lease.json"


def read_local(path: Path | None = None) -> dict:
    try:
        return json.loads((path or lease_path()).read_text())
    except (OSError, ValueError):
        return {}


def take_local(path: Path | None = None, force: bool = False, watching: bool = False, ttl: float = TTL,
               info: dict | None = None, check_process: bool = True) -> dict:
    """Take or renew the local lease (with a file lock); LeaseHeld when another live agent holds it."""
    path = path or lease_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    info = info or agent_info()
    with open(path.with_suffix(".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        holder = read_local(path)
        if not force and not is_free_for(holder, info["agent"], check_process=check_process):
            raise LeaseHeld(holder)
        same = holder.get("agent") == info["agent"]
        lease = {**info, "since": holder.get("since") if same else now_iso(), "renewed_at": now_iso(), "ttl": ttl,
                 "watching": watching}
        if force and holder.get("agent") and not same:
            lease["took_over_from"] = holder.get("agent")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(lease, indent=1))
        os.replace(temporary, path)
        return lease


def release_local(path: Path | None = None, force: bool = False) -> bool:
    path = path or lease_path()
    holder = read_local(path)
    if not holder:
        return True
    if holder.get("agent") != agent_id() and not force:
        raise LeaseHeld(holder)
    path.unlink(missing_ok=True)
    return True
