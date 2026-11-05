"""Build the documentation site from doc/ (the only source of truth) into report/site/.

Order: load and validate the tree (docsite.nodes) → render every page (docsite.pages: node pages, maps, relation
graphs, code pages, run and commit pages, plans, home, comments overview) → comment layer on every page
(docsite.comments: version, history, static threads, panel, cycle status) → download allow-list and _build.json
(build id, polled by open pages to offer a reload). The output folder is rebuilt from scratch every time; nothing in
it is edited by hand.

Usage: kea build [--strict]   (`make site`)
    --strict: exit 1 when the tree has problems (broken links, schema violations).

Input: doc/**, doc/_schema.yaml, doc/_cycles/cycle-NNN.md (plans), artefact and figure files named in the pages,
git, data/feedback/events.jsonl and cycle.jsonl.
Output: report/site/ (HTML, copied figure images, _feedback/ and _assets/ files, _files.json download allow-list).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from kea.config import SITE_DIR
from kea.docsite import comments
from kea.docsite.nodes import PROJECT_ROOT, Tree, load_tree
from kea.docsite.pages import ASSETS, SiteRenderer

SITE = SITE_DIR


def build_site(tree: Tree, site: Path) -> tuple[dict, list[str]]:
    """Render all pages into an empty ``site`` folder and add the comment layer. Returns (summary, problems)."""
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / "_assets").mkdir()
    for asset in [*ASSETS.glob("*.js"), *ASSETS.glob("*.png"), *ASSETS.glob("*.ico")]:
        shutil.copy2(asset, site / "_assets" / asset.name)
    renderer = SiteRenderer(tree, site)
    renderer.render_all()
    commit = comments.source_version(None)
    build_id = f"{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{commit}"
    counts = comments.inject(site, renderer.pages, build_id=build_id)
    (site / "_files.json").write_text(json.dumps(sorted(renderer.downloads), indent=1))
    editable = {key: str(source.relative_to(PROJECT_ROOT)) for key, source in renderer.pages.values()
                if source is not None and ":" in key and source.is_relative_to(PROJECT_ROOT / "doc")}
    (site / "_sources.json").write_text(json.dumps(editable, indent=1, sort_keys=True))   # pages with an Edit button
    (site / "_build.json").write_text(json.dumps({"build_id": build_id, "commit": commit,
                                                  "built_at": dt.datetime.now().isoformat(timespec="seconds")}))
    summary = {"pages": len(renderer.pages), "injected": counts["pages"], "with_history": counts["with_history"],
               "downloads": len(renderer.downloads), "problems": len(tree.problems) + len(renderer.broken),
               "notes": len(tree.notes)}
    return summary, tree.problems + renderer.broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--site", type=Path, default=SITE)
    args = parser.parse_args(argv)
    tree = load_tree()
    summary, problems = build_site(tree, args.site)
    for problem in problems:
        print(f"PROBLEM {problem}")
    for note in sorted(set(tree.notes)):
        print(f"note    {note}")
    print(json.dumps(summary))
    return 1 if args.strict and summary["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
