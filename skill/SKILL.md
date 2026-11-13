---
name: kea
description: Set up and run a Kea site for a data analysis, and run the analysis through it. Typed Markdown pages in doc/ (questions, premises, hypotheses, steps, results, conclusions, caveats, figures, artefacts, resources, terms, references) become a static site with code and data pages, a relations graph, change logs per agent run and semantic versions; readers comment or suggest edits; the agent runs review cycles (collect → harvest into a plan → implement → release). Use when the user says "use Kea", wants an explained, commentable project site, wants to review or discuss an analysis with others, asks to set up kea in a project, or works on a question in a project that has kea.yaml (read its context with kea context first).
---
# Kea

The tool does the work; this skill says when and how to use it. Never copy kea's code into a project.

## When the user says "use Kea" (start-up routine)

**One agent per project, always.** Before any other step in a project that has `kea.yaml`, run `kea lease take`.
If it refuses (exit 2: another agent works on this project), stop: tell the user which session holds it and do
nothing else in the project. Take over with `--force` only when the user says that session is finished. Every
command that writes (reply, status, cycle, watch, apply-suggestion, publish) checks the lease too.

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
   - readers anywhere, with comments: a **Kea hub** (below, "Hosting on a Kea hub");
   - outside readers without comments: `kea build --mode public --out DIR` on any static host.

   If in doubt, run `kea serve` on `127.0.0.1` and a free port (`kea.yaml` `port:`) as a background process of the
   session.
4. **Hand over.** Give the user the link and say that the password is `SITE_PASSWORD` in `.env` (never print it).
   Say what they can do on the site: read, select text to comment, or edit a section.
5. **Watch.** Start `kea watch --deadline 3d` in the background at once, and respond when it exits (see Review
   cycle). Tell the user it is running, and until when.

Then **stop**: ask the owner to read the questions and premises on the site and approve them (see "Pace"). Do not
write hypotheses, plan steps or analyse anything yet.

## One experiment, or more

With one experiment the site starts at its page (`index.html` sends readers there; no project level in the menu
bar; the project's title stays). `doc/_summary.md` is optional then, shown above the experiment's text only when
it says more than the experiment's own summary. To add an experiment (when the owner asks, or approves a reader's
"Propose ▸ an experiment"): `kea new experiment <name> --title "…"`, write its summary and scope, and in the same
step `doc/_summary.md`, the project's summary across the experiments (`kea check` requires it from two
experiments on); the site's start becomes the project page again, and no existing address changes. Under
`pace: guided` a new experiment waits for approval (`approved:` on its home page) before questions go under it;
when the owner gave the outline for the first experiment in chat, record that approval on its home page.

## Pace: one step along the route, then stop

Kea's route: experiment → questions (and premises) → hypotheses and planned steps → results → conclusions. Unless
the owner explicitly asks you in this conversation to go further ("go ahead and run it", "do the whole question"),
do **only the next step** for the page you are working from, write it as pages, build and publish the site, and
**stop**: tell the owner which pages to read and what to approve, with the links. Never plan ahead or run ahead
because the next step seems obvious; the owner reading each step is the point.

| You are at | Do | Do not |
| --- | --- | --- |
| an experiment | propose questions (and premises): question pages, status open | write hypotheses, steps or code |
| an approved question | propose hypotheses (prediction, criterion, fixed_before_results: true) and planned steps (status planned, with decisions) | run anything, write code beyond a sketch on the step page |
| approved planned steps | run them reproducibly (scripts, Makefile targets) and write result pages and figures | conclude, set hypothesis outcomes, update the answer |
| reviewed results | write conclusions (supported_by with because:, certainty), hypothesis outcomes, caveats, the answer | start the next question |

**Approval** is a signature recorded on the page: `approved:` is a list, one entry per person,
`- {by: <name>, orcid: <iD>, date: <ISO date>, version: <page version>, how: chat|site}` (an older single mapping
still counts). The owner approves in this conversation (name the pages they approved; "looks good" about one
question approves that question only; `how: chat`), or a reader presses on the site:

- **Approve**: a sign-off only (the reader's name and the version they read). Applied at the next harvest (add the
  signature, change no claim), not deferred to Implement; it asks for no further work.
- **Approve & go** (needs the right to steer): the same signature, plus a request to take that page's next step
  now; the button says which (propose questions, write the plan, plan its steps, run the step, draw conclusions).
  `kea watch` stops with exit 40; see the review cycle.
With `pace: guided` in `kea.yaml` (the default of `kea init`) `kea check` enforces this: hypotheses or steps under an
unapproved question, a step in progress or done without approval, and conclusions from unreviewed results are
problems. `kea context` starts with "Next step on the route": what to do now, or what waits for the owner.
`pace: free` turns the gate off (only when the owner asks for it); even then, stop between steps unless told not to.

## Working on a question (each analysis run)

The tree holds what earlier runs established. Read it before adding to it. The steps below are the whole route
for one question; under the pace rule (above) one run does only the step that is next, then stops for review:
step 3 (with the step pages of step 4) is one stop, running the steps and writing results (4–5) the next, and
concluding (6–8) the one after.

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
3. **Fix the test before running it.** Write hypothesis pages with the test, `prediction:` (what you expect to observe) and `criterion:` (what result counts as support, what counts against, and what is inconclusive), and `fixed_before_results: true`, and commit them before the test runs; the commit time is the record. Work that was not fixed in advance gets `analysis: exploratory` on its results and conclusions.
4. **Do the work reproducibly.** Write step and decision pages. Code goes in scripts with Makefile targets (one per
   step), with seeds and versions, and new versioned output files. Never analyse in the chat.
5. **Write what came out.**
   - **Result pages:** every number comes from a file named in `sources:`. Null results get pages too.
   - **Figures:** made by scripts, with full captions.
6. **Check the caveats again.**
   - A caveat this run dealt with: set it to `addressed` and link the step.
   - A new weakness: give it a new caveat page with `limits:`.
7. **Conclude.**
   - Write conclusions with `supported_by` / `opposed_by`, each link with its reason: `supported_by: [{id: r-x, because: "…"}]` (why this result bears on this conclusion), and `certainty:` (high, moderate, low, very_low) with `certainty_because:`.
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
     the machine; the Makefile then calls `kea` directly (`kea init` detects this). To upgrade, run it again
     with `--force` and the new tag (`uv tool upgrade` does not move a pinned tag).
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

- **Permanent ids:** every page has a `uid:` (26 characters, minted once, never edited). After creating pages run `kea check --fix`, which writes one into every page without it; never copy a `uid:` to another page or change one. Cite a page from outside the site as `kea:<uid>`; `/id/<uid>` on the site redirects to it.
- **No hard line wraps in `doc/`:** one line per paragraph and per list item. Readers edit pages in the site's
  editor, where wrapped lines look broken; the renderer joins them anyway.
- One idea per page: `doc/<experiment>/<type>/<id>.md`, front matter `id, type, title, short, parent, status,
  relations, sources`; ids unique on the site. Types and allowed relations: `doc/_schema.yaml`.
- `result` = what a file shows (every number from a file named in `sources:` or an artefact page);
  `conclusion` = the interpretation, with `supported_by`/`opposed_by` results (each with `because:`) and `certainty:`;
  `caveat` = what limits other pages (`limits:`, and `kind:` internal, external, construct, statistical or other);
  `premise` = what the analysis takes as given (data, methods, earlier findings), so a reader can question it;
  hypotheses carry `fixed_before_results: true|false`, `prediction:` and `criterion:`, and are committed before
  their test runs. `analysis: confirmatory | exploratory` on results and conclusions (not in `status:`).
  Prefer a typed relation over `relies_on` (a step that follows a decision: `decided_in`).
- **Steps read as the Methods section of a paper**: what was done to which data (dataset, version, n of donors and
  cells), with which tool and version (package, function, parameters, seed), which test and why (unit, sidedness,
  correction, number of permutations), and which files came out. Name the script and its Makefile target. A step
  that says only "ran the analysis" is not finished.
- Figures: made by scripts from saved tables, new version per change; captions with title, take-home and per
  panel take-home / Shows / Method / Statistics (`kea build` notes missing parts). Make figures at their printed
  size (at most 16.6 cm wide, 19 cm high, fonts 6–8 pt, with the PNG's dpi set): the PDF prints them at that size
  and the build notes figures it has to shrink below 80 %. Start the caption with the take-home as one bold line: the site and the PDF show it once,
  under the image, and fold the rest (Shows / Method / Statistics).
- A page's figures (`shown_in:`, or figures under it) and data files (`from_artefact:`, artefacts under it, artefact files in `sources:`) are shown after its text (and a question's answer) under a Figures (and files) separator, with a tab per item when there are several; a conclusion or question also shows the first figure of each result behind it. In the PDF a result's figures follow its summary. To place a figure inside the text instead, put `![[f-…]]` on a line of its own.
- An experiment page has no figures or files of its own: an artefact or figure under the experiment, or linked to it, and `sources:` or `from_artefact:` on the experiment page are problems (`kea check`); put them under the step that made them or the result that uses them. After its text the experiment page has tabs: "Questions" (one line each), "Answers so far" (each question's `answer:` with links to its conclusions, so the answer must say what the conclusions say), "About this page" (its hypotheses, steps, results and conclusions), Changes and Comments. Resources, terms and references are not listed under "About this page" on any page (Map → Resources, Terms, References has them; a resource that made a page stays in its Provenance).
- Inline data links (`[[data:path]]`) render as a short chip with the path on hover; give the chip a name with `[[data:path|counts table]]`. A resource with `aliases:` (a dataset id) is followed by its title at its first mention in a page's prose.
- Terms (`aliases:`) are linked automatically at their first use in each section (each `##` heading starts a new one), in prose and in table cells (not table headers), and numbered T1, T2 … in glossary order. Terms that
  name entities (genes, proteins, cell types) get `group: Genes` (etc.); the glossary lists each group after the
  key terms (titles that look like gene symbols go under Genes without it).
  `link: every` links every use of a term on a page instead of the first (genes a reader looks up anywhere);
  it matches the case as written, so a gene APP does not link "app". A term page lists the pages that use it.
  Start the text with the definition: when it opens with the `short:`, the site does not repeat it in a box.
- **Resources** (`resource/`, numbered O1, O2 …): everything the analysis takes from outside: a database or API, an
  MCP server, a dataset on a server, an uploaded or downloaded file, software with its version. Front matter:
  `kind` (database | api | mcp_server | dataset | file | software), `url`, `version`, `retrieved` (ISO date),
  `sha256` (files), `local` (path of the local copy), `access`, `licence`, and `rrid` (Research Resource
  Identifier) where one exists. Steps, results and figures point to them with `uses:`. A resource with
  `aliases:` (a dataset id such as G23/MIC) is linked wherever that id appears in the text or a table cell, like a
  term. The front-matter facts are shown as a table above the text: do not repeat them in a table of your own.
- **Tools are resources too, with RRIDs.** Every tool a step runs (language, packages, command-line tools) gets a
  `kind: software` resource with the exact version from the lock file, `part_of:` a resource for the environment
  (the lock file with its sha256), and its RRID: find it on scicrunch.org/resources (never from memory) and run
  `kea rrid`, which checks every RRID against the SciCrunch resolver. Each step `uses:` the tools its scripts
  import; the PDF's Methods list them with their RRIDs. A tool with none gets `rrid: none` (searched, none registered) and keeps its version, URL and, where there is one, the paper it `cites:`. The build notes resources without kind, version, retrieved date or (files, datasets)
  checksum. Keep them apart from references (papers): a resource is what you need to rerun the analysis.
- **A source and each record taken from it are separate resources.** A website, catalog, database, API or MCP
  server is one resource (its URL, release or version, the date it was queried, the client and its version). Each
  record the analysis uses from it (a dataset, a study, an accession, a release file) is a resource of its own:
  its `accession` or `dataset_id`, its own `version`/release, the `retrieved` date, the `sha256` and `size` of the
  local copy, `part_of:` the source's page, and `cites:` the reference page of the paper behind it (fetched, with
  `kea cite`). Examples: the GWAS Catalog is one resource and each GWAS study used (GCST accession, its summary
  statistics file) is another, citing its paper; Open Targets (platform release) and each target or credible set
  used; Europe PMC and a saved search result.
- **Anthive** follows the same rule: one resource for the server (`kind: database`, URL, Anthive version, vark
  version), one per Anthive dataset read (`kind: dataset`, `dataset_id` such as F26/PFC, the dataset `version` and
  `deposit` id from `vark datasets status <deposit> --json`, the h5ad's `sha256` and `size`, cells, genes, the
  datasets it reanalyses, access, licence, `cites:` its source paper), `part_of:` the server. When the analysis
  reads a local copy, compare its checksum with the deposit's and say on the page whether they match; a local
  file that is not on the server is a `kind: file` resource of its own, and the mismatch is a caveat.
- References show on the site as a pill with the author and year (Akiyama et al. 1994), taken from the start of
  the title ("Akiyama et al. 1994, J Neuroimmunol: …", the house style) or from `citation:`. Cite them in the text
  as `([[ref-x]])`; `[[ref-x|Lloyd 2024, p.7]]` puts that text in the pill (a page number, say).
- Reference pages carry `pmid:` / `doi:`, the abstract fetched from Europe PMC / PubMed (never from memory) and why
  the paper is there. Run `kea cite --write` to add the full citation (`citation:`, Nature style, from Europe
  PMC, or Crossref for DOIs Europe PMC does not index); the PDF numbers references B1, B2 … in order of first citation, shows them in the text as ordinary tags (never superscript) and lists them like a journal.
- **Name pages by their link**, never as "conclusion 2" or "step 3": `[[c-x]]` shows the kind and tag
  (Conclusion C2) exactly as everywhere else; the build notes spelled-out names.
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

## Scientific language

Every page is written as a careful paper would be. The wording must not claim more than the evidence does.
- **Verbs match the design.** Use "is associated with", "is consistent with", "predicts" or "does not support".
  Causal verbs (causes, drives, regulates, explains, leads to) need an intervention or a design that justifies
  them; otherwise say why the link is only an association.
- **Effects carry their size and uncertainty**: estimate, interval or spread, and n of the unit of replication
  (donors, not cells). Write "significant" only with the test and the corrected p or q. Never write "trend towards
  significance", "marginally significant" or "highly significant".
- **Null results are stated as such**: "no difference was detected (n, estimate, interval)". Write "there is no
  effect" only after an equivalence test or with a stated detectable effect size. Absence of evidence is not
  evidence of absence.
- **Say how sure, and why.** Tie it to the evidence: one cohort, n = 40 donors, not replicated, a post-hoc test.
  Do not hedge with empty words ("may potentially", "might suggest") and do not oversell ("clearly", "robust"
  without the robustness check, "novel", "striking", "remarkable", "powerful").
- **Label exploratory and confirmatory work in the text, not only in the front matter.** Hypotheses formed after
  the results are called post hoc.
- **Keep the literature apart from the data.** Write "Smith et al. (2023) report …" and "in our data …"; never
  present a claim from a paper as a finding here. Cite only from fetched records (see References).
- **Be precise and consistent.** Define a term once (a term page) and use the same word for the same thing
  throughout. Give numbers with units and the rounding of the source file. Limits go in caveats and are named in
  the conclusion they limit, not buried.
- **Keep the tone neutral.** No conversational or promotional phrasing ("interestingly", "it is worth noting", "we
  believe", "exciting").
- Before a release, reread every `answer:`, conclusion and executive summary for words stronger than the evidence,
  and fix them in the same commit.

## The graph as a whole, and rechecks

`kea check` and every `kea build` check the reasoning graph as a whole, not only each link (docsite/graph.py).
Problems (the strict build fails): a conclusion that rests on no result or figure (directly or through other
conclusions); conclusions supporting each other in a loop; a conclusion that `relies_on` a hypothesis or question;
a live conclusion on deprecated evidence; a confirmatory conclusion on exploratory results only; a hypothesis with
an outcome that no result tests. Notes: an answered question nothing answers, a result without `made_by`, high
certainty on exploratory evidence or under an open caveat, a supported premise with nothing behind it.

**Rechecks.** Every page depends on what is upstream of it (evidence, the step, artefact, decision and resources it
was made with, what it relies on, the caveats that limit it; a hypothesis on its tests, a question on what answers
it). `doc/_checks.yaml` (commit it) holds the fingerprint of each upstream page when the page was last checked.
When an upstream page changes in substance, the page and everything downstream get a red **recheck** pill and a
gap in `kea context`. Then, for each (`kea recheck --list`): read it against what changed; if it is even slightly
affected, update it (numbers from the re-run, wording, status, certainty, caveats); then record the check:
`kea recheck <id> --because "unaffected: …"` or `"updated: …"`. Recheck the page that changed directly first:
pages marked "via X" clear with it. `kea cycle release` refuses while pages wait for a recheck
(`--allow-recheck "why"` only when the owner agrees, and say so in the run entry). Never clear a recheck without
reading the page.

## Proposals from readers

Readers can propose the next step of the reasoning for the page type (tags of group `propose`, with text): a
question or premise on the experiment, a hypothesis, step or premise on a question, a step or competing
hypothesis on a hypothesis, a control or another method on a step, a conclusion, caveat, control or other
explanation on a result, a caveat, other explanation, follow-up question or certainty on a conclusion, a reason a
premise may not hold, another option on a decision, a step that addresses a caveat. They are harvested like
comments; `kea show` prints what each asks. Write each as its own page with the right relations (or merge it,
or say why not), keep the reader's wording where it holds, and name the reader in the reply.

## Builds

`kea build` (review, with comments), `kea build --mode local` (no comments, data links into the project folder,
for reading from disk), `kea build --mode public --out DIR` (no comments, no data, no previews of controlled
tables; for hosting elsewhere; check `_public_report.json`; run entries may quote comments, so read them first).

`kea pdf` (`make pdf`): one PDF of every page, typeset with Typst, into `report/pdf/` under a new name each time
(title, date, site version, commit).

- **Title page:** title, author (`author:` in `kea.yaml`), then stacked: document version, commit and date,
  repository, "made with Kea" with the page of "About this document"; then the project summary. With several
  experiments page 2 summarises them; with one, the PDF reads as that experiment.
- **Order of each chapter:** at a glance (each question with its answer and conclusions; each conclusion in full
  once; open caveats), background and scope (the home page after its summary), premises, then per question its
  answer, a hypothesis table and the results with their figures, then conclusions, caveats and methods (steps
  with their decisions).
- **Layout:** At a glance, every question and every closing chapter start on a new page (other sections follow
  on); full names read as the kind in its colour followed by the tag ("Question [Q1]"); lists of
  pages are one link per line with the status and page number at the end of the line; hypotheses, conclusions and
  caveats also appear as tables tinted by status (green supported, red rejected, amber open).
- **Closing chapters** (no "Appendix" label): overview of all pages (one table per kind: tag, one line, status,
  question, linked pages), hypotheses in full, data and resources (resources with version, date, checksum and
  local copy; data files; figure files), glossary (key terms, then groups such as Genes), references (numbered
  B1 …, Nature style), what changed (each release with kind, plan, commit and run; each run with its plan,
  release and commits); then a standard "About this document" that names only the parts present.
- **No data-file contents.**
- **Without Typst** the `.typ` source is still written and the command exits 3 with install instructions. Offer
  to install Typst rather than working around it.
- **`kea build` adds two PDFs to the site**: the reader's copy (the story, glossary and references; the menu's PDF) and the complete one with the records (overview tables, hypotheses in full, data and resources, figure files; under PDF ▸ With all records). Each is recompiled only when its inputs change
  (source, images, Kea, Typst; the build says why); `--no-pdf` skips compiling it and keeps the PDF of the last full build on the site.

The PDF is read on paper by people outside the review cycle. Keep review-process notes ("plan v0.4 #2", "Mark's
comment", thread ids) out of page bodies and summaries, or confine them to one short closing section; keep
hypothesis numbers in captions and titles current after renumbering. Look at a few rendered pages (figures, tables) after a large change to the pages.

## Hosting on a Kea hub

A hub (`kea hub serve`, behind an https reverse proxy) hosts many projects at `https://<hub>/p/<project>/` and keeps
their comments; the agent works locally and talks to the hub only over https.

1. **The owner** runs `kea hub add <project>` on the hub and gives you the project key; it prints a site password
   (readers comment under any name) and an iteration password (also Harvest and Implement). Put
   `KEA_REMOTE_KEY=<key>` in `.env` (never print or commit it) and in `kea.yaml`:
   `remote: {url: https://<hub>, project: <project>}`.
2. **Data files: ask first, in one batch.** Run `kea publish --files`: it lists every data file the site links to,
   its size and whether it would go up. Files that may hold identifiers (donor, subject, sample … columns) or that
   kea cannot inspect (h5ad, parquet, npz) stay home unless named. Ask the owner one question, e.g. "Upload the
   12 small files (< 100 kB) without identifier columns? These 9 stay home: …", and record the answer in
   `kea.yaml` (`upload_max_kb`, `upload_include`, `upload_exclude`). Default: nothing goes up. Controlled-access
   data never goes up without the owner's explicit yes, file by file. On the hub, files that stay home show no
   download link and no preview.
3. **Publish** after every `make site`: `kea publish` (it sends the site, the Markdown for the editor and the chosen
   files; the first time also the existing comments). Only files the hub does not hold yet go up, in resumable
   chunks, so later publishes are small; a failed publish can simply be run again. Tell the owner the link and the two passwords' roles.
4. **Watch** as usual: `kea watch`, `kea list`, `kea reply` and `kea cycle` read and write the hub's record; the
   local `data/feedback/*.jsonl` are kept as an exact mirror (commit them as before).

## Every agent run

Pick a run id `YYYY-MM-DD-<letter>`; put `Run: <id>` in every commit; `Answers-comment: <thread>` when a commit
answers a comment; write `doc/_changes/<id>.md` (asked, found, changed, corrections, checked, not done).

## Review cycle

1. **Watch:** `kea watch --deadline 3d` (or 12h, an ISO date/time, epoch seconds) in the background (token-free;
   comments alone never wake it; a status line every hour; check it with `kea watch --status`). Exit 30: deadline
   reached, start it again if the owner still wants it.
2. **Harvest (exit 10):** a PI pressed *Harvest comments*. Fold every comment not yet in the plan
   (`kea list --unplanned`; also suggested edits and direct edit commits) into `doc/_cycles/cycle-NNN.md`, with one
   `### N. title` item per change, the threads it answers, the kind of change and the proposed version (front
   matter `version:`). Reply to each thread with its item (`kea reply <thread> "…" --status planned`), commit, run
   `kea cycle plan-updated --commit <sha>` (always, also when nothing was new: it ends the harvest; before it,
   apply Approve, Revise and Drop on pages that wait for approval, see Tags), `make site`
   (and `kea publish`), and watch again. The plan then stands until the next harvest; comments go on, and the plan
   page counts those made since.
3. **Approve & go (exit 40):** a reader signed a page off and asked for its next step now; `kea list` shows the
   thread (tag `go`, its text names the step, its page version). Add the signature to the page's `approved:`, then
   do **that one step for that page only**, as in the pace table (write the plan → hypotheses and planned steps;
   run the step → run it and write the results; draw conclusions → conclusions, outcomes, answer). Tell readers what
   you are doing at each stage, so the click is never followed by silence: `kea progress "writing H1 and S1–S3"
   --page <page>`, `kea progress "running S2: 3 of 8 donors"`, `kea progress "publishing"`. Then the run entry,
   commit, `make site`, `kea publish`, answer the thread with the commit (`kea reply <thread> "…" --status
   page-changed --commit <sha>`), stop for review and start `kea watch` again. Several requests: one at a time,
   oldest first. A request you cannot do (the step needs data you lack, the route is not there yet): answer the
   thread saying why (`--status wont-fix`) and watch again; never leave it open.
4. **Implement (exit 20):** a PI pressed Implement (only possible after a harvest); comments made after the
   harvest are not in the plan and stay for the next cycle. Exit 20: run `kea cycle start` and `make site`, then implement every item. Suggested edits:
   `kea apply-suggestion <thread>`, then check every number against its source and commit with the reader as
   co-author. After the changes, work through `kea recheck --list` (see "The graph as a whole") before the
   release. Never implement before Implement unless the owner asks in chat.
5. **Release:**
   - Reply to each thread with its commit (`--status page-changed --commit <sha>`).
   - Set the plan's `status: implemented` and `run:`.
   - Write the run entry and commit.
   - Run `kea cycle release --run <id> --commit <sha> --version X.Y.Z --kind major|minor|patch --reason "…"
     [--experiment NAME=X.Y.Z]`. It writes the git tags.
   - Run `make site` (and `kea publish` with a hub). Restart `kea serve` if kea itself changed.

   Version rules: MAJOR when a conclusion changes direction or is withdrawn, MINOR for new results or pages,
   PATCH for wording only. Before 1.0 a major change counts as minor.

**Tags.** Readers tag selected text or a whole page with one click, next to commenting. Suggestions for the next run (explain, expand, shorten, delete, challenge, source, or a project's own) are open items like comments: `kea show` prints each tag's instruction; follow it, plan it and answer it as usual. For `challenge`, start a separate reviewer (a subagent that sees the page, its sources and caveats, not your reasoning), answer its points, then strengthen, weaken or withdraw the claim, and summarise the exchange in the reply. The page verdicts are definitive, and `kea show` prints what each asks. On a page that waits for approval (pace): `approve`, `revise` (with the reader's text) and `drop` are applied at the harvest itself, so the step-by-step route never waits for an Implement: `approve` adds a signature to `approved:` (`{by, orcid, date, version, how: site}`; keep earlier ones, one per person); `go` (Approve & go) is handled at once, see the review cycle; `revise` rewrites the page, which then waits for approval again; `drop` removes it and what rests only on it. On a settled page they go into the plan and are done at Implement: `confirm` writes `confirmed: {by, date, version}` and changes nothing else (from then on, change a confirmed page's claim only through a plan item that names the confirmation); `unconfirm` removes that field; `revise` reworks the branch (rewrite the page, remove `approved:`/`confirmed:`, then recheck every page downstream with `kea recheck`); `drop` removes the page and every page that rests only on it (`kea drop <id>` lists them; a question or step gets status dropped, results, conclusions and figures deprecated with the reason, a decision superseded, other pages are deleted; fix the links, recheck what rested partly on them). `reject` (before 1.19) reads as `drop`. Manuscript tags (introduction, methods, results, discussion, conclusions, supplement, not-in-manuscript) give the thread the status `marked`: no work, not in plans, never set a status on them. `kea tags [names…]` lists marked fragments per section with file and lines, the input for a manuscript. Change the vocabulary under `tags:` in kea.yaml.

## Adapting Kea on request (in flight)

Kea is small (about 11,500 lines of Python, no database, static HTML), and changing it at the reader's request is
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
