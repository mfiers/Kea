---
id: s-paper-compiler
uid: x56zogthjmglbffyxhtcbjulum
type: step
title: "Paper and rebuttal compiler"
short: "A manuscript generated from the graph; each reviewer point becomes a plan item tied to a commit."
parent: q-order
status: planned
order: 6
relations:
  relies_on: [s-tags, s-stable-ids]
---
A manuscript generated from the graph; each reviewer point becomes a plan item tied to a commit.

## How a manuscript starts (Mark Fiers, 7 November 2026)

Readers mark what they want in the paper with the manuscript tags ([[s-tags]]): introduction, methods, results, discussion, conclusions, or not in manuscript. A second button, next to the one that starts a review iteration, starts a manuscript instead: a new folder like an experiment, but made for writing a paper. Its text refers back to the original Kea objects.

## Design to discuss (Claude, 7 November 2026)

- **The folder:** `doc/<manuscript>/`, an experiment with its own page types: `section` (introduction, methods, results, discussion, conclusions, supplement), plus `figure` pages that link to the figures of the analysis. Each section starts as a list of the marked fragments (from `kea tags`) with links to their pages; the agent turns the list into prose, keeping one reference per claim.
- **References to the analysis:** every sentence that carries a claim links to the Kea object it comes from. With [[s-stable-ids]] those links are version ids, so the manuscript records exactly which version of a conclusion it states; when the analysis changes later, the manuscript shows which sentences now rest on an older version.
- **The button:** a cycle event ("manuscript requested", with a name) in the same log as Freeze and Implement, behind the iteration password; `kea watch` reports it to the agent, which creates the folder. The server itself writes no files in `doc/`.
- **Not in manuscript** fragments are left out even when their page is marked as a whole.
- **Reviews:** the manuscript folder gets review cycles like any experiment; reviewer reports enter as comments, each becoming a plan item with a commit (the rebuttal part of this step).
