<!-- kea:start -->
## Documentation site and review cycle (kea)

- One agent per project: run `kea lease take` before anything else; if it refuses, stop and tell the owner.
- `doc/` is the source of truth: `doc/<experiment>/<type>/<id>.md` with typed front matter (`doc/_schema.yaml`).
  Every agent run writes `doc/_changes/<run id>.md` and puts `Run: <run id>` in its commit messages; commits that
  answer comments carry `Answers-comment: <thread>`.
- `make site` (`kea build --strict`) builds the site; `make serve` (`kea serve`) serves it with comments
  (`SITE_PASSWORD` in `.env`, never printed or committed). With a Kea hub (`remote:` in kea.yaml,
  `KEA_REMOTE_KEY` in .env): `kea publish` after every build; data files up to 10 kB go up unless flagged
  (identifiers, opaque formats); ask the owner before larger ones go up (`kea publish --files`).
- Pace: one step along the route, then stop for the owner's review (experiment → questions → hypotheses and
  planned steps → results → conclusions); go further only when the owner says so in chat or the step is an item of the plan being implemented.
  Sign-offs go on the page with `kea sign` (never by hand): bound to the wording signed; minor edits with `kea sign <id> --minor --because …`; `kea context` names the next step.
- Before working on a question: `kea context <question>` (premises, decisions in force, caveats, evidence so far,
  open comments, gaps); fix hypotheses (`fixed_before_results: true`) and commit them before the test runs; after
  the run, re-check the caveats and update `answer:` and the summaries. `kea context <experiment>` shows open work.
- Review cycle: `kea watch` waits; comments alone never wake it. Exit 10 (a PI pressed Harvest): fold the
  comments into `doc/_cycles/cycle-NNN.md` (`kea reply … --status planned`), then always `kea cycle plan-updated
  --commit …` (it ends the harvest). Exit 20 (Implement) → `kea cycle start`, implement, run entry, replies with
  commits → `kea cycle release --version X.Y.Z --kind … --reason …` → `make site`. Never implement a
  plan item before Implement unless the owner asks in chat. Sign-offs (Approve on the site) wait for the harvest like
  every comment: at the harvest, `kea sign --pending` writes them onto the pages, and the next step of every stage
  that is signed becomes a plan item (`kea context` names it); a harvest runs nothing else. During Implement, tell
  readers what you are doing with `kea progress "…"`.
- Changing a signed page (skill: sign-offs; Kea 1.32): minor → `kea sign <id> --minor --because`; substantive → `kea change <id> --because` (the pages built on it then wait for a sign-off each, showing the change; pages further down are held until those are signed); invalidating (a question's ask, a tested hypothesis's prediction) → a new page with `supersedes:` and `kea drop <old> --apply --replaced-by <new>` (retired, kept as a record; premises, decisions, terms, resources stay). Name the class and `kea impact <id>` in the plan item. An experiment page's progress (so far, nothing yet, written date and version) goes in its `answer:` field, not its text: `answer:` is unsigned, so updating it holds nothing (moving it there is `--minor`).
- After any change, `kea recheck --list`: read every page downstream of a changed page against the change,
  update it if it is even slightly affected, then `kea recheck <id> --because "…"`; releases wait for this.
- Versions: MAJOR = a conclusion changes direction or is withdrawn; MINOR = new results or pages; PATCH = wording
  only; before 1.0 a major change counts as minor.
- Figure captions: title, take-home, then per panel take-home / Shows / Method / Statistics, written by the figure
  script from the saved table.
- Every number on a page comes from a file named in `sources:` or an artefact page.
- Minimal graph (skill: "A minimal graph"): anything that can be a page is a page (limits as caveats, assumptions as premises, choices as decisions); one idea per page, a question asks one thing; titles one line, texts as short as the idea allows; precise, never wordy. `kea build` notes breaches.
- Scientific language (skill: "Scientific language"): verbs no stronger than the design (association, not
  cause), effect sizes with uncertainty and n of the replicate unit, nulls stated as nulls, post hoc labelled, literature kept
  apart from our data, no hype or empty hedges.
- Summary lines are written for the reader, without internal labels; dates in the text carry their version.
- Do not hard-wrap Markdown in `doc/`: one line per paragraph and per list item (readers edit pages in the site's editor, where wrapped lines look broken).
<!-- kea:end -->

## Kea's own version numbers

- The page scripts (`src/kea/feedback/static/`) are copied into every built site and published with it; the hub's own Kea only serves the API (`src/kea/feedback/server.py`, `hub.py`, `store.py`, `cycle.py`, the publish format, `/api/status` fields).
- A change that needs the hub (or `kea serve`) to be upgraded before a site built with it works (a new or changed endpoint, status field, event type, tag rule or publish format) is at least a MINOR release (1.31 → 1.32), never a patch. A patch must run against a hub on any patch of the same minor version: the reader's menu turns the hub version red only when MAJOR.MINOR differ.
- In each change entry say whether the hub must be upgraded.
