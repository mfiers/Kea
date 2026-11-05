---
name: kea
description: Set up and run a Kea site for a data analysis (Kea = Knowledge, Evidence, Argument). Typed Markdown pages in doc/ (questions, premises, hypotheses, steps, results, conclusions, caveats, figures, artefacts, terms, references) become a static site with code and data pages, a relations graph, change logs per agent run and semantic versions; readers comment or suggest edits; the agent runs two-phase review cycles (collect → freeze → implement → release). Use when the user wants an explained, commentable project site, wants to review or discuss an analysis with others, or asks to set up kea in a project.
---
# Kea

The tool does the work; this skill says when and how to use it. Never copy kea's code into a project.

## Set up (once per project)

Kea lives at https://github.com/mfiers/Kea (public). Install a **tagged** version, never an untagged branch, so
a project does not change when Kea does. Check the newest tag with `git ls-remote --tags https://github.com/mfiers/Kea.git`.

1. Install:
   - Python project with `pyproject.toml` (uv): `uv add "kea @ git+https://github.com/mfiers/Kea.git@vX.Y.Z"`.
   - Any other project (R, plain folder): `uv tool install git+https://github.com/mfiers/Kea.git@vX.Y.Z` once on
     the machine; the Makefile then calls `kea` directly (`kea init` detects this).
2. `kea init --title "<title>" --experiment <first-experiment> --question "<question>"` in the project root. It
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
- Summary lines (`short:`) are written for the reader (e.g. biologists): one plain sentence with the finding and why
  it matters; no internal labels (P1, H5, W2) or test names; numbers only where they carry the message. The
  build notes summary lines with internal labels or more than ~45 words.
- A date in the text always comes with its release: "written 2026-11-04 (v0.1.0)".
- `make site` must report 0 problems.

## Builds

`kea build` (review, with comments), `kea build --mode local` (no comments, data links into the project folder,
for reading from disk), `kea build --mode public --out DIR` (no comments, no data, no previews of controlled
tables; for hosting elsewhere; check `_public_report.json`; run entries may quote comments, so read them first).

## Every agent run

Pick a run id `YYYY-MM-DD-<letter>`; put `Run: <id>` in every commit; `Answers-comment: <thread>` when a commit
answers a comment; write `doc/_changes/<id>.md` (asked, found, changed, corrections, checked, not done).

## Review cycle

1. **Watch:** `kea watch --deadline <epoch>` in the background (token-free; fast polling while readers are active;
   reports a burst once it has settled). Exit 10: fold the new comments (and suggested edits, and direct edit
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

## Scientific rules that the site makes visible

Label exploratory versus fixed tests; report null results like positive ones; state method, n, effect size,
correction for every test; check every number on a page against its file before a release.
