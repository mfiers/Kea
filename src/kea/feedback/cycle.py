"""Review cycles in two phases: comment everywhere → freeze (comments only on the plan) → implement → release.

State is an append-only log, ``data/feedback/cycle.jsonl`` (one JSON event per line, never edited); the current
state is the replay of all events. Transitions (cycle 1 item 8, 2026-11-05):

    collecting ──(reader presses "Freeze for review")──► frozen            comments only on the plan
    frozen ──(reader presses "Unfreeze")──► collecting
    frozen ──(reader presses "Implement the plan"; only when every comment is in the plan)──► implement-requested
    implement-requested ──(reader cancels)──► frozen                       no comments at all
    implement-requested ──(Claude starts)──► implementing                  no comments at all
    implementing ──(Claude releases: run id + commit)──► collecting, next cycle number

Before 2026-11-05 a reader could request implementation directly from collecting (and cancel back to it); old
logs still replay the same way. ``plan-updated`` events record when Claude last folded the comments into the
plan (doc/_cycles/<cycle>.md): threads touched after that moment still need planning.

Input: nothing (the log is created on first write). Output: the log; :func:`state` for server, CLI and builder.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from kea.config import FEEDBACK_DIR, PROJECT_ROOT
from kea.feedback.store import FeedbackError, now_iso

EVENT_TYPES = ("plan-updated", "frozen", "unfrozen", "implement-requested", "cancelled", "implementing", "released")
FROZEN_STATES = ("frozen", "implement-requested", "implementing")     # comments refused (except on the plan, below)
PLAN_OPEN_STATES = ("collecting", "frozen")                           # comments on the plan page accepted
PLAN_PAGE_PREFIX = "plan/"
ALLOWED = {  # event type -> states in which it may happen
    "plan-updated": ("collecting", "frozen"),
    "frozen": ("collecting",),
    "unfrozen": ("frozen",),
    "implement-requested": ("frozen",),
    "cancelled": ("implement-requested",),
    "implementing": ("implement-requested", "frozen", "collecting"),   # Claude may also start when asked in chat
    "released": ("implementing",),
}
_lock = threading.Lock()


def default_path() -> Path:
    return FEEDBACK_DIR / "cycle.jsonl"


@dataclass
class CycleState:
    cycle: int = 1                    # number of the cycle being collected or implemented
    state: str = "collecting"
    since: str = ""                   # time of the last transition
    by: str = ""                      # who made the last transition
    plan_updated_at: str = ""         # last plan-updated event in this cycle
    plan_commit: str = ""
    last_release: dict | None = None  # {cycle, run, commit, at}
    requested_from: str = ""          # state before implement-requested (cancel returns there)

    @property
    def frozen(self) -> bool:
        return self.state in FROZEN_STATES

    def accepts_comments_on(self, page_key: str) -> bool:
        """Whether a new comment, reply or status change on this page key is accepted now."""
        if self.state == "collecting":
            return True
        return self.state in PLAN_OPEN_STATES and page_key.startswith(PLAN_PAGE_PREFIX)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["frozen"] = self.frozen
        return result


def load_events(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or default_path()
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fold(events: list[dict[str, Any]]) -> CycleState:
    current = CycleState()
    for event in events:
        kind = event.get("type")
        if kind == "plan-updated":
            current.plan_updated_at, current.plan_commit = event.get("at", ""), event.get("commit", "")
            continue
        current.since, current.by = event.get("at", ""), event.get("by", "")
        if kind == "implement-requested":
            current.requested_from = current.state
            current.state = "implement-requested"
        elif kind == "frozen":
            current.state = "frozen"
        elif kind == "unfrozen":
            current.state = "collecting"
        elif kind == "cancelled":
            current.state = current.requested_from or "collecting"   # old logs: back to collecting
        elif kind == "implementing":
            current.state = "implementing"
        elif kind == "released":
            current.last_release = {"cycle": current.cycle, "run": event.get("run", ""),
                                    "commit": event.get("commit", ""), "at": event.get("at", ""),
                                    "version": event.get("version", "")}
            current.cycle += 1
            current.state = "collecting"
            current.plan_updated_at, current.plan_commit = "", ""
    return current


def state(path: Path | None = None) -> CycleState:
    return fold(load_events(path))


def append(kind: str, by: str, path: Path | None = None, **fields: str) -> CycleState:
    """Record a transition if it is allowed in the current state; returns the new state."""
    if kind not in EVENT_TYPES:
        raise FeedbackError(f"unknown cycle event {kind!r}")
    path = path or default_path()
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            current = state(path)
            if current.state not in ALLOWED[kind]:
                fcntl.flock(handle, fcntl.LOCK_UN)
                raise FeedbackError(f"cannot {kind} while the site is {current.state}")
            if kind == "released" and not (fields.get("run") and fields.get("commit")):
                fcntl.flock(handle, fcntl.LOCK_UN)
                raise FeedbackError("released needs run and commit")
            event = {"type": kind, "cycle": current.cycle, "at": now_iso(), "by": by,
                     **{key: str(value)[:200] for key, value in fields.items() if value}}
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle, fcntl.LOCK_UN)
    return state(path)


def needs_attention(thread) -> bool:
    """Open, or a reader replied after Claude's last word (and not resolved). Marks (manuscript tags) never do."""
    if thread.status == "marked":
        return False
    if thread.status == "open":
        return True
    last_author = thread.replies[-1].author if thread.replies else thread.author
    return thread.status != "resolved" and last_author != "claude"


def last_activity(thread) -> str:
    times = [thread.created_at, thread.status_at] + [reply.created_at for reply in thread.replies]
    return max(time for time in times if time)


def heartbeat_path() -> Path:
    """Written by the watcher on every poll (not in git): lets the plan page say when Claude last looked."""
    return default_path().parent / "watch_heartbeat.json"


def write_heartbeat(path: Path | None = None, extra: dict | None = None) -> None:
    path = path or heartbeat_path()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"at": now_iso(), **(extra or {})}))
    os.replace(temporary, path)


def read_heartbeat_info(path: Path | None = None) -> dict:
    """Everything the watcher wrote ({} when no watcher has run): at, pid, deadline, state, cycle, started."""
    path = path or heartbeat_path()
    try:
        info = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return info if isinstance(info, dict) and info.get("at") else {}


def read_heartbeat(path: Path | None = None) -> str:
    path = path or heartbeat_path()
    try:
        return json.loads(path.read_text()).get("at", "")
    except (OSError, ValueError):
        return ""


def needs_planning(threads: list, current: CycleState) -> list:
    """Threads needing attention with activity after the last plan update of this cycle."""
    return [thread for thread in threads if needs_attention(thread)
            and (not current.plan_updated_at or last_activity(thread) > current.plan_updated_at)]


AGENT_TRAILER = re.compile(r"^Run:\s*\S+", flags=re.M)   # every agent commit names its run (see the skill)


def direct_edits(since_iso: str) -> list[dict]:
    """Commits after ``since_iso`` that change doc/ and were not made by the agent (no ``Run:`` trailer):
    a reader's own edits (e.g. in Obsidian), to be checked and listed in the plan like a comment."""
    import subprocess
    from kea.feedback import store
    repository = PROJECT_ROOT
    if not since_iso:       # no plan yet: only commits after the first comment can be reactions to the site
        events = store.load_events()
        if not events:
            return []
        since_iso = min(event.get("created_at", "") for event in events)
    arguments = ["git", "log", "--format=%x1e%h%x1f%an%x1f%aI%x1f%s%x1f%b%x1f", "--name-only"]
    if since_iso:
        arguments.append(f"--since={since_iso}")
    output = subprocess.run(arguments + ["--", "doc"], cwd=repository, capture_output=True, text=True).stdout
    edits = []
    for record in output.split("\x1e"):
        if "\x1f" not in record:
            continue
        fields = record.strip("\n").split("\x1f")
        body_and_files = fields[5] if len(fields) > 5 else ""
        if AGENT_TRAILER.search(fields[4] if len(fields) > 4 else ""):
            continue
        files = [line for line in body_and_files.splitlines() if line.startswith("doc/")]
        edits.append({"commit": fields[0].strip(), "author": fields[1], "date": fields[2], "subject": fields[3],
                      "files": files})
    return edits
