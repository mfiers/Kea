<!-- kea:start -->
## Documentation site and review cycle (kea)

- One agent per project: run `kea lease take` before anything else; if it refuses, stop and tell the owner.
- `doc/` is the source of truth: `doc/<experiment>/<type>/<id>.md` with typed front matter (`doc/_schema.yaml`).
  Every agent run writes `doc/_changes/<run id>.md` and puts `Run: <run id>` in its commit messages; commits that
  answer comments carry `Answers-comment: <thread>`.
- `make site` (`kea build --strict`) builds the site; `make serve` (`kea serve`) serves it with comments
  (`SITE_PASSWORD` in `.env`, never printed or committed). With a Kea hub (`remote:` in kea.yaml,
  `KEA_REMOTE_KEY` in .env): `kea publish` after every build; ask the owner before data files go up
  (`kea publish --files`).
- Before working on a question: `kea context <question>` (premises, decisions in force, caveats, evidence so far,
  open comments, gaps); fix hypotheses (`fixed_before_results: true`) and commit them before the test runs; after
  the run, re-check the caveats and update `answer:` and the summaries. `kea context <experiment>` shows open work.
- Review cycle: `kea watch` → fold comments into `doc/_cycles/cycle-NNN.md` (`kea reply … --status planned`,
  `kea cycle plan-updated --commit …`) → readers Freeze, then Implement → `kea cycle start`, implement, run entry,
  replies with commits → `kea cycle release --version X.Y.Z --kind … --reason …` → `make site`. Never implement a
  plan item before Implement unless the owner asks in chat.
- Versions: MAJOR = a conclusion changes direction or is withdrawn; MINOR = new results or pages; PATCH = wording
  only; before 1.0 a major change counts as minor.
- Figure captions: title, take-home, then per panel take-home / Shows / Method / Statistics, written by the figure
  script from the saved table.
- Every number on a page comes from a file named in `sources:` or an artefact page.
- Scientific language (skill: "Scientific language"): verbs no stronger than the design (association, not
  cause), effect sizes with uncertainty and n of the replicate unit, nulls stated as nulls, post hoc labelled, literature kept
  apart from our data, no hype or empty hedges.
- Summary lines are written for the reader, without internal labels; dates in the text carry their version.
<!-- kea:end -->
