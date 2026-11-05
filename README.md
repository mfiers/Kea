<p align='center'><img src='branding/logo.png' alt='kea: Keep Evidence Attached' width='520'></p>

# Kea: Knowledge, Evidence, Argument

*Keep Evidence Attached.* A documentation site for a data analysis, built from typed Markdown pages, with
comments, review cycles run by an agent, and semantic versions.

- **Typed pages** in `doc/<experiment>/<type>/<id>.md`: goal, premise, question, hypothesis (written before or
  after the results), step, result, conclusion, decision, figure, artefact, caveat, term, reference. Typed
  relations live in the front matter (supports, opposes, answers, tests, limits, …) and are checked against
  `doc/_schema.yaml`.
- **The site** (`kea build`) shows:
    - node pages with their connections;
    - a tree map and an interactive relations graph per experiment;
    - code pages with line anchors, and artefact pages with preview, checksum and download;
    - one change-log page per agent run, and commit pages;
    - a glossary with automatic links, and full figure captions;
    - for every page, when it last changed (site version) and whether its claim changed.
- **Comments** (`kea serve`):
    - select text and comment, or suggest an edit in the page's Markdown;
    - a shared password with a free-form name;
    - an append-only log in `data/feedback/events.jsonl`.
- **Review cycles**:
    1. Readers comment; the agent (`kea watch`, adaptive polling) folds the comments into one plan.
    2. A reader presses *Freeze for review*; then only the plan takes comments.
    3. *Implement*, or *Unfreeze*. On Implement, the agent implements, writes the change log, answers every
       thread with its commit and releases a semantic version (`kea cycle release`, git tags).
    4. A History page shows comments → plan items → commits → pages per version.

## Use in a project

```
uv add --editable path/to/kea      # or: uv add git+https://…/kea@vX.Y.Z
uv run kea init --title "My project" --experiment first-experiment
make site && make serve            # the password is in .env
```

`kea init` never overwrites a file; it adds `kea.yaml`, `doc/_schema.yaml`, a first experiment, `.env`, Makefile
targets and a section in `CLAUDE.md`. The agent's routine is in the skill (`skill/SKILL.md`).

## Commands

`kea init | build [--strict] | serve | check | list [--unplanned] | show | reply | status | cycle
status|plan-updated|start|release | watch | apply-suggestion`

## Third-party files (copied, pinned)

Recogito text-annotator 4.3.7 (BSD-3), Cytoscape.js 3.30.2 (MIT), marked 12.0.2 (MIT); versions and checksums in
`src/kea/feedback/static/VENDOR.md` and `src/kea/docsite/static/README.md`.

## History

Developed inside the trajectories project (KU Leuven) in November 2026 (`src/docsite`, `src/feedback`, then
`packages/kea`) and moved here on 2026-11-05. This repository previously held an unrelated older Kea (a helper to
make command line tools more intelligent, last PyPI release 0.0.28); its history is kept: tag `legacy-0.0.28`,
branches `master` and `prefix_mode`.

## Tests

`uv run pytest` (unit tests, the comment server, the review cycle, and an example project built from scratch).
