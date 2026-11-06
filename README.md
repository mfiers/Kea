<p align='center'><img src='branding/logo.png' alt='kea' width='520'></p>

# Kea

Website: https://mfiers.github.io/Kea/ (what Kea is, and how to install the tool and the Claude Code skill).

A documentation site for a data analysis, built from typed Markdown pages, with
comments, review cycles run by an agent, and semantic versions.

- **Typed pages** in `doc/<experiment>/<type>/<id>.md`: goal, premise, question, hypothesis (written before or
  after the results), step, result, conclusion, decision, figure, artefact, resource (a data source, server or file from outside, with version and checksum), caveat, term, reference. Typed
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
- **Executive summaries** at three levels: the project (`doc/_summary.md`), each experiment (its home page's text
  before the first `##` heading) and each question (front-matter `answer:`, two or three sentences). The experiment
  page lists every question with its answer in short; a question page leads with its conclusions and results.
- **Tags**: every page has a coloured tag with its type's icon and number (Q1, C2). The tag is always the link; in
  lists of pages the whole line is the link.

## Small enough to change while you use it

Kea is deliberately lightweight:
- about 4,000 lines of Python and 700 lines of its own JavaScript and CSS;
- nine Python dependencies, with three JavaScript libraries copied in at fixed versions;
- no database: the pages are Markdown in git, and comments and review-cycle state are append-only JSON-lines
  files;
- the site is plain static HTML, rebuilt in seconds.

This means the agent that runs the review cycle can also change the tool **during the session**, when a reader
asks for it. In the project where Kea was built, these all came from reader requests and were added within the
same session, most within minutes:
- the menu bar;
- comment states per version;
- a "freeze" phase;
- static builds for public hosting;
- the in-page editor;
- the History page.

A wish for one project goes into `kea.yaml` or the project's own pages. A wish that would help every project goes
into Kea, with a test, as a new tagged version.

## Use in a project

**Kea is meant to be run by an AI coding agent** (Claude Code, or another harness that reads a skill file and runs
shell commands). Give the agent the skill (`skill/SKILL.md`, see below) and tell it "use Kea" in your project; it
installs a tagged version, sets up the pages, builds and serves the site, and runs the review cycles. Running Kea
by hand is possible, but keeping pages, hypotheses, change logs and cycles consistent is the agent's job. For
reference, the agent runs:

```
uv add "kea @ git+https://github.com/mfiers/Kea.git@v1.8.2"     # a Python/uv project
#   or, for any other project:  uv tool install git+https://github.com/mfiers/Kea.git@v1.8.2
kea init --title "My project" --experiment first-experiment
make site && make serve                                       # the password is in .env
kea serve --install-service --host <ip> --port 8210 --enable   # optional: keep it running (systemd user unit)
```

`kea init` never overwrites a file; it adds `kea.yaml`, `doc/_schema.yaml`, a first experiment, `.env`, Makefile
targets and a section in `CLAUDE.md`. The agent's routine is in the skill (`skill/SKILL.md`); copy that folder to
`~/.claude/skills/kea/` to make it available in every project.

## Commands

`kea init | build | context <question|experiment> [--strict] [--mode review|local|public] [--out DIR] | pdf [--out FILE] [--no-pdf on build] | cite [--write] | serve [--install-service] | check | list [--unplanned] | show | reply | status | cycle
status|plan-updated|start|release | watch | apply-suggestion`

`kea context <question>` prints what an analysis run on that question must take into account: its answer so far,
conclusions, results and hypotheses, the premises, the decisions in force, every caveat on these pages and on the
method, open comments and gaps. `kea context <experiment>` lists the open work of an experiment.

`kea watch --deadline 3d` (or 12h, an ISO date/time, epoch seconds) exits 10 when there are comments to plan, 20
when a reader pressed Implement and 30 at the deadline; it prints a status line every hour (`--report-every`).
`kea watch --status` says whether a watcher is running and when it last looked.

## PDF

`kea pdf` (or `make pdf`) puts every page into one PDF, ordered for a reader on paper. The title page has the
project's summary, its version (the version of the pages; the site and the PDF are two views of it), the author
(`author:` in `kea.yaml`), the repository (`repository:`, or the git remote) and a link to Kea. With more than one
experiment, page 2 summarises each experiment and each is a chapter; with one, the PDF reads as that experiment.
Then:

- *At a glance* (every question with its answer in short and its conclusions, each conclusion in full once, and
  the open caveats);
- background and scope, premises;
- one part per question: a table of its hypotheses, then the results with their figures;
- conclusions, caveats and methods (steps, each followed by its decisions);
- closing chapters: overview of all pages (one table per kind: tag, one line, status, question, linked pages),
  hypotheses in full, data and resources (resources O1 … with version, retrieval date, checksum and local copy;
  data files; figure files), the glossary (terms T1 …, then groups such as *Genes*), the references and what
  changed (releases with kind, plan and commit; runs with their commits).

References are numbered B1, B2 … in order of first citation, shown in the text as small superscript tags, and listed
like a journal's reference list from each page's `citation:` (`kea cite --write` fills it from Europe PMC, Nature
style). Full names read as the kind in its colour followed by the tag (Question [Q1]); lists of pages carry the
status and page number at the end of each line. Figures are printed at their own size (from the PNG's dpi), at most
the text width and 19 cm high; the build notes figures it has to shrink below 80 %.

A standard closing chapter, *About this document*, explains the parts present, the page types (in the site's
colours), the numbers, the statuses and the page references. Every link to a page shows its page number.

It leaves out comments, plans, code listings, the relations graph (the overview tables are its printed form) and
the contents of data files, so no donor-level rows reach the PDF. It needs
[Typst](https://github.com/typst/typst/releases) (a single binary; or `typst:` in `kea.yaml`). Without it the
`.typ` source is still written. Output goes to `report/pdf/<title>_<date>_<version>_<commit>.pdf` and is never
overwritten. A figure page may set `pdf_width:` (`100%`, `12cm`) to override the automatic size.

`kea build` also puts the PDF into the site, linked from the home page, when Typst is installed. It is recompiled
only when something in it changes: the cache key (`report/pdf/_cache/`) covers the whole Typst source, every image
file's bytes, the Kea version and the Typst version, and the build prints why it reused or rebuilt the PDF.
`--no-pdf` skips it.

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

## About

Kea was developed by Mark Fiers together with Claude (Anthropic), an AI coding assistant. Mark directed the
design and tested it in use; much of the code and text was written by Claude. Treat Kea as research software:
check what it builds before you rely on it.
