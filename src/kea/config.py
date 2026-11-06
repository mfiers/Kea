"""Where the project is and how it is configured.

The project root is the nearest folder, from the current directory upwards, that holds ``kea.yaml`` (or, for
older projects, ``doc/_schema.yaml``); ``KEA_PROJECT`` overrides it. ``kea.yaml`` holds the few project
settings; everything else (types, relations, statuses) is in ``doc/_schema.yaml``.

kea.yaml (all keys optional):
    title: Trajectories                     # site name in the menu bar
    heading: "Trajectories: …"              # heading of the site home
    author: Mark Fiers                      # author(s) on the PDF's title page
    repository: https://github.com/x/y      # optional; default: the git remote `origin`, as an https address
    port: 8210                              # kea serve
    host: 127.0.0.1
    site_dir: report/site                   # built site (never edited by hand)
    feedback_dir: data/feedback             # events.jsonl, cycle.jsonl (in git), server log, watcher heartbeat
    cookie_salt: <text>                     # optional; default "kea-site:<project folder name>"
    code_paths: [src/, tests/]              # optional; folders that get code pages
    typst: /path/to/typst                   # optional; kea pdf uses `typst` on PATH otherwise
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

CONFIG_NAME = "kea.yaml"
DEFAULTS = {"title": "Project", "heading": "", "port": 8210, "host": "127.0.0.1", "site_dir": "report/site",
            "feedback_dir": "data/feedback"}


def find_root(start: Path | None = None) -> Path:
    if os.environ.get("KEA_PROJECT"):
        return Path(os.environ["KEA_PROJECT"]).resolve()
    here = (start or Path.cwd()).resolve()
    for folder in [here, *here.parents]:
        if (folder / CONFIG_NAME).exists():
            return folder
    for folder in [here, *here.parents]:
        if (folder / "doc" / "_schema.yaml").exists():
            return folder
    return here


def load_settings(root: Path) -> dict:
    settings = dict(DEFAULTS)
    config = root / CONFIG_NAME
    if config.exists():
        settings.update(yaml.safe_load(config.read_text()) or {})
    settings["heading"] = settings["heading"] or settings["title"]
    return settings


PROJECT_ROOT = find_root()
SETTINGS = load_settings(PROJECT_ROOT)
SITE_DIR = PROJECT_ROOT / SETTINGS["site_dir"]
FEEDBACK_DIR = PROJECT_ROOT / SETTINGS["feedback_dir"]
PACKAGE_DIR = Path(__file__).resolve().parent
