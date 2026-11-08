"""Permanent identifiers of pages (roadmap S11, step 1: concept ids).

Every page gets a ``uid:`` in its front matter: 128 random bits written as 26 lower-case base32 characters
(``kea:<uid>`` when cited). It is minted once, never changes when the page is edited, renamed or moved to another
experiment, and is unique across a site (and, on a hub, across all its projects). Each state of a page has a version
id, the hash of its canonical form (:func:`version_of`); the hub keeps the text of every version it was sent, so
``kea:<uid>@<version>`` keeps pointing at what was cited.

    kea check          reports malformed and duplicate uids (problems) and pages without one (one note)
    kea check --fix    writes a new uid into every page that has none (one line after ``id:``; nothing else changes)

The build writes ``_ids.json`` (uid -> page) into the site; ``kea serve`` and the hub answer ``/id/<uid>`` with a
redirect to the page and ``/id/<uid>.json`` with its public facts.

Input: the tree of pages. Output: :func:`problems_and_notes`, :func:`add_missing`, :func:`index`.
"""
from __future__ import annotations

import base64
import re
import secrets
from pathlib import Path

UID_PATTERN = re.compile(r"^[a-z2-7]{26}$")


def new_uid() -> str:
    """128 random bits as 26 lower-case base32 characters (no padding)."""
    return base64.b32encode(secrets.token_bytes(16)).decode("ascii").lower().rstrip("=")


def uid_of(node) -> str:
    return str(node.header.get("uid") or "").strip()


def problems_and_notes(tree) -> tuple[list[str], list[str]]:
    problems, notes, seen = [], [], {}
    missing: dict[str, int] = {}
    for node in tree.nodes.values():
        uid = uid_of(node)
        if not uid:
            missing[node.project] = missing.get(node.project, 0) + 1
            continue
        if not UID_PATTERN.match(uid):
            problems.append(f"{node.key}: uid {uid!r} is not 26 characters a-z and 2-7 (let kea check --fix write one)")
        elif uid in seen:
            problems.append(f"{node.key}: uid {uid} is also the uid of {seen[uid]} (a copied page needs its own: "
                            "delete the line and run kea check --fix)")
        else:
            seen[uid] = node.key
    for project, count in sorted(missing.items()):
        notes.append(f"{project}: {count} page(s) without a permanent id (uid:); run kea check --fix")
    return problems, notes


def add_missing(tree) -> list[Path]:
    """Write a new uid into every page without one, as a line right after ``id:``. Returns the changed files."""
    changed = []
    for node in tree.nodes.values():
        if uid_of(node):
            continue
        text = node.source.read_text(encoding="utf-8")
        lines = text.split("\n")
        end = lines.index("---", 1) if lines and lines[0] == "---" and "---" in lines[1:] else -1
        if end < 0:
            continue
        at = next((index for index in range(1, end) if lines[index].startswith("id:")), 0)
        lines.insert(at + 1, f"uid: {new_uid()}")
        node.source.write_text("\n".join(lines), encoding="utf-8")
        changed.append(node.source)
    return changed


VOLATILE = ("order",)            # front-matter fields that do not change what a page says


def canonical(node) -> str:
    """The page in a fixed form for its version id: front matter with sorted keys (without VOLATILE fields), then
    the body with every run of whitespace made one space. A whitespace-only edit keeps the version; any change of
    words, numbers, status or relations gives a new one."""
    import json
    header = {key: value for key, value in node.header.items() if key not in VOLATILE}
    body = re.sub(r"\s+", " ", node.body).strip()
    return json.dumps(header, sort_keys=True, ensure_ascii=False, default=str) + "\n" + body


def version_of(node) -> str:
    """20 base32 characters of the sha256 of the canonical page (100 bits): cited as kea:<uid>@<version>."""
    import hashlib
    digest = hashlib.sha256(canonical(node).encode("utf-8")).digest()
    return base64.b32encode(digest).decode("ascii").lower()[:20]


def index(tree) -> dict[str, dict]:
    """uid -> the public facts of its page (what /id/<uid>.json answers), with the current version id."""
    return {uid_of(node): {"key": node.key, "url": node.url, "type": node.type, "number": node.number or "",
                           "title": node.title, "short": node.short, "status": str(node.status or ""),
                           "version": version_of(node),
                           "source": source_path(node.source)}
            for node in tree.nodes.values() if UID_PATTERN.match(uid_of(node))}


def source_path(path: Path) -> str:
    """'doc/<experiment>/<type>/<id>.md': the page's file from the project root (as in a published bundle)."""
    parts = path.parts
    return "/".join(parts[len(parts) - 1 - parts[::-1].index("doc"):]) if "doc" in parts else path.name
