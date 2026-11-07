"""Append-only store of reader comments (threads) on the site.

What it does: keeps every comment, reply and status change as one JSON line in
`data/feedback/events.jsonl`. Nothing in that file is ever edited or deleted; the current
state of every thread is rebuilt by replaying the events in order (`threads()`).

Event types:
    create  a new thread: page, optional quote with context and character offsets, text, author
    reply   a reply in an existing thread
    status  a status change: open, answered, page-changed (with the commit), wont-fix, resolved
    tags    the thread's tags replaced by a new list (tags.py); ``mark`` says whether they are all mark tags

A create event may carry ``tags`` (then the text is optional) and ``mark``. A thread whose tags are all mark tags
(``mark: true``, decided by the server from the site's tag list) has the status ``marked``: a label for later use
(the manuscript), not a request; it turns ``open`` when a task tag is added, and back when the task tags go.

Input: nothing (the file is created on the first write).
Output: the event file; `threads()` returns `Thread` objects for the site, the server and the CLI.
"""

from __future__ import annotations

import fcntl
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kea.config import FEEDBACK_DIR
from kea.feedback.tags import TagError, clean as clean_tags

STATUSES = ("open", "planned", "answered", "page-changed", "wont-fix", "resolved", "marked")
EVENT_TYPES = ("create", "reply", "status", "tags")
MAX_TEXT = 8000
MAX_QUOTE = 2000
MAX_CONTEXT = 200
MAX_NAME = 60
MAX_PAGE = 300
MAX_SOURCE = 200_000                 # suggested edits: the whole page's Markdown

_write_lock = threading.Lock()


class FeedbackError(ValueError):
    """A request that cannot be stored (missing field, too long, unknown thread)."""


@dataclass
class Message:
    author: str
    text: str
    created_at: str
    event_id: str


@dataclass
class Thread:
    thread_id: str
    page: str
    author: str
    text: str
    created_at: str
    page_commit: str = ""
    page_title: str = ""
    quote: str = ""
    prefix: str = ""
    suffix: str = ""
    start: int | None = None
    end: int | None = None
    status: str = "open"
    status_by: str = ""
    status_at: str = ""
    status_note: str = ""
    commit: str = ""
    suggestion: dict | None = None    # suggested edit: {path, base_commit, base_text, new_text, diff}
    tags: list[str] = field(default_factory=list)
    replies: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_path() -> Path:
    return FEEDBACK_DIR / "events.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(prefix: str) -> str:
    """Short, sortable-enough id: date + random part (e.g. t2026_11_04_a3f9c1)."""
    return f"{prefix}{datetime.now(timezone.utc).strftime('%Y_%m_%d')}_{secrets.token_hex(3)}"


def _clean(value: Any, limit: int, name: str, required: bool = False) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\x00", "").strip() if name in ("text", "author", "page", "note") else text.replace("\x00", "")
    if required and not text:
        raise FeedbackError(f"{name} is required")
    if len(text) > limit:
        raise FeedbackError(f"{name} is longer than {limit} characters")
    return text


def _offset(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise FeedbackError(f"{name} must be an integer") from error
    if number < 0:
        raise FeedbackError(f"{name} must be >= 0")
    return number


def load_events(path: Path | None = None) -> list[dict[str, Any]]:
    """All events in file order. A line that is not valid JSON is skipped and reported, never removed."""
    path = path or default_path()
    if not path.exists():
        return []
    events = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"feedback: skipping unreadable line {line_number} of {path}")
    return events


def append_event(event: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    """Validate and append one event (with an exclusive file lock and fsync). Returns the stored event.

    Idempotent per ``request_id`` (a key the browser makes for each submit): when an event with the same key is
    already stored (the request was sent again, e.g. after a stalled disk), that event is returned and nothing is
    written."""
    path = path or default_path()
    request_id = _clean(event.get("request_id"), 80, "request_id")
    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise FeedbackError(f"unknown event type {event_type!r}")
    stored: dict[str, Any] = {"event_id": new_id("e"), "type": event_type, "created_at": now_iso(),
                              "author": _clean(event.get("author"), MAX_NAME, "author", required=True)}
    with _write_lock:
        if request_id:
            for earlier in load_events(path):
                if earlier.get("request_id") == request_id:
                    return earlier
            stored["request_id"] = request_id
        existing = {thread.thread_id for thread in threads(path)} if event_type != "create" else set()
        if event_type == "create":
            stored.update({
                "thread_id": new_id("t"),
                "page": _clean(event.get("page"), MAX_PAGE, "page", required=True),
                "page_title": _clean(event.get("page_title"), MAX_PAGE, "page_title"),
                "page_commit": _clean(event.get("page_commit"), 64, "page_commit"),
                "quote": _clean(event.get("quote"), MAX_QUOTE, "quote"),
                "prefix": _clean(event.get("prefix"), MAX_CONTEXT, "prefix"),
                "suffix": _clean(event.get("suffix"), MAX_CONTEXT, "suffix"),
                "start": _offset(event.get("start"), "start"),
                "end": _offset(event.get("end"), "end"),
                "text": _clean(event.get("text"), MAX_TEXT, "text"),
            })
            stored.update(_tags_of(event))
            if not stored["text"] and not stored.get("tags"):
                raise FeedbackError("text is required (or at least one tag)")
            if stored["page"].startswith("/") or ".." in stored["page"]:
                raise FeedbackError("page must be a path relative to the site root")
            suggestion = event.get("suggestion")
            if suggestion is not None:
                if not isinstance(suggestion, dict):
                    raise FeedbackError("suggestion must be an object")
                stored["suggestion"] = {
                    "path": _clean(suggestion.get("path"), MAX_PAGE, "suggestion.path", required=True),
                    "base_commit": _clean(suggestion.get("base_commit"), 64, "suggestion.base_commit"),
                    "base_text": _clean(suggestion.get("base_text"), MAX_SOURCE, "suggestion.base_text"),
                    "new_text": _clean(suggestion.get("new_text"), MAX_SOURCE, "suggestion.new_text", required=True),
                    "diff": _clean(suggestion.get("diff"), MAX_SOURCE, "suggestion.diff", required=True)}
        else:
            thread_id = _clean(event.get("thread_id"), 64, "thread_id", required=True)
            if thread_id not in existing:
                raise FeedbackError(f"unknown thread {thread_id}")
            stored["thread_id"] = thread_id
            if event_type == "reply":
                stored["text"] = _clean(event.get("text"), MAX_TEXT, "text", required=True)
            elif event_type == "tags":
                stored.update(_tags_of(event))
                stored.setdefault("tags", [])
                stored.setdefault("mark", False)
            else:
                status = event.get("status")
                if status not in STATUSES:
                    raise FeedbackError(f"status must be one of {', '.join(STATUSES)}")
                stored["status"] = status
                stored["note"] = _clean(event.get("note"), MAX_TEXT, "note")
                stored["commit"] = _clean(event.get("commit"), 64, "commit")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(json.dumps(stored, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle, fcntl.LOCK_UN)
    return stored


def _tags_of(event: dict[str, Any]) -> dict[str, Any]:
    try:
        names = clean_tags(event.get("tags"))
    except TagError as error:
        raise FeedbackError(str(error)) from error
    return {"tags": names, "mark": bool(event.get("mark")) and bool(names)} if names else {}


def _retag(thread: Thread, names: list[str], mark: bool) -> None:
    thread.tags = names
    if mark and thread.status == "open":
        thread.status = "marked"
    elif not mark and thread.status == "marked":
        thread.status = "open"


def fold(events: list[dict[str, Any]]) -> dict[str, Thread]:
    """Replay events into threads (ordered by creation)."""
    result: dict[str, Thread] = {}
    for event in events:
        thread_id = event.get("thread_id", "")
        if event.get("type") == "create":
            result[thread_id] = Thread(
                thread_id=thread_id, page=event.get("page", ""), author=event.get("author", ""),
                text=event.get("text", ""), created_at=event.get("created_at", ""),
                page_commit=event.get("page_commit", ""), page_title=event.get("page_title", ""),
                quote=event.get("quote", ""), prefix=event.get("prefix", ""), suffix=event.get("suffix", ""),
                start=event.get("start"), end=event.get("end"), suggestion=event.get("suggestion"))
            _retag(result[thread_id], event.get("tags") or [], bool(event.get("mark")))
        elif thread_id in result:
            thread = result[thread_id]
            if event.get("type") == "reply":
                thread.replies.append(Message(author=event.get("author", ""), text=event.get("text", ""),
                                              created_at=event.get("created_at", ""),
                                              event_id=event.get("event_id", "")))
            elif event.get("type") == "tags":
                _retag(thread, event.get("tags") or [], bool(event.get("mark")))
            elif event.get("type") == "status":
                thread.status = event.get("status", thread.status)
                thread.status_by = event.get("author", "")
                thread.status_at = event.get("created_at", "")
                thread.status_note = event.get("note", "")
                if event.get("commit"):
                    thread.commit = event["commit"]
    return result


def threads(path: Path | None = None) -> list[Thread]:
    return list(fold(load_events(path)).values())
