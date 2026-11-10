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
