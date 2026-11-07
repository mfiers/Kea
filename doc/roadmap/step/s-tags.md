---
id: s-tags
type: step
title: "Tags on text fragments and whole pages"
short: "Readers can tag selected text or a whole page: task tags (challenge, needs source, explain, expand, shorten, remove) ask for work in the next cycle; manuscript tags (introduction, methods, results …) mark what goes where in a paper."
parent: q-order
status: in_progress
order: 14
---
## Proposal (Mark Fiers, 7 November 2026)

Before Kea writes papers ([[s-paper-compiler]]), readers need to tag text as well as comment on it: select text,
press a button, choose tags. The same must work for whole pages. A few tags are predefined; free tags are worth
considering. The set must be easy to extend, each tag with its own assignment for the agent.

- doubt: picked up in the next iteration and re-assessed critically by a second, adversarial agent that discusses
  with the main line whether the text is correct and what support it needs ([[s-adversarial-reviewer]]);
- remove, explain, expand;
- for the manuscript: not in manuscript, introduction, methods, results, discussion, conclusions.

## As built (7 November 2026, not released yet)

- Selecting text shows **Comment** and **Tag**. The comment form also has the tag chips, so one note can carry
  both, and the whole-page form at the bottom of the panel can tag the page.
- A tag is stored on a comment thread, so it uses the same anchoring, history, hub sync and cycle as a comment.
  Tags of a thread can be edited later.
- **Task tags** make the thread an open item for the next cycle; `kea show` prints the tag's instruction for the
  agent.
- **Manuscript tags** ask for no work: the thread gets the state *marked*, is not counted as open, never enters a
  plan, and can be set even while the site is frozen for review. `kea tags` lists the marked fragments per section
  with their source file and line numbers; that list is the input of the manuscript.
- The vocabulary is in `src/kea/feedback/tags.py`; a project adds or changes tags under `tags:` in kea.yaml (name,
  group, task, label, help, instruction). Free tags are on by default (`free_tags: false` turns them off); a free
  tag counts as a task without an instruction.
- **Hub:** a hub only accepts tags once it runs this version of Kea.

## Choices made (Claude, 7 November 2026)

- **"challenge" instead of "doubt".** The tag names what the agent does with the text, as the others do (explain,
  expand, remove). "Doubt" describes the reader; "deep research" describes a search, not a test.
- **Two tags added: "needs source" and "shorten".** "Needs source" differs from "challenge": the claim may be
  right, but the page does not show where it comes from (CLAUDE.md requires a source for every number).
  "Shorten" is the counterpart of "expand".
- **"supplement" added to the manuscript tags,** since much of a Kea project ends up in supplementary material.
- **Not added:** "figure" (figures already are typed pages) and "abstract" (written from the conclusions, not from
  fragments). Either can be added in kea.yaml.

## Open

- The challenge assignment asks the agent to run a separate reviewer and summarise the exchange in its reply. The
  summary would be better kept as a node of its own (a *discussion* or *footnote* type, linked with `limits` or
  `supports` to the text it challenged), so that the reasoning survives after the thread is resolved. That belongs
  to [[s-adversarial-reviewer]].
- Tags on a fragment that is later rewritten end up under "comments on earlier wording", like comments. For
  manuscript marks the agent should move them to the new wording; this is not automatic.
