---
id: w-hash-pins-version
type: caveat
title: A content hash names one version, so links to a living claim break on every edit
short: "With only a content hash, a link from another project is pinned to the wording it saw; after any edit, even a typo fix, it points at an orphan and has to walk the supersedes chain to find the current claim."
parent: s-stable-ids
status: open
relations:
  limits: [s-stable-ids, s-federated-claims]
---
Raised in the review of the identifier proposal on 7 November 2026 (Claude). The remedy proposed on [[s-stable-ids]] is a second, stable concept id per page, as Zenodo keeps a concept DOI next to each version DOI.
