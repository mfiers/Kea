"""The kea command: one entry point for building, serving and the review cycle.

    kea init [--title T] [--author A] [--port N]
                                      set up doc/, kea.yaml, .env, Makefile targets and the CLAUDE.md section
    kea new experiment <name> --title "…"
                                      add an experiment to the project (doc/<name>/experiment/home.md)
    kea build [--strict]              build the site (report/site/ by default)
    kea serve [--host H --port P]     serve it with comments (password in .env: SITE_PASSWORD)
    kea list | show | reply | status | cycle | watch | apply-suggestion | tags …
                                      the review cycle (see `kea list --help` etc.)
    kea pdf [--out FILE]               one PDF of all pages (needs Typst; writes the .typ source without it)
    kea cite [--write] [ID …]         full citations (Nature style) for reference pages, from Europe PMC
    kea rrid                          check every resource's RRID against the SciCrunch resolver
    kea context <question|experiment> what to take into account before working on it (premises, decisions,
                                      caveats, evidence so far, open comments, gaps)
    kea check                         validate doc/ against doc/_schema.yaml and the graph rules without building
    kea recheck --list | <id> … --because "…"
                                      pages to recheck after an upstream change; record that one was checked
    kea drop <id>                     what a Drop of that page removes (it and what rests only on it)
    kea lease status|take|release     one agent per project (take it at the start of a session)
    kea publish [--files]             send the built site to the project's Kea hub (kea.yaml remote:)
    kea hub init|add|list|passwords|rotate-key|remove|serve
                                      run a Kea hub: one https server hosting many projects' sites
"""
from __future__ import annotations

import sys

FEEDBACK_COMMANDS = {"list", "show", "reply", "status", "cycle", "watch", "apply-suggestion", "lease", "tags"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        from kea import TAGLINE, __version__
        print(f"Kea {__version__}. {TAGLINE}\n")
        print(__doc__)
        return 0
    command, rest = argv[0], argv[1:]
    if command == "init":
        from kea import init
        return init.main(rest)
    if command == "build":
        from kea.docsite import build
        return build.main(rest)
    if command == "pdf":
        from kea.docsite import pdf
        return pdf.main(rest)
    if command == "cite":
        from kea.docsite import cite
        return cite.main(rest)
    if command == "rrid":
        from kea.docsite import rrid
        return rrid.main(rest)
    if command == "new":
        if rest[:1] != ["experiment"]:
            print("usage: kea new experiment <name> --title \"…\"")
            return 2
        from kea import init
        return init.new_experiment(rest[1:])
    if command == "drop":
        from kea.docsite import graph
        return graph.drop_main(rest)
    if command == "recheck":
        from kea.docsite import graph
        return graph.main(rest)
    if command == "context":
        from kea.docsite import context
        return context.main(rest)
    if command == "hub":
        from kea.feedback import hub
        return hub.main(rest)
    if command == "publish":
        from kea.feedback import publish
        return publish.main(rest)
    if command == "serve":
        from kea.feedback import server
        return server.main(rest)
    if command == "check":
        from kea.docsite.nodes import load_tree
        tree = load_tree(baseline=True)
        if "--fix" in rest:                       # write a permanent id (uid:) into every page without one
            from kea.docsite import identity
            changed = identity.add_missing(tree)
            print(f"wrote a uid into {len(changed)} page(s)")
            tree = load_tree()
        for problem in tree.problems:
            print(f"PROBLEM {problem}")
        for note in sorted(set(tree.notes)):
            print(f"note    {note}")
        print(f"{len(tree.nodes)} pages, {len(tree.problems)} problems")
        return 1 if tree.problems else 0
    if command in FEEDBACK_COMMANDS:
        from kea.feedback import __main__ as feedback
        return feedback.main(argv)
    if command == "--version":
        from kea import __version__
        print(__version__)
        return 0
    print(f"unknown command {command!r}\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
