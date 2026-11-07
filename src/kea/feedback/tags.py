"""Tags that readers put on a text fragment or a whole page, next to (or instead of) a comment.

A tag is stored on a comment thread (store.py: ``tags`` on the create event, a ``tags`` event to change them), so it
uses the comments' anchoring, storage, hub sync and history. There are two kinds:

    task tags     ask the agent for work in the next review cycle (challenge, source, explain, expand, shorten,
                  remove); a thread with one is handled like an open comment, and ``kea show`` prints the tag's
                  instruction for the agent.
    mark tags     label text for later use and ask for no work (the manuscript sections: introduction, methods, …);
                  a thread whose tags are all mark tags gets the status ``marked``: it is not open, not in a plan
                  and not counted as a comment waiting for an answer. ``kea tags`` lists marks for the manuscript.

The vocabulary is DEFAULT_TAGS plus ``tags:`` in kea.yaml (same fields; a known name replaces the default), and
``free_tags: false`` in kea.yaml turns off tags outside the vocabulary (on by default; a free tag is a task tag
without an instruction). ``kea build`` writes the vocabulary to ``_feedback/tags.json`` in the site, so the
browser and the server (also on a hub, which has no kea.yaml of the project) use the project's own list.

Input: kea.yaml settings, or a site's tags.json. Output: :func:`vocabulary`, :func:`check`, :func:`is_mark`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
MAX_TAGS = 12

GROUPS = {"review": "For the next review cycle", "manuscript": "For the manuscript", "own": "Own tags"}

DEFAULT_TAGS: list[dict] = [
    {"name": "challenge", "group": "review", "task": True, "label": "challenge",
     "help": "Doubt this: have it critically re-assessed",
     "instruction": "Re-assess this claim adversarially before the next release: start a separate reviewer (a "
                    "subagent that sees the page, its sources and its caveats, not your reasoning) and ask it "
                    "whether the claim follows from the evidence, what is missing and what would refute it. Answer "
                    "the reviewer point by point; then strengthen, weaken or withdraw the claim, add a caveat, or "
                    "keep it with the reasons. Summarise the exchange in the reply."},
    {"name": "source", "group": "review", "task": True, "label": "needs source",
     "help": "Which file, result or reference supports this?",
     "instruction": "Find the source of this statement: a file in `sources:`, a result page, or a reference. Add "
                    "it, or weaken or remove the statement when there is none."},
    {"name": "explain", "group": "review", "task": True, "label": "explain",
     "help": "Unclear: explain it",
     "instruction": "Explain this for a reader who knows the field but not this project: define terms, say why "
                    "it matters, add an example or a figure reference."},
    {"name": "expand", "group": "review", "task": True, "label": "expand",
     "help": "Say more about this",
     "instruction": "Write more about this: the reasoning, the evidence, the alternatives. Keep every number "
                    "tied to its source."},
    {"name": "shorten", "group": "review", "task": True, "label": "shorten",
     "help": "Too long: say it in fewer words",
     "instruction": "Say the same in fewer words; keep every claim, number and caveat."},
    {"name": "remove", "group": "review", "task": True, "label": "remove",
     "help": "Remove this",
     "instruction": "Remove this text. When it carries a claim that other pages rely on, say so in the reply "
                    "instead of removing it."},
    {"name": "not-in-manuscript", "group": "manuscript", "task": False, "label": "not in manuscript",
     "help": "Keep this out of the manuscript"},
    {"name": "introduction", "group": "manuscript", "task": False, "label": "introduction", "help": ""},
    {"name": "methods", "group": "manuscript", "task": False, "label": "methods", "help": ""},
    {"name": "results", "group": "manuscript", "task": False, "label": "results", "help": ""},
    {"name": "discussion", "group": "manuscript", "task": False, "label": "discussion", "help": ""},
    {"name": "conclusions", "group": "manuscript", "task": False, "label": "conclusions", "help": ""},
    {"name": "supplement", "group": "manuscript", "task": False, "label": "supplement",
     "help": "In the supplementary material"},
]


class TagError(ValueError):
    pass


def vocabulary(settings: dict | None = None) -> dict:
    """{"tags": [...], "free_tags": bool, "groups": {...}} from the defaults and kea.yaml."""
    if settings is None:
        from kea.config import SETTINGS as settings
    tags = {tag["name"]: dict(tag) for tag in DEFAULT_TAGS}
    for extra in settings.get("tags") or []:
        if not isinstance(extra, dict) or not NAME.match(str(extra.get("name", ""))):
            raise TagError(f"kea.yaml tags: each entry needs a name of lower-case letters, digits and '-' ({extra!r})")
        merged = {"group": "review", "task": True, "label": extra["name"], "help": "", "instruction": "",
                  **tags.get(extra["name"], {}), **extra}
        merged["task"] = bool(merged["task"])
        tags[extra["name"]] = merged
    return {"tags": list(tags.values()), "free_tags": bool(settings.get("free_tags", True)), "groups": GROUPS}


def site_vocabulary(site_dir: Path) -> dict:
    """The vocabulary the site was built with (_feedback/tags.json), else the defaults."""
    try:
        data = json.loads((site_dir / "_feedback" / "tags.json").read_text())
        if isinstance(data, dict) and isinstance(data.get("tags"), list):
            return data
    except (OSError, ValueError):
        pass
    return vocabulary({})


def clean(names) -> list[str]:
    """Validate the form of a tag list (no vocabulary check); duplicates dropped, order kept."""
    if names is None or names == "":
        return []
    if not isinstance(names, list):
        raise TagError("tags must be a list")
    result: list[str] = []
    for name in names:
        name = str(name).strip().lower()
        if not NAME.match(name):
            raise TagError(f"tag {name!r}: use lower-case letters, digits and '-' (at most 32)")
        if name not in result:
            result.append(name)
    if len(result) > MAX_TAGS:
        raise TagError(f"at most {MAX_TAGS} tags")
    return result


def check(names, known: dict) -> list[str]:
    """clean() plus: tags outside the vocabulary only when free tags are on."""
    result = clean(names)
    names_known = {tag["name"] for tag in known["tags"]}
    unknown = [name for name in result if name not in names_known]
    if unknown and not known.get("free_tags", True):
        raise TagError(f"unknown tag(s): {', '.join(unknown)}")
    return result


def is_mark(names: list[str], known: dict | None = None) -> bool:
    """True when there are tags and none asks for work (all are mark tags)."""
    if not names:
        return False
    known = known or vocabulary()
    marks = {tag["name"] for tag in known["tags"] if not tag.get("task", True)}
    return all(name in marks for name in names)


def describe(name: str, known: dict | None = None) -> dict:
    known = known or vocabulary()
    for tag in known["tags"]:
        if tag["name"] == name:
            return tag
    return {"name": name, "group": "own", "task": True, "label": name, "help": "",
            "instruction": "A reader's own tag: read it with the text and the comment; ask when the meaning is unclear."}
