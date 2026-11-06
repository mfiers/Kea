---
name: kea
description: Set up and run a Kea site for a data analysis, and run the analysis through it. Typed Markdown pages in doc/ (questions, premises, hypotheses, steps, results, conclusions, caveats, figures, artefacts, terms, references) become a static site with code and data pages, a relations graph, change logs per agent run and semantic versions; readers comment or suggest edits; the agent runs two-phase review cycles (collect → freeze → implement → release). Use when the user says "use Kea", wants an explained, commentable project site, wants to review or discuss an analysis with others, asks to set up kea in a project, or works on a question in a project that has kea.yaml (read its context with kea context first).
---
# Kea

The tool does the work; this skill says when and how to use it. Never copy kea's code into a project.

## When the user says "use Kea" (start-up routine)

When Kea is not yet set up here (no `kea.yaml`), do these in order; do not start analysing before step 5:

1. **Outline.** Read what the project already says (README, CLAUDE.md, reports, the conversation). Ask only for
   what is still unclear, in one short round: the project's title and aim in a sentence or two; who will read the
   site (e.g. biologists, collaborators); the first experiment (a short folder name and its main question); the
   data it starts from; what is taken as given (premises); the author name(s) for the PDF.
2. **Structure.** Install and run `kea init` (below) with `--author`. Write the first pages: `doc/_summary.md`
   (the project's summary), the experiment's home page (its summary before the first `##`, then `## Scope`), one
   page per question (`question/`) and per premise (`premise/`). `make site` must report 0 problems.
3. **Hosting.** Ask how readers will reach the site, unless that is clear:
   - only the user on this machine: `localhost`;
   - colleagues on a trusted network or VPN: `make serve HOST=<ip>` (plain http; ask before opening firewall
     ports);
   - outside readers: `kea build --mode public --out DIR` on any static host (no comments).

   If in doubt, run `kea serve` on `127.0.0.1` and a free port (`kea.yaml` `port:`) as a background process of the
   session.
4. **Hand over.** Give the user the link and say that the password is `SITE_PASSWORD` in `.env` (never print it).
   Say what they can do on the site: read, select text to comment, or edit a section.
5. **Watch.** Start `kea watch --deadline 3d` in the background at once, and respond when it exits (see Review
   cycle). Tell the user it is running, and until when.

Then work on the first question (below).

## Working on a question (each analysis run)

The tree holds what earlier runs established. Read it before adding to it:

1. **Choose.** `kea context <experiment>` lists every question with its state, the open caveats, the decisions in
   force, open comments and gaps. If the user did not name a question, propose one from this list.
2. **Read the context.** `kea context <question>` prints the question's answer so far, its conclusions, results and
   hypotheses, the premises, the decisions in force, every caveat on these pages and on the method, open comments,
   and gaps. Then act on each part:
   - **Premises:** take them as given, or question one explicitly on its own page.
   - **Decisions:** use the method as it stands. To change it, write a new decision page that says what it
     replaces and why.
   - **Open caveats:** for each, decide whether this run addresses it (plan the check) or whether it limits the new
     result. In the second case, add the new result to its `limits:`.
   - **Addressed caveats:** make sure the new work does not reopen them.
   - **Earlier results:** compare with them; do not redo them silently.
   - **Comments:** answer, or take them into the plan.
3. **Fix the test before running it.** Write hypothesis pages with the test, the yardstick and the expectation, and
   `fixed_before_results: true`, and commit them before the test runs; the commit time is the record. Work that
   was not fixed in advance is labelled exploratory.
4. **Do the work reproducibly.** Write step and decision pages. Code goes in scripts with Makefile targets (one per
   step), with seeds and versions, and new versioned output files. Never analyse in the chat.
5. **Write what came out.**
   - **Result pages:** every number comes from a file named in `sources:`. Null results get pages too.
   - **Figures:** made by scripts, with full captions.
6. **Check the caveats again.**
   - A caveat this run dealt with: set it to `addressed` and link the step.
   - A new weakness: give it a new caveat page with `limits:`.
7. **Conclude.**
   - Write conclusions with `supported_by` / `opposed_by`.
   - Set each hypothesis's status and outcome.
   - Update the question's `answer:`, the experiment's summary and `doc/_summary.md` in the same commit.
8. **Check.**
   - Run `kea context <question>` again: every gap is closed, or explained on a page.
   - Let an independent reviewer (a subagent given the context and the new pages, not your conclusions) check every
     number against its source file.
   - `make site` must report 0 problems.
   - Write the run entry and commit with `Run:`.

One question per run where possible. A result that also bears on another question gets a relation (`answers:`),
not a copy.

## Set up (once per project)

Kea lives at https://github.com/mfiers/Kea (public). Install a **tagged** version, never an untagged branch, so
a project does not change when Kea does. Check the newest tag with `git ls-remote --tags https://github.com/mfiers/Kea.git`.

1. Install:
   - Python project with `pyproject.toml` (uv): `uv add "kea @ git+https://github.com/mfiers/Kea.git@vX.Y.Z"`.
   - Any other project (R, plain folder): `uv tool install git+https://github.com/mfiers/Kea.git@vX.Y.Z` once on
     the machine; the Makefile then calls `kea` directly (`kea init` detects this).
2. Ask the owner for the author name(s) for the PDF's title page unless you already know them, then run
   `kea init --title "<title>" --author "<name>" --experiment <first-experiment> --question "<question>"` in the project root. It
   never overwrites files; read what it reports. It adds `kea.yaml`, `doc/_schema.yaml`, `.env` with a random
   password, Makefile targets and a section in CLAUDE.md.
3. Tell the user the password is in `.env` (`SITE_PASSWORD`); never print it, never commit `.env`.
4. Serving:
   - `make site`, then `make serve` (localhost only, by default port 8210 from `kea.yaml`; pick a free port
     per project).
   - For other people: `make serve HOST=<ip>`. It is plain http, so use a trusted network or VPN, and ask before
     opening firewall ports.
   - Default for a project under active work: run `kea serve` (and `kea watch`) as background processes of the
     Claude session; the site is up while the session runs. Do not install a service unless the owner asks.
   - Only on request, for a site that must stay up without a session: `kea serve --install-service --host <ip>
     --port <port> --enable` writes and starts a systemd user service `kea-<project>.service` (needs
     `loginctl enable-linger` to survive logout).

## Writing pages

- One idea per page: `doc/<experiment>/<type>/<id>.md`, front matter `id, type, title, short, parent, status,
  relations, sources`; ids unique on the site. Types and allowed relations: `doc/_schema.yaml`.
- `result` = what a file shows (every number from a file named in `sources:` or an artefact page);
  `conclusion` = the interpretation, with `supported_by`/`opposed_by` results; `caveat` = what limits other pages
  (`limits:`); hypotheses carry `fixed_before_results: true|false` and are committed before their test runs.
- Figures: made by scripts from saved tables, new version per change; captions with title, take-home and per
  panel take-home / Shows / Method / Statistics (`kea build` notes missing parts).
- Terms (`aliases:`) are linked automatically from first use; reference pages carry the abstract fetched from
  Europe PMC / PubMed (never from memory) and why the paper is there.
- **Executive summaries**, written for a biologist (or whoever the reader is) who has five minutes:
  - the project: `doc/_summary.md` (with a single experiment, that experiment's summary serves);
  - each experiment: the text of its home page before the first `##` heading: what was asked, what was found, how
    sure. Below it the site lists every question with its answer; put Scope, data and other detail in later `##`
    sections;
  - each question: front-matter `answer:` (two or three plain sentences: the answer, how sure, the main limit).
    The build notes answered questions without one.
  Keep them current: update them in the same commit that changes a conclusion.
- **Links**: write `[[c-x]]`; the tag (icon + C1) is the link. In a list of pages write `- [[r-x]] one line`: the
  whole line becomes the link. `[[id|text]]` shows the text with the tag after it (only the tag links). A heading
  `### [[q-x]]` shows the question's tag and title. Run entries may link other runs: `[[2026-11-05-a]]`.
- Summary lines (`short:`) are written for the reader (e.g. biologists): one plain sentence with the finding and why
  it matters; no internal labels (P1, H5, W2) or test names; numbers only where they carry the message. The
  build notes summary lines with internal labels or more than ~45 words.
- A date in the text always comes with its release: "written 2026-11-04 (v0.1.0)".
- `make site` must report 0 problems.

## Builds

`kea build` (review, with comments), `kea build --mode local` (no comments, data links into the project folder,
for reading from disk), `kea build --mode public --out DIR` (no comments, no data, no previews of controlled
tables; for hosting elsewhere; check `_public_report.json`; run entries may quote comments, so read them first).

`kea pdf` (`make pdf`): one PDF of every page, typeset with Typst, into `report/pdf/` under a new name each time
(title, date, site version, commit).

- **Title page:** project summary, version, author (`author:` in `kea.yaml`), repository, Kea link. With several
  experiments page 2 summarises them; with one, the PDF reads as that experiment.
- **Order of each chapter:** at a glance (each question with its answer and conclusions), key terms, background
  (the home page after its summary), premises, methods, then per question its answer, a hypothesis table and the
  results with their figures, then conclusions and caveats.
- **Appendix:** hypotheses in full, data and figure files, the glossary, the references; then a standard
  "About this document".
- **No data-file contents.**
- **Without Typst** the `.typ` source is still written and the command exits 3 with install instructions. Offer
  to install Typst rather than working around it.
- **`kea build` adds the PDF to the site** with a home page link. It is recompiled only when its inputs change
  (source, images, Kea, Typst; the build says why); `--no-pdf` skips it.

The PDF is read on paper by people outside the review cycle. Keep review-process notes ("plan v0.4 #2", "Mark's
comment", thread ids) out of page bodies and summaries, or confine them to one short closing section; keep
hypothesis numbers in captions and titles current after renumbering. Look at a few rendered pages (figures, tables) after a large change to the pages.

## Every agent run

Pick a run id `YYYY-MM-DD-<letter>`; put `Run: <id>` in every commit; `Answers-comment: <thread>` when a commit
answers a comment; write `doc/_changes/<id>.md` (asked, found, changed, corrections, checked, not done).

## Review cycle

1. **Watch:** `kea watch --deadline 3d` (or 12h, an ISO date/time, epoch seconds) in the background (token-free;
   fast polling while readers are active; reports a burst once it has settled; a status line every hour; check it
   with `kea watch --status`). Exit 30: deadline reached, start it again if the owner still wants it. Exit 10: fold the new comments (and suggested edits, and direct edit
   commits) into `doc/_cycles/cycle-NNN.md`, with one `### N. title` item per change, the threads it answers, the
   kind of change and the proposed version (front matter `version:`). Commit, then run `kea cycle plan-updated
   --commit <sha>`. Reply to each thread with its item (`kea reply <thread> "…" --status planned`), run
   `make site`, and watch again.
2. **Freeze / Implement:** readers freeze (comments only on the plan) and press Implement once every comment is
   in the plan. Exit 20: run `kea cycle start` and `make site`, then implement every item. Suggested edits:
   `kea apply-suggestion <thread>`, then check every number against its source and commit with the reader as
   co-author. Never implement before Implement unless the owner asks in chat.
3. **Release:**
   - Reply to each thread with its commit (`--status page-changed --commit <sha>`).
   - Set the plan's `status: implemented` and `run:`.
   - Write the run entry and commit.
   - Run `kea cycle release --run <id> --commit <sha> --version X.Y.Z --kind major|minor|patch --reason "…"
     [--experiment NAME=X.Y.Z]`. It writes the git tags.
   - Run `make site`. Restart `kea serve` if kea itself changed.

   Version rules: MAJOR when a conclusion changes direction or is withdrawn, MINOR for new results or pages,
   PATCH for wording only. Before 1.0 a major change counts as minor.

## Adapting Kea on request (in flight)

Kea is small (about 4,000 lines of Python, no database, static HTML), and changing it at the reader's request is
part of the job, not a detour:

1. Decide where the wish belongs. If it is for this project only, use `kea.yaml` or the project's pages. If it
   would help every project, change Kea itself, in its own checkout or submodule, not in a copy.
2. Make the change with a test, run Kea's tests, and check the result in a browser at desktop and phone width.
3. Commit and push in the Kea repository, then update the project to it. A new tagged version is needed when
   other projects should get the change.
4. Rebuild the site and restart `kea serve` if server code changed (stop the old process by its exact PID). Add a
   line to the project's change log.
5. During a review cycle: a fix to something just delivered may be done at once. A new feature goes into the plan,
   unless the owner asks for it in chat.

## Scientific rules that the site makes visible

Label exploratory versus fixed tests; report null results like positive ones; state method, n, effect size,
correction for every test; check every number on a page against its file before a release.
