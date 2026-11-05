"""The kea command: one entry point for building, serving and the review cycle.

    kea init [--title T] [--port N]   set up doc/, kea.yaml, .env, Makefile targets and the CLAUDE.md section
    kea build [--strict]              build the site (report/site/ by default)
    kea serve [--host H --port P]     serve it with comments (password in .env: SITE_PASSWORD)
    kea list | show | reply | status | cycle | watch | apply-suggestion …
                                      the review cycle (see `kea list --help` etc.)
    kea pdf [--rules public|internal] one PDF of all pages (needs Typst; writes the .typ source without it)
    kea check                         validate doc/ against doc/_schema.yaml without building
"""
from __future__ import annotations

import sys

FEEDBACK_COMMANDS = {"list", "show", "reply", "status", "cycle", "watch", "apply-suggestion"}


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
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
    if command == "serve":
        from kea.feedback import server
        return server.main(rest)
    if command == "check":
        from kea.docsite.nodes import load_tree
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
