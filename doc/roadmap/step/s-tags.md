---
id: s-tags
uid: pwsnbxg5cyottefbera7ecbl5e
type: step
title: "Tags on text fragments and whole pages"
short: "One-click tags on selected text or a whole page: suggestions for the next run (explain, expand, delete …), the reader's verdict on a page (confirm, reject) and the manuscript section a passage belongs in."
parent: q-order
status: in_progress
order: 14
---
## Proposal (Mark Fiers, 7 November 2026)

Before Kea writes papers ([[s-paper-compiler]]), readers need to tag text as well as comment on it: select text, press a button, choose tags. The same must work for whole pages. A few tags are predefined; free tags are worth considering. The set must be easy to extend, each tag with its own assignment for the agent.

- doubt: picked up in the next iteration and re-assessed critically by a second, adversarial agent that discusses with the main line whether the text is correct and what support it needs ([[s-adversarial-reviewer]]);
- remove, explain, expand;
- for the manuscript: not in manuscript, introduction, methods, results, discussion, conclusions.

## Second round (Mark Fiers, 8 November 2026)

Tagging took too many clicks. The tags should be there at once when text is selected, next to Comment and Edit. Editing should work on a selected passage, not only on whole pages and sections, and on the front page too. Three groups: suggestions for the next run (expand, delete, explain …); the reader's confirmation of the object itself (confirmed, remove), probably for whole pages only; and a separate choice of manuscript section.

## As built (8 November 2026, not released yet)

- **Selected text** opens a light popup next to the selection, never over it (below, or above when there is no room): *Comment* and *Edit* (suggest an edit of just the paragraphs that hold the selection) on top, then two labelled groups of one-click tags, *Next run* (explain, expand, shorten, delete, challenge, needs source) and *Manuscript* (introduction … not in manuscript). One click saves the tag; a note at the bottom says so and offers *Undo*. Esc closes the popup.
- **Page buttons** (8 November, third round): a column of pill buttons at the bottom right, folded open and shut by a small kea head (remembered across the site): *Comment* (with the count of open comments), *Edit*, then *Confirm* and *Reject*, then *Next run ▸* and *Manuscript ▸*, each opening a small popup of chips. What was chosen also shows as pills next to the title.
- **Confirm and Reject are definitive page verdicts** that go into the next plan; the server refuses them on selected text. A pending verdict stays highlighted until the plan is implemented; clicking it again takes it back. After Confirm, the agent writes `confirmed: {by, date, version}` into the page's front matter, and the button stays on (green) for as long as that field is there; clicking it then asks to withdraw the confirmation, again through the next plan. After Reject, the page is gone: results, conclusions and figures are deprecated with the reason, other pages deleted, relations fixed.
- **Taking tags off:** click an active chip again, or × on a tag in the comment panel; a thread of tags only is withdrawn when its last tag goes.
- **The comment panel is simpler:** no Suggest-an-edit button, no link to all comments, no help text, no tag picker in the comment form (tags are set with the buttons).
- **The front page** can be edited: its summary comes from `doc/_summary.md`, or from the only experiment's home page.
- Task tags make an open item for the next cycle, and `kea show` prints the tag's instruction for the agent. Manuscript marks are never counted as open, never enter a plan, and can be set while the site is frozen. `kea tags` lists the marked fragments per section with source file and line numbers.
- The vocabulary is in `src/kea/feedback/tags.py` (each tag: group, task, scope, label, help, instruction); a project adds or changes tags under `tags:` in kea.yaml, and `free_tags: false` turns off readers' own tags.
- **Hub:** a hub accepts tags only when it runs this version of Kea.

## Choices made (Claude)

- **"challenge" instead of "doubt"** (7 November): the tag names what the agent does with the text, like explain or expand.
- **"needs source", "shorten" and "supplement" added** (7 November); "remove" for text is now **"delete"**, so that it is not confused with the page verdict *remove* (8 November).
- **Passage edits take whole paragraphs.** The page shows rendered text and the source is Markdown, so a selection cannot be mapped to exact characters; the editor opens the blank-line paragraphs (or front-matter lines, for the summary) whose words match the start and end of the selection. When nothing matches, the whole page opens.
- **Verdicts and page tags are not offered on generated pages** (front page, map, history), which are not objects of the graph; there the page popup has only Comment and Edit.

## Open

- The challenge assignment asks the agent to run a separate reviewer and summarise the exchange in its reply. The summary would be better kept as a node of its own (a *discussion* or *footnote* type, linked with `limits` or `supports` to the text it challenged), so that the reasoning survives after the thread is resolved. That belongs to [[s-adversarial-reviewer]].
- A confirmation is tied to the page's version but not shown on the relations map; a map layer "confirmed / not confirmed" would show what the owner has checked.
- Tags on a fragment that is later rewritten end up under "comments on earlier wording", like comments. For manuscript marks the agent should move them to the new wording; this is not automatic.
