"""kea init: set up a project for a documentation site with review cycles. Never overwrites a file.

Creates (when missing): kea.yaml, doc/_schema.yaml, doc/<experiment>/experiment/home.md, doc/_changes/, doc/_cycles/,
data/feedback/ (with .gitkeep), .env with a random SITE_PASSWORD; appends (once, between markers): the kea section
of CLAUDE.md, the kea targets of the Makefile, and .gitignore lines. Prints what it did.
"""
from __future__ import annotations

import argparse
import secrets
from pathlib import Path

from kea.config import PACKAGE_DIR

TEMPLATES = PACKAGE_DIR / "templates"
GITIGNORE_LINES = ["report/site/", "report/pdf/", ".env", "data/feedback/server.log", "data/feedback/watch_heartbeat.json",
                   "data/feedback/watch_heartbeat.tmp", "data/feedback/agent_lease.*", "data/feedback/*.before-sync-*"]


def _write_new(path: Path, text: str, done: list[str]) -> None:
    if path.exists():
        done.append(f"kept     {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    done.append(f"created  {path}")


def _append_once(path: Path, marker: str, text: str, done: list[str]) -> None:
    current = path.read_text() if path.exists() else ""
    if marker in current:
        done.append(f"kept     {path} (kea section present)")
        return
    path.write_text(current + ("\n" if current and not current.endswith("\n") else "") + ("\n" if current else "")
                    + text)
    done.append(f"appended {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kea init", description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--title", default="")
    parser.add_argument("--port", type=int, default=8210)
    parser.add_argument("--experiment", default="", help="folder name of a first experiment (e.g. donor-recall)")
    parser.add_argument("--question", default="What does this experiment ask?")
    parser.add_argument("--author", default="", help="author(s) for the PDF's title page (ask the owner)")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    title = args.title or root.name
    done: list[str] = []
    author_line = f"author: {args.author}\n" if args.author else "# author: Your Name   # title page of the PDF\n"
    _write_new(root / "kea.yaml", f"title: {title}\nheading: {title}\n{author_line}port: {args.port}\nhost: 127.0.0.1\n"
                                  "site_dir: report/site\nfeedback_dir: data/feedback\n", done)
    _write_new(root / "doc" / "_schema.yaml", (TEMPLATES / "_schema.yaml").read_text(), done)
    for folder in ("_changes", "_cycles"):
        (root / "doc" / folder).mkdir(parents=True, exist_ok=True)
    _write_new(root / "data" / "feedback" / ".gitkeep", "", done)
    if args.experiment:
        _write_new(root / "doc" / args.experiment / "experiment" / "home.md",
                   (TEMPLATES / "home.md").read_text().replace("{question}", args.question.replace('"', "'")), done)
    _write_new(root / ".env", f"SITE_PASSWORD={secrets.token_urlsafe(12)}\n", done)
    _append_once(root / "CLAUDE.md", "<!-- kea:start -->", (TEMPLATES / "claude_section.md").read_text(), done)
    python_project = (root / "pyproject.toml").exists()
    makefile = (TEMPLATES / "makefile_section.mk").read_text()
    if not python_project:          # e.g. an R project: kea installed as a tool (uv tool install), not a dependency
        makefile = makefile.replace("uv run --locked kea", "kea")
    _append_once(root / "Makefile", "# --- kea:", makefile, done)
    gitignore = root / ".gitignore"
    lines = gitignore.read_text().splitlines() if gitignore.exists() else []
    missing = [line for line in GITIGNORE_LINES if line not in lines]
    if missing:
        gitignore.write_text("\n".join(lines + missing) + "\n")
        done.append(f"added    {len(missing)} line(s) to {gitignore}")
    print("\n".join(done))
    if not python_project:
        print("\nNo pyproject.toml here: the Makefile calls `kea` directly. Install it once with\n"
              "  uv tool install git+https://github.com/mfiers/Kea.git@<version>")
    print("\nNext: write pages under doc/<experiment>/ (see doc/_schema.yaml), then `make site` and `make serve`. "
          "The password is in .env (SITE_PASSWORD); share it, never commit it.")
    return 0
