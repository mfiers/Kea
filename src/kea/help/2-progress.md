## How a project progresses

<!-- ROUTE -->

Every analysis follows one route, and each page is a stop on it: experiment → question → hypothesis → step → result → conclusion → the question's answer. Premises, decisions, caveats, figures, artefacts and resources feed in from the side.

- A question is proposed, and approved before anything is built on it.
- Hypotheses are written before the test, with a prediction and a criterion for support, and committed; the commit time is the record. That record lives in the project's own repository, so it is not a public preregistration: git history can be rewritten, and the repository is often private. Work not fixed in advance is labelled exploratory on its results and conclusions.
- Steps do the work from scripts (Makefile targets, seeds, versions) and make results; every number on a result page comes from a named file.
- Conclusions are drawn from results only, with the evidence for and against, a reason per link and a certainty. The question's answer and the summaries change in the same commit. The reason on each link is Toulmin's warrant (why this evidence bears on this claim); the certainty uses GRADE's four labels (high, moderate, low, very low), though Kea does not apply GRADE's rating method.
- After each run the caveats are read again: addressed by this run, or still limiting the new result.

One step at a time (`pace: guided`, the default of `kea init`). The agent takes one step along the route and stops for the owner's review: it proposes questions and waits; for an approved question it proposes hypotheses and planned steps and waits; it runs approved steps, writes the results and waits; it concludes from reviewed results. A page that waits carries a "waiting for approval" pill. The reader's verdicts on it are Approve (a sign-off: your name and the version you read, recorded on the page), Approve & go (the same, and the agent takes the next step now: write the plan, run the step, …), Revise (say what to change; it is rewritten and waits again) and Drop (remove it, with every page that rests only on it). On a settled page the verdicts are Confirm (keep it as it is; recorded on the page), Revise and Drop. Approval can also be given in the agent's chat; either way it is written on the page (`approved:`, one signature per person), and `kea check` refuses work built on unapproved pages.

What Kea checks on every build (`kea check`; `kea build --strict` fails on a problem): a conclusion rests on at least one result or figure, not on a hypothesis or a question; no conclusions support each other in a loop; a live conclusion does not rest on deprecated evidence; a confirmatory conclusion does not rest on exploratory results only; a hypothesis with an outcome names the result that tested it; a hypothesis fixed before its results states its prediction and criterion; every relation connects the right kinds of page; every linked page and file exists.

When a page upstream changes (a premise is revised, a result redone, a decision changed), every page that rests on it, directly or further down, gets a red "recheck" pill. The agent reads each against the change, updates it when it is even slightly affected, and records the check (`kea recheck`, ledger `doc/_checks.yaml`). A version is not released while pages wait for a recheck.

Versions. Each release is a semantic version and a git tag: MAJOR when a conclusion changes direction or is withdrawn, MINOR for new results or pages, PATCH for wording only; before 1.0 a major change counts as minor. Each page shows the release in which it last changed, so settled parts stand out from parts in flux. The site and the PDF are two views of one version.
