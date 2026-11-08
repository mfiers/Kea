"""Check every local link in a built site: each href/src that points into the site must name a file that exists.

The source check in docsite.nodes covers [[links]] in doc/; this covers what the builder itself writes (menus,
history, change logs, commit pages), so a generated link to a page that was never written is reported too.
Not checked: external addresses (http:, https:, mailto: …), in-page anchors (#…), and paths the site server
answers itself (SERVER_PATHS: comment API, login, data files under files/), which are not files in the built
folder. A link out of the site (local mode: data links into the project folder) is fine when the file exists.

Input: the built site folder. Output: :func:`broken_links`, a list of problem lines (empty when all links resolve).
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

TAG = re.compile(r"<[a-zA-Z][^<>]*>")       # real tags only: link-like text in highlighted code is not a tag
LINK = re.compile(r"""\s(?:href|src)\s*=\s*(?:"([^"]*)"|'([^']*)')""", flags=re.I)
SERVER_PATHS = ("_feedback/", "_api/", "_files/", "files/", "login", "logout", "hub/", "id/")   # id/: uid resolver   # files/: data links
                                                                                          # (review mode)


def _is_local(target: str) -> bool:
    if not target or target.startswith(("#", "/", "//", "{", "$")):
        return False
    return not re.match(r"^[a-z][a-z0-9+.-]*:", target, flags=re.I)       # http:, mailto:, data:, javascript: …


def broken_links(site: Path) -> list[str]:
    """One line per broken local link: '<page>: link to <target> (no such file)'."""
    problems: list[str] = []
    site = site.resolve()
    for page in sorted(site.rglob("*.html")):
        text = page.read_text(encoding="utf-8", errors="replace")
        seen: set[str] = set()
        for match in (link for tag in TAG.finditer(text) for link in LINK.finditer(tag.group(0))):
            target = match.group(1) if match.group(1) is not None else match.group(2)
            target = target.replace("&amp;", "&")
            if target in seen or not _is_local(target):
                continue
            seen.add(target)
            path = unquote(urlsplit(target).path)
            if not path:
                continue
            resolved = (page.parent / path).resolve()
            relative = resolved.relative_to(site).as_posix() if resolved.is_relative_to(site) else None
            if relative is not None and relative.startswith(SERVER_PATHS):
                continue
            if relative is None and resolved.is_file():     # local mode: a project file next to the site
                continue
            if relative is None or not (resolved.is_file() or (resolved / "index.html").is_file()):
                problems.append(f"{page.relative_to(site).as_posix()}: link to {target} (no such file in the site)")
    return problems
