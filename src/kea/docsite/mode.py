"""Build mode: what a built site may contain and how it links to data (set once by `kea build --mode`).

review  (default) the comment layer and review cycle; data downloads through the server (/files/<path>, allow-list)
local   no comment layer; data links are relative file links into the project folder (the site lives inside it),
        so the site works opened from disk or served as plain files
public  no comment layer, no data links or downloads, no previews of tables unless the artefact page declares
        `access:` public or aggregate; no comment threads, plans or comments overview; for hosting elsewhere
"""
from __future__ import annotations

import os
from pathlib import Path

from kea.config import PROJECT_ROOT

MODES = ("review", "local", "public")
PUBLIC_ACCESS = ("public", "aggregate", "aggregate numbers only")
MODE = "review"
WITH_CHANGELOG = True             # public builds: run and commit pages only with --with-changelog
SITE: Path = PROJECT_ROOT / "report" / "site"
OMITTED: list[dict] = []          # public builds: what was left out, written to _public_report.json


def configure(mode: str, site: Path, with_changelog: bool = False) -> None:
    global MODE, SITE, WITH_CHANGELOG
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    MODE, SITE = mode, site.resolve()
    WITH_CHANGELOG = mode != "public" or with_changelog
    OMITTED.clear()


def comments_enabled() -> bool:
    return MODE == "review"


def data_links() -> bool:
    return MODE in ("review", "local")


def file_href(relative: str, prefix: str) -> str | None:
    """Link from a page (with `prefix` back to the site root) to a project file, or None when not allowed."""
    if MODE == "review":
        return f"/files/{relative}"
    if MODE == "local":
        to_root = os.path.relpath(PROJECT_ROOT, SITE).replace(os.sep, "/")
        return f"{prefix}{to_root}/{relative}"
    return None


def preview_allowed(access: str | None) -> bool:
    if MODE != "public":
        return True
    return str(access or "").strip().lower() in PUBLIC_ACCESS


def omit(kind: str, what: str) -> None:
    OMITTED.append({"kind": kind, "what": what})
