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
Output: report/site/ (HTML, copied figure images, _feedback/ and _assets/ files, _files.json download allow-list,
        <title>-<version>.pdf of all pages when Typst is installed: docsite.pdf.site_pdf; --no-pdf skips it).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

from kea.config import SITE_DIR
from kea.docsite import comments, mode
from kea.docsite.nodes import PROJECT_ROOT, Tree, load_tree
from kea.docsite.pages import ASSETS, SiteRenderer

SITE = SITE_DIR


def build_site(tree: Tree, site: Path, build_mode: str = "review", with_changelog: bool = False,
               with_pdf: bool = True) -> tuple[dict, list[str]]:
    """Render all pages into an empty ``site`` folder and add the comment layer (review mode). Returns
    (summary, problems)."""
    mode.configure(build_mode, site, with_changelog)
    if site.exists():
        shutil.rmtree(site)
    site.mkdir(parents=True)
    (site / "_assets").mkdir()
    for asset in [*ASSETS.glob("*.js"), *ASSETS.glob("*.png"), *ASSETS.glob("*.ico")]:
        shutil.copy2(asset, site / "_assets" / asset.name)
    renderer = SiteRenderer(tree, site)
    if with_pdf:
        from kea.docsite import pdf
        renderer.pdf = pdf.site_pdf(tree, site)
    from kea.docsite import render
    render.PDF = renderer.pdf               # the menu bar links it on every page
    renderer.render_all()
    commit = comments.source_version(None)
    build_id = f"{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}-{commit}"
    counts = comments.inject(site, renderer.pages, build_id=build_id, with_comments=mode.comments_enabled())
    if build_mode == "public":
        report = {"mode": "public", "built_at": dt.datetime.now().isoformat(timespec="seconds"), "commit": commit,
                  "left_out": ["comment layer, comment threads, plans, comments overview, history of review cycles",
                               "change log (run and commit pages)" if not with_changelog else
                               "data files, comment logs and plans in commit diffs (run entries are included and may "
                               "quote comments: read them)",
                               "data links and downloads", "previews of tables without access: public/aggregate"],
                  "previews_left_out": [item["what"] for item in mode.OMITTED if item["kind"] == "preview"]}
        (site / "_public_report.json").write_text(json.dumps(report, indent=1))
    (site / "_files.json").write_text(json.dumps(sorted(renderer.downloads) if build_mode == "review" else [],
                                                 indent=1))
    editable = {key: str(source.relative_to(PROJECT_ROOT)) for key, source in renderer.pages.values()
                if source is not None and ":" in key and source.is_relative_to(PROJECT_ROOT / "doc")}
    (site / "_sources.json").write_text(json.dumps(editable, indent=1, sort_keys=True))   # pages with an Edit button
    (site / "_build.json").write_text(json.dumps({"build_id": build_id, "commit": commit,
                                                  "built_at": dt.datetime.now().isoformat(timespec="seconds")}))
    summary = {"pages": len(renderer.pages), "injected": counts["pages"], "with_history": counts["with_history"],
               "downloads": len(renderer.downloads), "problems": len(tree.problems) + len(renderer.broken),
               "notes": len(tree.notes),
               "pdf": (renderer.pdf or {}).get("file", "none (typst not installed)" if with_pdf else "skipped")
               + (" (reused)" if (renderer.pdf or {}).get("reused") else "")}
    return summary, tree.problems + renderer.broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--mode", choices=mode.MODES, default="review",
                        help="review: with comments (default); local: no comments, data links into the project "
                             "folder; public: no comments, no data, for hosting elsewhere")
    parser.add_argument("--out", "--site", dest="site", type=Path, default=None,
                        help="output folder (default: kea.yaml site_dir; local: report/site-local; public: "
                             "report/site-public)")
    parser.add_argument("--no-pdf", action="store_true", help="skip the PDF of all pages (built with Typst "
                        "when installed, recompiled only when the pages changed)")
    parser.add_argument("--with-changelog", action="store_true",
                        help="public: include run and commit pages (run entries may quote comments)")
    args = parser.parse_args(argv)
    default = {"review": SITE, "local": PROJECT_ROOT / "report" / "site-local",
               "public": PROJECT_ROOT / "report" / "site-public"}[args.mode]
    site = (args.site or default).resolve()
    if args.mode == "local" and not site.is_relative_to(PROJECT_ROOT):
        parser.error("a local build must lie inside the project folder (its data links point into it)")
    if site.is_relative_to(PROJECT_ROOT / "data") or site == PROJECT_ROOT or site in PROJECT_ROOT.parents:
        parser.error(f"refusing to build into {site}: it is the project, a parent of it, or inside data/")
    tree = load_tree()
    summary, problems = build_site(tree, site, args.mode, args.with_changelog, not args.no_pdf)
    for problem in problems:
        print(f"PROBLEM {problem}")
    for note in sorted(set(tree.notes)):
        print(f"note    {note}")
    print(json.dumps({**summary, "mode": args.mode, "out": str(site)}))
    return 1 if args.strict and summary["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
