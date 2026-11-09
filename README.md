<p align='center'><img src='branding/logo.png' alt='kea' width='520'></p>

# Kea

Website: https://mfiers.github.io/Kea/ (what Kea is, and how to install the tool and the Claude Code skill).

A documentation site for a data analysis, built from typed Markdown pages, with
comments, review cycles run by an agent, and semantic versions.

- **Typed pages** in `doc/<experiment>/<type>/<id>.md`: experiment (the home page, `experiment/home.md`), premise, question, hypothesis (written before or
  after the results), step, result, conclusion, decision, figure, artefact, resource (a data source, server or file from outside, with version and checksum; each record taken from a source, such as a dataset or a GWAS study, is a resource of its own, part of the source), caveat, term, reference. Typed
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
    - select text and comment, or tag it (work for the next cycle, or a manuscript section), or suggest an edit in
      the page's Markdown;
    - propose the next step of the reasoning for the page type (a question on an experiment, a hypothesis or step
      on a question, a conclusion or caveat on a result, …), on the whole page or on selected text;
    - a shared password with a free-form name;
    - an append-only log in `data/feedback/events.jsonl`.
- **The graph as a whole** (`kea check`, every build): a conclusion rests on results, never on a hypothesis; no
  circular support; nothing confirmatory on exploratory evidence only; outcomes name their test. When a page
  changes, every page downstream of it is marked **recheck** until the agent has read it against the change
  (`kea recheck`, ledger `doc/_checks.yaml`); releases wait for that.
- **One step at a time** (`pace: guided`, the default for new projects): the agent proposes questions and
  stops; for an approved question it proposes hypotheses and planned steps and stops; it runs approved steps and
  stops; it concludes from reviewed results. Approval is a Confirm on the site or the owner's word in chat
  (`approved:` on the page); `kea check` refuses work built on unapproved pages.
- **One experiment or more**: a project with one experiment starts at that experiment's page; `kea new
  experiment` adds one, and from two experiments on the site starts at the project page with its own summary.
- **Review cycles**:
    1. Readers comment anywhere; the agent waits (`kea watch`, adaptive polling, no tokens spent on comments).
    2. A PI presses *Harvest comments*; the agent folds every comment into one plan, which then stands until
       the next harvest. The plan page counts the comments made since (*Harvest again* adds them).
    3. *Implement the plan*: comments pause; the agent implements, writes the change log, answers every thread in
       the plan with its commit and releases a semantic version (`kea cycle release`, git tags). Comments left out
       of the plan stay for the next cycle.
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
- a review phase (since replaced by the harvest);
- static builds for public hosting;
- the in-page editor;
- the History page.

A wish for one project goes into `kea.yaml` or the project's own pages. A wish that would help every project goes
into Kea, with a test, as a new tagged version.

## Install

Kea is not on PyPI; install it from this repository with [uv](https://docs.astral.sh/uv/) (it fetches Python ≥ 3.11
if needed). Always name a tag (see [tags](https://github.com/mfiers/Kea/tags)), so a project does not change when
Kea does.

```
# as a command on this machine (any project; also the hub host): puts `kea` in ~/.local/bin
uv tool install git+https://github.com/mfiers/Kea.git@v1.20.0
kea --help

# or as a dependency of a Python/uv project (pinned in its uv.lock); run it as `uv run kea …`
uv add "kea @ git+https://github.com/mfiers/Kea.git@v1.20.0"

# or once, without installing
uvx --from git+https://github.com/mfiers/Kea.git@v1.20.0 kea --help
```

- Upgrade: run the same command with the new tag (`uv tool install --force git+…@vX.Y.Z`, or `uv add` again).
  `uv tool upgrade kea` does not move a pinned tag.
- Remove: `uv tool uninstall kea` (or `uv remove kea`).
- If `kea` is not found after `uv tool install`, run `uv tool update-shell` and open a new shell.
- Needs `git` (for the install and for change logs and versions). Optional: [Typst](https://github.com/typst/typst/releases)
  for the PDF (see [PDF](#pdf)).
- The agent skill is separate: copy `skill/SKILL.md` to `~/.claude/skills/kea/SKILL.md` (Claude Code), from the
  same tag:
  `mkdir -p ~/.claude/skills/kea && curl -fsSL https://raw.githubusercontent.com/mfiers/Kea/v1.20.0/skill/SKILL.md -o ~/.claude/skills/kea/SKILL.md`

## Use in a project

**Kea is meant to be run by an AI coding agent** (Claude Code, or another harness that reads a skill file and runs
shell commands). Give the agent the skill (`skill/SKILL.md`, see below) and tell it "use Kea" in your project; it
installs a tagged version, sets up the pages, builds and serves the site, and runs the review cycles. Running Kea
by hand is possible, but keeping pages, hypotheses, change logs and cycles consistent is the agent's job. For
reference, the agent runs:

```
uv add "kea @ git+https://github.com/mfiers/Kea.git@v1.20.0"     # a Python/uv project
#   or, for any other project:  uv tool install git+https://github.com/mfiers/Kea.git@v1.20.0
kea init --title "My project" --experiment first-experiment
make site && make serve                                       # the password is in .env
kea serve --install-service --host <ip> --port 8210 --enable   # optional: keep it running (systemd user unit)
```

`kea init` never overwrites a file; it adds `kea.yaml`, `doc/_schema.yaml`, a first experiment, `.env`, Makefile
targets and a section in `CLAUDE.md`. The agent's routine is in the skill (`skill/SKILL.md`); copy that folder to
`~/.claude/skills/kea/` to make it available in every project.

## Hosting on a Kea hub

One server can host the sites of many projects and collect their comments, while each project's agent works on
its own machine. The hub runs on any Linux host behind an https reverse proxy (Caddy, nginx); kea talks to it only
over https.

```
# on the hub
kea hub init --dir /srv/kea-hub --url https://kea.example.org
kea hub add trajectories --title Trajectories    # prints the project key, site password, iteration password
kea hub serve --host 127.0.0.1 --port 8300       # behind the proxy, e.g. Caddy: kea.example.org { reverse_proxy 127.0.0.1:8300 }
```

The hub watches each project's agent session through the heartbeats of `kea watch`. A watcher that stops on purpose (to plan comments, to implement, or at its deadline) says so in a last heartbeat; one that falls silent without saying why, while its deadline is still ahead, counts as stopped unexpectedly (a crash, a closed terminal, a sleeping machine or a lost network). The plan page shows the session's state and the time since the last heartbeat; readers who may steer also get a banner on every page. With `notify_url: https://ntfy.sh/<your-topic>` in `hub.yaml` the hub also posts a message when a session stops unexpectedly and when it is back (a plain-text POST with Title and Click headers; any webhook works). `kea hub list` shows each project's session.

To see what the hub does, add `--log events` to `kea hub serve`: one line on stderr per publish, lease change, sign-in, refused key, unknown site and reader action (comment, tag, harvest, implement). `--log requests` adds every request. Query strings are never logged, because sign-in codes travel in them.

Optional: sign-in with ORCID instead of shared passwords. Register a client at orcid.org (Developer tools; redirect URI `https://example.org/auth/orcid/callback`), give the hub `KEA_ORCID_CLIENT_ID` and `KEA_ORCID_CLIENT_SECRET` in its environment, and approve readers with `kea hub users approve <orcid> [pi] [--project name]` (`kea hub users` lists who asked, and for which project). A reader signs in once: every other project site of the hub then lets them in without a click (it asks the hub, which hands its session over with a one-time code, so no cookie is shared between project subdomains), and Sign out on any site signs out of all of them; comments and verdicts carry the reader's ORCID iD. Roles, per project or for all: auditor (reads the site and its comments, writes nothing), reviewer (comments, tags, suggests edits; the default), PI (also harvests the comments into the plan and asks the agent to implement it), director (everything a PI may; the project's lead). The names used before 1.19 (reader, commenter, steerer, owner) still work on the command line and in an existing `users.json`. The project passwords keep working; with ORCID on, a project's login page shows the ORCID button first and folds the shared-password form under "Sign in with a project password". The hub's own address (`https://example.org/`) is a landing page: visitors see what the hub is, a Sign in with ORCID button and the public projects; a signed-in reader sees their projects with their role in each, the projects waiting for approval, the other public projects and Sign out.

Optional: a public project. `kea hub public <name> on` makes its pages, PDF and `/id/` links readable without a login; the comments, the review cycle and uploaded data files still need a sign-in, and visitors see a "Sign in to comment" button. `kea hub public <name> off` closes it again; `kea hub list` shows which projects are public.

Optional: each project on its own subdomain. Put `project_domain: example.org` in the hub's `hub.yaml` and give the proxy a wildcard certificate for `*.example.org`; project `trajectories` is then read at `https://trajectories.example.org/`, old `/p/trajectories/` links redirect there, and agents keep using `https://example.org` in `remote.url`. Every page has a permanent id (`uid:`, minted by `kea check --fix`); `https://example.org/id/<uid>` finds it on any project of the hub, and `…/id/<uid>@<version>` shows a cited version even after later edits.

```
# in the project: kea.yaml
remote:
  url: https://kea.example.org
  project: trajectories
  upload_max_kb: 100                 # data files up to this size go up (default 0: none) …
  upload_include: []                 # … plus these (also flagged ones), never these:
  upload_exclude: []
# .env: KEA_REMOTE_KEY=<project key>
kea publish --files                  # what would go up, and why not
kea publish                          # after every build
```

- **Readers** open `https://kea.example.org/p/trajectories/`. The site password lets them comment under any name;
  the iteration password also lets them harvest the comments into the plan and ask Claude to implement it.
- **The agent** publishes the built site (with the Markdown for the editor), and `kea watch`, `list`, `reply`
  and `cycle` read and write the hub's record. The local `data/feedback/*.jsonl` stay an exact mirror.
- **Data** stays home unless chosen: files that may hold identifiers or that kea cannot inspect are flagged, and
  on the hub a file that stayed home has no download link and no preview.
- **One agent per project**: the hub keeps a lease. A second agent (another session, another machine) is refused
  until the first one's lease expires (2 h after its last action) or the owner says to take over (`kea lease take
  --force`). The same lease protects projects without a hub (`data/feedback/agent_lease.json`).
- **Secrets**: the hub stores only hashes of the key and passwords. Renew them with `kea hub passwords` and `kea hub
  rotate-key`. Wrong passwords are throttled (10 per 10 minutes per address). Cookies are per project and secure
  over https.
- Locally, `SITE_STEER_PASSWORD` in `.env` gives `kea serve` the same second password.

## Commands

`kea init | build | context <question|experiment> [--strict] [--mode review|local|public] [--out DIR] | pdf [--out FILE] [--no-pdf on build] | cite [--write] | serve [--install-service] | check | list [--unplanned] | show | reply | status | cycle
status|plan-updated|start|release | watch | apply-suggestion`

`kea context <question>` prints what an analysis run on that question must take into account: its answer so far,
conclusions, results and hypotheses, the premises, the decisions in force, every caveat on these pages and on the
method, open comments and gaps. `kea context <experiment>` lists the open work of an experiment.

`kea watch --deadline 3d` (or 12h, an ISO date/time, epoch seconds) exits 10 when a PI pressed Harvest, 20
when a PI pressed Implement and 30 at the deadline (comments alone never wake it); it prints a status line every hour (`--report-every`).
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

References are numbered B1, B2 … in order of first citation, shown in the text as tags like every other page (not superscript), and listed
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
overwritten. Resources may carry an `rrid:` (Research Resource Identifier); `kea rrid` checks each against the SciCrunch
resolver, and the PDF's Methods list the tools each step uses with their RRIDs, plus the questions, results and
conclusions that follow from the step. A figure page may set `pdf_width:` (`100%`, `12cm`) to override the automatic size.

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
