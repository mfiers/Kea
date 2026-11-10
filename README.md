<p align='center'><img src='branding/logo.png' alt='kea' width='520'></p>

# Kea

<!-- help:1-why -->

## What is Kea?

Break a data analysis into small, linked nodes: questions, hypotheses, steps, results, conclusions. You and your AI agent work through them one at a time, reviewing each before moving on.

The agent reads the nodes that bear on a question, takes one step along the route, writes it back as pages and stops for review. People read the pages as a website, comment on any sentence and approve or revise each step; the agent folds the comments in, release by release. The pages are Markdown files in the project's git repository; the site is static HTML, and a PDF of the same version is built beside it.

## Why

An analysis produces claims, and whether a claim holds depends on things that are hard to see: the file a number came from, the test that was run, what was assumed, when the hypothesis was written, and what changed since. In a report or a notebook that chain is not inspectable. The number is there but not its file; the hypothesis reads as if it came first; a premise was revised weeks ago and nothing downstream was looked at again.

An AI agent makes this worse. It produces more claims, faster, and the reasoning that connects them sits in a chat log nobody will read again.

Review has the same problem. Comments on a PDF or in an email thread lose their place: which version was commented on, what was done about it, and in which release.

Kea writes the chain down and keeps it checkable: every claim is a page, every page says what it rests on, every change is recorded, and a reader's comment is answered with the commit that dealt with it.

## Why small pages

One claim per page, so that each claim can be handled on its own. A page can be linked by a typed relation (this result supports that conclusion; this caveat limits it), cited by a permanent id that survives edits and renames, commented on, approved or dropped by a reader, rechecked when something it rests on changes, and versioned with the rest of the site.

The evidence chain becomes checkable because every link is written down. A result names the file every number comes from. A conclusion names the results for and against it, with a reason per link and a certainty. A hypothesis states its prediction and what would count as support, and whether that was written before or after the test. `kea check` reads the links as a graph on every build.

A page is also the right unit for an agent and for a reader. The agent works, is reviewed and corrected one page at a time. A reader with five minutes reads a question's answer and stops, or follows the links down to the file.

## What Kea adds

Claims linked to their evidence are not new: micropublications, discourse graphs, Octopus and nanopublications model them, and agent systems such as Kosmos keep a structured state of an analysis (see [Related work](https://github.com/mfiers/Kea/blob/main/doc/_site/related-work.md)). We found none of the following, combined, in those systems:

- a person's approval at each step of the route before the agent builds on it (`pace: guided`);
- hypotheses fixed before their test, recorded in the graph with the commit time as the record;
- recheck flags that run downstream when a page upstream changes;
- the agent's runs, change logs and review cycles tied to semantic versions of the whole graph;
- all of it as Markdown in the project's own git repository.

<!-- /help -->

<!-- help:2-progress -->

## How a project progresses

<!-- ROUTE -->

Every analysis follows one route, and each page is a stop on it: experiment → question → hypothesis → step → result → conclusion → the question's answer. Premises, decisions, caveats, figures, artefacts and resources feed in from the side.

- A question is proposed, and approved before anything is built on it.
- Hypotheses are written before the test, with a prediction and a criterion for support, and committed; the commit time is the record. That record lives in the project's own repository, so it is not a public preregistration: git history can be rewritten, and the repository is often private. Work not fixed in advance is labelled exploratory on its results and conclusions.
- Steps do the work from scripts (Makefile targets, seeds, versions) and make results; every number on a result page comes from a named file.
- Conclusions are drawn from results only, with the evidence for and against, a reason per link and a certainty. The question's answer and the summaries change in the same commit. The reason on each link is Toulmin's warrant (why this evidence bears on this claim); the certainty uses GRADE's four labels (high, moderate, low, very low), though Kea does not apply GRADE's rating method.
- After each run the caveats are read again: addressed by this run, or still limiting the new result.

One step at a time (`pace: guided`, the default of `kea init`). The agent takes one step along the route and stops for the owner's review: it proposes questions and waits; for an approved question it proposes hypotheses and planned steps and waits; it runs approved steps, writes the results and waits; it concludes from reviewed results. A page that waits carries a "waiting for approval" pill. The reader's verdicts on it are Approve (the next step may build on it), Revise (say what to change; it is rewritten and waits again) and Drop (remove it, with every page that rests only on it). On a settled page the verdicts are Confirm (keep it as it is; recorded on the page), Revise and Drop. Approval can also be given in the agent's chat; either way it is written on the page (`approved:`), and `kea check` refuses work built on unapproved pages.

What Kea checks on every build (`kea check`; `kea build --strict` fails on a problem): a conclusion rests on at least one result or figure, not on a hypothesis or a question; no conclusions support each other in a loop; a live conclusion does not rest on deprecated evidence; a confirmatory conclusion does not rest on exploratory results only; a hypothesis with an outcome names the result that tested it; a hypothesis fixed before its results states its prediction and criterion; every relation connects the right kinds of page; every linked page and file exists.

When a page upstream changes (a premise is revised, a result redone, a decision changed), every page that rests on it, directly or further down, gets a red "recheck" pill. The agent reads each against the change, updates it when it is even slightly affected, and records the check (`kea recheck`, ledger `doc/_checks.yaml`). A version is not released while pages wait for a recheck.

Versions. Each release is a semantic version and a git tag: MAJOR when a conclusion changes direction or is withdrawn, MINOR for new results or pages, PATCH for wording only; before 1.0 a major change counts as minor. Each page shows the release in which it last changed, so settled parts stand out from parts in flux. The site and the PDF are two views of one version.

<!-- /help -->

<!-- help:3-reading -->

## Reading a Kea site

Start at the top. With one experiment the site opens at the experiment's page: its summary, then every question with its answer in short. With more experiments the project page summarises them first. A question page leads with its answer so far, then its conclusions, results and hypotheses. Details are one click further down.

Every page has a type, shown as a coloured tag with an icon and a number (Q1, R2, C3; references show author and year). The tag is the link to the page; hover it for the page's one-line summary. In lists of pages the whole line is the link.

<!-- KINDS -->

| Type | What it is |
| --- | --- |
| Experiment | the experiment's home page: its summary, then every question with its answer in short |
| Premise | what the analysis takes as given, so a reader can question it |
| Question | what is asked; leads with its answer so far and the conclusions behind it |
| Hypothesis | what was expected, with its prediction and criterion, and whether it was written before its test |
| Step | what was done (the methods: data, tool, version, test, output files) |
| Decision | a choice made along the way, why, and the alternatives |
| Result | what a file shows; every number comes from a named file |
| Conclusion | what the results mean, with the evidence for and against and a certainty |
| Figure | a figure with its full caption, script and table |
| Artefact | a data file the analysis made, with checksum, preview and download |
| Resource | what the analysis takes from outside (a database, dataset, file or tool), with version, retrieval date and checksum |
| Caveat | what limits a result, conclusion or premise; open until a step addresses it |
| Term | a glossary entry; words with a dotted underline link to it |
| Reference | a paper, with its abstract and why it is cited |

On a page:

- The coloured bar on the left and the word above the title say the type. The page's own content (title, summary, text) is set in a serif face. Under the line "About this page" is what Kea knows about it: its permanent identifier (`kea:…`, which stays when the page is edited or moved, and `@…` for exactly this version, to cite), its sources, and its links to other pages as tables ("Tested by this step", "Supported by these results"), with the reason each link holds.
- A page reads in this order: its title, summary and text, as written, in a typewriter face; on a question, the answer so far; then its figures and data files under their own separator (one tab per figure or file when there are several; the take-home under each figure, the rest of the caption under "Shows, method and statistics"; a question or conclusion also shows the figures of the results behind it as a row of small images); then About this page. Under the text, conclusions and caveats are listed one per line; how the page was made (steps, data, sources) is folded under Provenance. "Changes to this page" lists one line per version; the exact changes are under History.
- Pills next to the title: the status (green: supported, done or answered; amber: open, planned, assumed or inconclusive; dark red: not supported, deprecated or dropped); "exploratory"; on a hypothesis "written before its test" or "written after results"; on a conclusion its certainty; "waiting for approval", "approved", "confirmed", "recheck"; and the release in which the page last changed.
- The menu bar: the kea head goes home, then project / experiment / page. Map (the experiment as a tree) with Relations (the graph of links) and Objects (every page in one table to search, filter and sort; Data and Code under it); Plan (the current review cycle); History (what changed per agent run; review cycles; all comments); PDF (the analysis as one document to read; with all records under it); Help.

<!-- /help -->

<!-- help:4-reviewing -->

## Comments and the review cycle

On a site served with comments, sign in with the site password and your name, or with ORCID on a hub that offers it. Then:

- Select any text for Comment, Edit (just that passage) or a one-click tag: a request for the next run (explain, expand, shorten, delete, challenge, needs source) or the manuscript section the passage belongs in.
- The buttons at the bottom right act on the whole page: Comment, Edit, the verdicts (Approve, Revise, Drop; Confirm on a settled page), Propose (the next step of the reasoning for this kind of page: a hypothesis on a question, a caveat on a result, a control on a step, …), Next run and Manuscript.
- The pencils in the left margin edit the title or summary in place; the pencil after a section heading edits that section. Every edit is saved as a suggestion, shown as a diff, and goes into the next plan.

Nothing changes until the comments are harvested:

1. Comment. Readers comment, tag, edit and propose for as long as the round takes. The agent waits (`kea watch`) without reading them; comments alone never wake it, so a long round costs nothing.
2. Harvest. A PI presses "Harvest comments". The agent folds every comment into one plan of numbered items (what will change, on which pages, the version it will make) and answers each comment with its item. Approve, Revise and Drop on pages waiting for approval are applied at the harvest itself, so the route never waits for an Implement. The plan stands until the next harvest; the plan page counts the comments made since, and "Harvest again" adds them.
3. Implement. A PI presses "Implement the plan". Comments pause. The agent changes the pages item by item, checks every number against its file, works through the rechecks, commits each change and answers each comment with its commit: page changed, answered, or won't fix with the reason.
4. Release. A new version and git tag, with the run's change log. Open pages reload and comments reopen. Comments left out of the plan stay for the next cycle. The History page links each comment to its plan item, commit and pages.

The plan page shows the agent's session (watching, with the time since its last heartbeat; working; ended; stopped unexpectedly) and offers Harvest and Implement to PIs.

<!-- /help -->

Links: [code on GitHub](https://github.com/mfiers/Kea) · [web page](https://mfiers.github.io/Kea/) · [how to use it](#how-to-use-it) · [related work](doc/_site/related-work.md) (micropublications, discourse graphs, Octopus, nanopublications, PROV).

## How to use it

Kea is meant to be run by an AI coding agent: Claude Code, or another harness that reads a skill file and runs shell commands. Give the agent the skill (`skill/SKILL.md`) and say "use Kea" in your project. It installs a tagged version of Kea, asks for a short outline (title, first experiment, data, premises, author) unless that is already clear, writes the first pages, builds the site, agrees with you on where to host it, gives you the link and starts watching for comments. Then it stops: you read and approve the questions on the site, and it takes the next step. Before each run it reads what the site already holds for the question (`kea context`).

Running Kea by hand is possible, but keeping pages, hypotheses, change logs and cycles consistent is the agent's job.

For Claude Code, the skill is one file:

```
mkdir -p ~/.claude/skills/kea && curl -fsSL https://raw.githubusercontent.com/mfiers/Kea/v1.25.1/skill/SKILL.md -o ~/.claude/skills/kea/SKILL.md
```

Other agents: put `skill/SKILL.md` where the agent reads its instructions, for example in the project's agent instructions file.

## Install

Kea is not on PyPI; install it from this repository with [uv](https://docs.astral.sh/uv/) (it fetches Python ≥ 3.11 if needed). Always name a tag (see [tags](https://github.com/mfiers/Kea/tags)), so a project does not change when Kea does. The agent normally does this itself.

```
# as a command on this machine (any project; also the hub host): puts `kea` in ~/.local/bin
uv tool install git+https://github.com/mfiers/Kea.git@v1.25.1
kea --help

# or as a dependency of a Python/uv project (pinned in its uv.lock); run it as `uv run kea …`
uv add "kea @ git+https://github.com/mfiers/Kea.git@v1.25.1"

# or once, without installing
uvx --from git+https://github.com/mfiers/Kea.git@v1.25.1 kea --help
```

- Upgrade: run the same command with the new tag (`uv tool install --force git+…@vX.Y.Z`, or `uv add` again). `uv tool upgrade kea` does not move a pinned tag.
- Remove: `uv tool uninstall kea` (or `uv remove kea`).
- If `kea` is not found after `uv tool install`, run `uv tool update-shell` and open a new shell.
- Needs `git` (for the install, the change logs and the versions). Optional: [Typst](https://github.com/typst/typst/releases) for the PDF (see [PDF](#pdf)).
- The agent skill is separate: copy `skill/SKILL.md` to `~/.claude/skills/kea/SKILL.md` (Claude Code) from the same tag, as under [How to use it](#how-to-use-it).

## Reference

### What the agent runs in a project

```
uv add "kea @ git+https://github.com/mfiers/Kea.git@v1.25.1"     # a Python/uv project
#   or, for any other project:  uv tool install git+https://github.com/mfiers/Kea.git@v1.25.1
kea init --title "My project" --author "Your Name" --experiment first-experiment --question "What does it ask?"
make site && make serve                                       # the password is in .env
kea watch --deadline 3d                                       # waits for Harvest or Implement
kea serve --install-service --host <ip> --port 8210 --enable   # optional: keep it running (systemd user unit)
```

`kea init` never overwrites a file; it adds `kea.yaml` (with `pace: guided`), `doc/_schema.yaml`, a first experiment, `.env` with a random `SITE_PASSWORD`, Makefile targets and a section in `CLAUDE.md`. `kea new experiment <name> --title "…"` adds an experiment; from two experiments on the site starts at the project page and needs `doc/_summary.md`.

### Pages and the site

- Pages live in `doc/<experiment>/<type>/<id>.md` with YAML front matter: `id`, `uid` (permanent, minted by `kea check --fix`), `type`, `title`, `short`, `parent`, `status`, the relations (`supports`, `opposes`, `supported_by`, `opposed_by`, `answers`, `tests`, `limits`, `made_by`, `uses`, `cites`, …) and `sources`. Types, statuses and allowed relations are in `doc/_schema.yaml`; `kea check` validates every page against it. A relation can carry its reason: `supported_by: [{id: r-x, because: "…"}]`.
- Links in text: `[[id]]` shows the page's tag; `[[id|text]]` shows the text with the tag after it; `[[code:path#symbol]]` and `[[data:path]]` link code and data. A heading `### [[q-x]]` shows the question's tag and title.
- Extra fields: hypotheses `fixed_before_results`, `prediction`, `criterion`; results and conclusions `analysis: confirmatory | exploratory`; conclusions `certainty` (high, moderate, low, very_low) with `certainty_because`; caveats `kind` (internal, external, construct, statistical, other) and `limits`; resources `kind`, `url`, `version`, `retrieved`, `sha256`, `size`, `local`, `access`, `licence`, `rrid`, `accession` or `dataset_id`, `part_of`. A source (a database, catalog, API or MCP server) is one resource; each record taken from it (a dataset, a study, a file) is a resource of its own, part of the source.
- Terms carry `aliases:` and are linked at their first use in each section, in prose and table cells (`link: every` links every use, case-sensitive); a term or aliased resource page lists where it is used. References carry `pmid:`/`doi:`; `kea cite --write` fills `citation:` from Europe PMC (Crossref for DOIs it lacks). `kea rrid` checks every resource's RRID against SciCrunch.
- Executive summaries at three levels: the project (`doc/_summary.md`), each experiment (its home page's text before the first `##`) and each question (`answer:`, two or three sentences). Figure captions: title, take-home, then per panel take-home / Shows / Method / Statistics (the build notes missing parts).
- The site (`kea build`, `make site`) has: the node pages with their connections; per experiment a Map (tree), Relations (interactive graph) and Objects (one table of every page, built for thousands); code pages with line anchors; artefact pages with preview, checksum and download; a Data page of every file the pages refer to; one change-log page per agent run and a page per commit; a History page of releases and review cycles; a Help page; site-wide pages from `doc/_site/*.md`; the PDF when Typst is installed. Every page shows the release in which it last changed. A grey pill in the menu bar names the Kea version that built the site.
- Modes: `kea build` (review, with comments), `kea build --mode local` (no comments; data links into the project folder, for reading from disk), `kea build --mode public --out DIR` (no comments, no data files, no previews of controlled tables; for any static host; `_public_report.json` lists what was left out). `--no-pdf` skips the PDF.
- Comments (`kea serve`): a shared password (`SITE_PASSWORD` in `.env`) with a free-form name; `SITE_STEER_PASSWORD` gives a second password for Harvest and Implement (without it every signed-in reader may). Comments, tags, suggested edits and proposals go to an append-only log, `data/feedback/events.jsonl`; the cycle state to `data/feedback/cycle.jsonl`. Both are committed. Tags come from `feedback/tags.py` plus `tags:` in `kea.yaml`; `free_tags: false` turns off tags outside the list.
- One agent per project: `kea lease take` at the start of a session; a second agent is refused until the lease expires (2 h after its last action) or is taken over (`--force`). The lease is in `data/feedback/agent_lease.json`, or on the hub.

### Commands

```
kea init [--title T] [--author A] [--experiment E] [--question Q] [--port N]
kea new experiment <name> --title "…"
kea build [--strict] [--mode review|local|public] [--out DIR] [--no-pdf]
kea serve [--host H] [--port P] [--install-service [--enable]]
kea check [--fix]                   validate doc/ and the graph; --fix mints missing uids
kea context <question|experiment>   what a run must take into account; the next step on the route
kea recheck --list | <id> … --because "…"
kea drop <id>                       what a Drop of that page removes (lists only)
kea pdf [--out FILE]
kea cite [--write] [ID …]           citations from Europe PMC
kea rrid                            check RRIDs against SciCrunch
kea list [--unplanned] | show | reply | status | tags [names…]
kea cycle status | plan-updated --commit SHA | start | release --version X.Y.Z --kind major|minor|patch --reason "…"
kea watch --deadline 3d|12h|<ISO>|<epoch> [--report-every S] | kea watch --status
kea apply-suggestion <thread>
kea lease status | take [--force] | release
kea publish [--files]
kea hub init | add | list | passwords | rotate-key | remove | public <name> on|off | users [list|approve|role|block] | serve
```

`kea context <question>` prints what an analysis run on that question must take into account: the next step on the route, its answer so far, conclusions, results and hypotheses, the premises, the decisions in force, every caveat on these pages and on the method, open comments and gaps. `kea context <experiment>` lists the open work of an experiment.

`kea watch --deadline 3d` (or 12h, an ISO date/time, epoch seconds) exits 10 when a PI pressed Harvest, 20 when a PI pressed Implement and 30 at the deadline; comments alone never wake it. It prints a status line every hour (`--report-every`) and writes a heartbeat the hub reads. `kea watch --status` says whether a watcher is running and when it last looked.

### kea.yaml

All keys are optional.

```
title: Trajectories                 # site name in the menu bar
heading: "Trajectories: …"          # heading of the site home
author: Mark Fiers                  # author(s) on the PDF's title page
repository: https://github.com/x/y  # default: the git remote origin
pace: guided                        # one step along the route at a time (kea init writes it); free turns the gate off
port: 8210                          # kea serve
host: 127.0.0.1
site_dir: report/site               # the built site (never edited by hand)
feedback_dir: data/feedback         # events.jsonl, cycle.jsonl, server log, watcher heartbeat
code_paths: [src/, tests/]          # folders that get code pages
code_files: [Makefile]              # single files that get code pages
typst: /path/to/typst               # default: typst on PATH
tag_prefix: site/                   # release tags <prefix>vX.Y.Z, for a repository whose plain tags mean something else
changes_since: 68791ab              # commit pages and the change log start after this commit
tags: [{name: abstract, group: manuscript, task: false}]   # more tags, or changed ones
free_tags: true                     # readers may add tags outside the list
cookie_salt: <text>                 # default "kea-site:<project folder name>"
remote: {url: …, project: …}        # a Kea hub (below)
```

### Hosting on a Kea hub

One server hosts the sites of many projects and collects their comments, while each project's agent works on its own machine. The hub runs on any Linux host behind an https reverse proxy (Caddy, nginx); kea talks to it only over https.

```
# on the hub
kea hub init --dir /srv/kea-hub --url https://kea.example.org
kea hub add trajectories --title Trajectories    # prints the project key, site password, iteration password
kea hub serve --host 127.0.0.1 --port 8300       # behind the proxy, e.g. Caddy: kea.example.org { reverse_proxy 127.0.0.1:8300 }
```

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
kea publish                          # after every build: sends only files the hub lacks, in resumable chunks
```

- Readers open `https://kea.example.org/p/trajectories/`. The site password lets them comment under any name; the iteration password also lets them harvest the comments into the plan and ask the agent to implement it.
- The agent publishes the built site (with the Markdown for the editor), and `kea watch`, `list`, `reply` and `cycle` read and write the hub's record. The local `data/feedback/*.jsonl` stay an exact mirror.
- Data stays home unless chosen: files that may hold identifiers (donor, subject, sample … columns) or that kea cannot inspect (h5ad, parquet, npz) are flagged and go up only when named in `upload_include`. On the hub a file that stayed home has no download link and no preview.
- One agent per project: the hub keeps the lease. A second agent (another session, another machine) is refused until the first one's lease expires (2 h after its last action) or the owner says to take over (`kea lease take --force`).
- Secrets: the hub stores only hashes of the key and passwords. Renew them with `kea hub passwords` and `kea hub rotate-key`. Wrong passwords are throttled (10 per 10 minutes per address). Cookies are per project and secure over https.
- Sessions: the hub watches each project's agent through the heartbeats of `kea watch`. A watcher that stops on purpose (to plan, to implement, or at its deadline) says so in a last heartbeat; one that falls silent without saying why, while its deadline is still ahead, counts as stopped unexpectedly (a crash, a closed terminal, a sleeping machine, a lost network). The plan page shows the session's state and the time since the last heartbeat; PIs get a banner on every page. With `notify_url: https://ntfy.sh/<your-topic>` in `hub.yaml` the hub also posts a message when a session stops unexpectedly and when it is back (a plain-text POST with Title and Click headers; any webhook works). `kea hub list` shows each project's session.
- Logging: `kea hub serve --log events` prints one line on stderr per publish, lease change, sign-in, refused key, unknown site and reader action (comment, tag, harvest, implement); `--log requests` adds every request. Query strings are never logged, because sign-in codes travel in them.
- ORCID sign-in instead of shared passwords (optional). Register a client at orcid.org (Developer tools; redirect URI `https://example.org/auth/orcid/callback`), give the hub `KEA_ORCID_CLIENT_ID` and `KEA_ORCID_CLIENT_SECRET` in its environment, and approve readers with `kea hub users approve <orcid> [role] [--project name]` (`kea hub users` lists who asked, and for which project). A reader signs in once; every other project site of the hub then lets them in without a click (the hub hands its session over with a one-time code, so no cookie is shared between project subdomains), and Sign out on any site signs out of all. Comments and verdicts carry the reader's ORCID iD. Roles, per project or for all: auditor (reads the site and its comments, writes nothing), reviewer (comments, tags, suggests edits; the default), PI (also harvests the comments into the plan and asks the agent to implement it), director (everything a PI may; the project's lead). The names used before 1.19 (reader, commenter, steerer, owner) still work on the command line and in an existing `users.json`. The project passwords keep working; with ORCID on, a project's login page shows the ORCID button first and folds the shared-password form under "Sign in with a project password". The hub's own address (`https://example.org/`) is a landing page: visitors see what the hub is, a Sign in with ORCID button and the public projects; a signed-in reader sees their projects with their role in each, the projects waiting for approval, the other public projects and Sign out.
- Public projects (optional): `kea hub public <name> on` makes a project's pages, PDF and `/id/` links readable without a login; the comments, the review cycle and uploaded data files still need a sign-in, and visitors see a "Sign in to comment" button. `kea hub public <name> off` closes it again; `kea hub list` shows which projects are public.
- Subdomains (optional): put `project_domain: example.org` in the hub's `hub.yaml` and give the proxy a wildcard certificate for `*.example.org`; project `trajectories` is then read at `https://trajectories.example.org/`, old `/p/trajectories/` links redirect there, and agents keep using `https://example.org` in `remote.url`.
- Permanent ids: every page has a `uid:` (minted by `kea check --fix`); `https://example.org/id/<uid>` finds it on any project of the hub, and `…/id/<uid>@<version>` shows a cited version even after later edits.
- Locally, without a hub, `SITE_STEER_PASSWORD` in `.env` gives `kea serve` the same second password.

### PDF

`kea pdf` (or `make pdf`) puts every page into one PDF, ordered for a reader on paper. The title page has the project's summary, its version (the version of the pages; the site and the PDF are two views of it), the author (`author:` in `kea.yaml`), the repository (`repository:`, or the git remote) and a link to Kea. With more than one experiment, page 2 summarises each experiment and each is a chapter; with one, the PDF reads as that experiment. Then:

- *At a glance*: every question with its answer in short and its conclusions, each conclusion in full once, and the open caveats;
- background and scope, premises;
- one part per question: a table of its hypotheses, then the results, each with its figures right under its summary (take-home once, then Shows / Method / Statistics);
- conclusions, caveats and methods (steps, each followed by its decisions);
- closing chapters: overview of all pages (one table per kind: tag, one line, status, question, linked pages), hypotheses in full, data and resources (resources O1 … with version, retrieval date, checksum and local copy; data files; figure files), the glossary (terms T1 …, then groups such as *Genes*), the references, and what changed (releases with kind, plan and commit; runs with their commits).

References are numbered B1, B2 … in order of first citation, shown in the text as tags like every other page (not superscript), and listed like a journal's reference list from each page's `citation:` (`kea cite --write` fills it from Europe PMC, Nature style). Full names read as the kind in its colour followed by the tag (Question [Q1]); lists of pages carry the status and page number at the end of each line. Figures are printed at their own size (from the PNG's dpi), at most the text width and 19 cm high; the build notes figures it has to shrink below 80 %. A figure page may set `pdf_width:` (`100%`, `12cm`) to override the automatic size. The Methods list the tools each step uses with their RRIDs, plus the questions, results and conclusions that follow from the step.

`kea build` puts two PDFs on the site: the reader's copy (the story, the glossary and the references) and the complete one with the closing chapters (overview tables, hypotheses in full, data and resources, figure files); a page that is only in the complete copy is named in the reader's without a page number. A table with seven or more columns in a page's text gets a landscape page of its own.

A standard closing chapter, *About this document*, explains the parts present, the page types (in the site's colours), the numbers, the statuses and the page references. Every link to a page shows its page number.

It leaves out comments, plans, code listings, the relations graph (the overview tables are its printed form) and the contents of data files, so no donor-level rows reach the PDF. It needs [Typst](https://github.com/typst/typst/releases) (a single binary; or `typst:` in `kea.yaml`). Without it the `.typ` source is still written. Output goes to `report/pdf/<title>_<date>_<version>_<commit>.pdf` and is never overwritten.

`kea build` also puts the PDF into the site, linked from the menu bar, when Typst is installed. It is recompiled only when something in it changes: the cache key (`report/pdf/_cache/`) covers the whole Typst source, every image file's bytes, the Kea version and the Typst version, and the build prints why it reused or rebuilt the PDF. `--no-pdf` skips it.

### Small enough to change while you use it

Kea is deliberately small: about 11,500 lines of Python and 1,900 lines of its own JavaScript and CSS; nine Python dependencies, with three JavaScript libraries copied in at fixed versions; no database (the pages are Markdown in git, and comments and review-cycle state are append-only JSON-lines files); plain static HTML, rebuilt in seconds.

So the agent that runs the review cycle can also change the tool during the session, when a reader asks for it. In the project where Kea was built, the menu bar, comment states per version, static builds for public hosting, the in-page editor and the History page all came from reader requests and were added within the same session, most within minutes. A wish for one project goes into `kea.yaml` or the project's own pages. A wish that would help every project goes into Kea, with a test, as a new tagged version.

### Third-party files (copied, pinned)

Recogito text-annotator 4.3.7 (BSD-3), Cytoscape.js 3.30.2 (MIT), marked 12.0.2 (MIT); versions and checksums in `src/kea/feedback/static/VENDOR.md` and `src/kea/docsite/static/README.md`.

### History

Developed inside the trajectories project (KU Leuven) in November 2026 (`src/docsite`, `src/feedback`, then `packages/kea`) and moved here on 2026-11-05. This repository previously held an unrelated older Kea (a helper to make command line tools more intelligent, last PyPI release 0.0.28); its history is kept: tag `legacy-0.0.28`, branches `master` and `prefix_mode`.

### Tests

`uv run pytest` (unit tests, the comment server, the review cycle, the graph rules, the hub, and an example project built from scratch).

### About

Kea was developed by Mark Fiers together with Claude (Anthropic), an AI coding assistant. Mark directed the design and tested it in use; much of the code and text was written by Claude. Treat Kea as research software: check what it builds before you rely on it.
