"""Where a comment thread is in the review cycle, for display: open, in plan, addressed (in which version), resolved.

Derived from the thread's status, the plans (doc/_cycles/) and the release tags; nothing is stored:
    open        status open: new, not yet in a plan
    planned     status planned; label "in plan v0.5 #2" (the plan item that names the thread)
    addressed   status answered, page-changed or wont-fix; label "addressed in v0.4.0" (the release that contains
                the answering commit), "addressed, in the next release" before that release exists
    resolved    a reader marked it resolved; label as for addressed when known
ORDER gives the display order (open first, resolved last).
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from kea.config import PROJECT_ROOT

ORDER = {"open": 0, "planned": 1, "addressed": 2, "marked": 2.5, "resolved": 3}
ADDRESSED = ("answered", "page-changed", "wont-fix")
THREAD_ID = re.compile(r"\bt\d{4}_\d{2}_\d{2}_[0-9a-f]{6}\b")
ITEM_HEADING = re.compile(r"^### (\d+)\.", flags=re.M)
_cache: dict[str, object] = {}


def _head() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True).stdout.strip()


def _plan_items() -> dict[str, str]:
    """thread id -> 'v0.5 #2' for every plan in doc/_cycles/ (latest plan wins)."""
    from kea.docsite.history import cycle_version_label
    from kea.docsite.versions import releases
    site = releases("")
    found: dict[str, str] = {}
    for source in sorted((PROJECT_ROOT / "doc" / "_cycles").glob("cycle-*.md")):
        number = int(source.stem.split("-")[-1])
        label = cycle_version_label(number, site)
        text = source.read_text(encoding="utf-8")
        headings = list(ITEM_HEADING.finditer(text))
        for index, match in enumerate(headings):
            end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
            for thread_id in THREAD_ID.findall(text[match.start():end]):
                found[thread_id] = f"{label} #{match.group(1)}".strip() if label else f"cycle {number} #{match.group(1)}"
    return found


def context() -> dict:
    """Release label per commit and plan item per thread; recomputed when git HEAD or the plans change."""
    plans = sorted((PROJECT_ROOT / "doc" / "_cycles").glob("cycle-*.md"))
    key = _head() + "|" + "|".join(f"{path.name}:{path.stat().st_mtime_ns}" for path in plans)
    if _cache.get("key") != key:
        from kea.docsite import versions
        versions._COMMIT_LABELS = None                      # release labels may have changed (new tag)
        _cache.update({"key": key, "labels": versions.commit_labels(), "items": _plan_items()})
    return _cache


def state_of(thread, info: dict | None = None) -> tuple[str, str]:
    """(state, label) of a thread (store.Thread or its dict)."""
    info = info or context()
    status = thread["status"] if isinstance(thread, dict) else thread.status
    thread_id = thread["thread_id"] if isinstance(thread, dict) else thread.thread_id
    commit = (thread.get("commit", "") if isinstance(thread, dict) else thread.commit) or ""
    if status == "open":
        return "open", "open"
    if status == "marked":
        return "marked", "marked"
    if status == "planned":
        item = info["items"].get(thread_id)
        return "planned", f"in plan {item}" if item else "in the plan"
    release = info["labels"].get(commit.split("+")[0][:7], "") if commit else ""
    where = ("in the next release" if release.startswith("after") else f"in {release}") if release else ""
    if status == "resolved":
        return "resolved", "resolved" + (f", addressed {where}" if where else "")
    if status == "wont-fix":
        return "addressed", "won't fix" + (f" ({where.removeprefix('in ')})" if where else "")
    return "addressed", f"addressed {where}".strip()


def sort_key(thread, info: dict | None = None) -> tuple:
    state, _ = state_of(thread, info)
    created = thread["created_at"] if isinstance(thread, dict) else thread.created_at
    return (ORDER[state], created)
