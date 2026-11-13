## Comments and the review cycle

On a site served with comments, sign in with the site password and your name, or with ORCID on a hub that offers it. Then:

- Select any text for Comment, Edit (just that passage) or a one-click tag: a request for the next run (explain, expand, shorten, delete, challenge, needs source) or the manuscript section the passage belongs in.
- The buttons at the bottom right act on the whole page: Comment, Edit, the verdicts (Approve, Approve & go, Revise, Drop; Confirm on a settled page), Propose (the next step of the reasoning for this kind of page: a hypothesis on a question, a caveat on a result, a control on a step, …), Next run and Manuscript.
- The pencils in the left margin edit the title or summary in place; the pencil after a section heading edits that section. Every edit is saved as a suggestion, shown as a diff, and goes into the next plan.

Nothing changes until the comments are harvested:

1. Comment. Readers comment, tag, edit and propose for as long as the round takes. The agent waits (`kea watch`) without reading them; comments alone never wake it, so a long round costs nothing.
2. Harvest. A PI presses "Harvest comments". The agent folds every comment into one plan of numbered items (what will change, on which pages, the version it will make) and answers each comment with its item. Approve, Revise and Drop on pages waiting for approval are applied at the harvest itself, so the route never waits for an Implement. The plan stands until the next harvest; the plan page counts the comments made since, and "Harvest again" adds them.
3. Implement. A PI presses "Implement the plan". Comments pause. The agent changes the pages item by item, checks every number against its file, works through the rechecks, commits each change and answers each comment with its commit: page changed, answered, or won't fix with the reason.
4. Release. A new version and git tag, with the run's change log. Open pages reload and comments reopen. Comments left out of the plan stay for the next cycle. The History page links each comment to its plan item, commit and pages. Plan → Current comments lists who commented what and where, with a filter per person.

Approve & go does not wait for a harvest. It signs the page off like Approve and asks the agent to take that page's next step now; the button names the step (propose questions, write the plan, plan its steps, run the step, draw conclusions). It needs the iteration password, like Harvest. A line at the top of every page then says what was asked, whether a session is watching, and, once the agent has picked it up, what it is doing ("running S2: 3 of 8 donors"); the page reloads when the new version is published. The agent takes only that one step and stops for your review.

Plan → Progress is the overview: the pages that wait for a sign-off and the button that moves each on, the pages ready for their next step, the route of every question (approved, plan, run, results, conclusions: done, waiting for you, the agent's turn, running), the open Approve & go requests with the agent's status, and every sign-off with its name, version and date.

The plan page shows the agent's session (watching, with the time since its last heartbeat; working; ended; stopped unexpectedly) and offers Harvest and Implement to PIs.
