## Why

An analysis produces claims, and whether a claim holds depends on things that are hard to see: the file a number came from, the test that was run, what was assumed, when the hypothesis was written, and what changed since. In a report or a notebook that chain is not inspectable. The number is there but not its file; the hypothesis reads as if it came first; a premise was revised weeks ago and nothing downstream was looked at again.

An AI agent makes this worse. It produces more claims, faster, and the reasoning that connects them sits in a chat log nobody will read again.

Review has the same problem. Comments on a PDF or in an email thread lose their place: which version was commented on, what was done about it, and in which release.

Kea writes the chain down and keeps it checkable: every claim is a page, every page says what it rests on, every change is recorded, and a reader's comment is answered with the commit that dealt with it.

## Why small pages

One claim per page, so that each claim can be handled on its own. A page can be linked by a typed relation (this result supports that conclusion; this caveat limits it), cited by a permanent id that survives edits and renames, commented on, approved or dropped by a reader, rechecked when something it rests on changes, and versioned with the rest of the site.

The evidence chain becomes checkable because every link is written down. A result names the file every number comes from. A conclusion names the results for and against it, with a reason per link and a certainty. A hypothesis states its prediction and what would count as support, and whether that was written before or after the test. `kea check` reads the links as a graph on every build.

A page is also the right unit for an agent and for a reader. The agent works, is reviewed and corrected one page at a time. A reader with five minutes reads a question's answer and stops, or follows the links down to the file.

## What Kea adds

Claims linked to their evidence are not new: micropublications, discourse graphs, Octopus and nanopublications model them, and agent systems such as Kosmos keep a structured state of an analysis (see [Related work](https://github.com/mfiers/Kea/blob/main/doc/_site/related-work.md)). We found none of the following, combined, in those systems:

- a person's approval at each step of the route before the agent builds on it (`pace: guided`);
- hypotheses fixed before their test, recorded in the graph with the commit time as the record;
- recheck flags that run downstream when a page upstream changes;
- the agent's runs, change logs and review cycles tied to semantic versions of the whole graph;
- all of it as Markdown in the project's own git repository.
