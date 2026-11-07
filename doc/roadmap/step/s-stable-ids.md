---
id: s-stable-ids
type: step
title: "Permanent identifiers for every object in the graph"
short: "Every page version gets an identifier that never changes and a URL on the host it is published on (keahub.eu or any other), so that projects can link to each other's claims and a reader can always follow a superseded object forward."
parent: q-order
status: planned
order: 11
relations:
  relies_on: [p-small-kernel]
---
## Proposal (Mark Fiers, 7 November 2026)

Every object in the graph (premise, result, conclusion, figure …) gets a unique identifier that never changes, in the
spirit of RRIDs and DOIs. Minting real DOIs should stay possible later; for now a URL is enough, on keahub.eu or on
whatever host a project is published on:

    https://keahub.eu/p/<project>/C/<long-id>

- The number shown on the site (C1, H2 …) stays the readable name that follows the logic of the story; the long id is the permanent one.
- The long id is the hash of the object. Once written it is stable: a typo fix gives a new id.
- Old ids are never deleted, only orphaned when a page is rewritten; a manual purge removes them.
- The graph stores which id supersedes which, so a reader who arrives at a deprecated object is pointed forward.
- Local ids are not transferable, but that is fixed the moment a project publishes on a host.

This is what [[s-federated-claims]] needs: a link from one project to another must point at something that does not
move.

## Review (Claude, 7 November 2026)

The hash part works: it needs no registry, it is the same on every machine, and it proves which text was cited.
Three parts need changes; see the caveats below.

1. **A hash names a version, not the claim.** A premise in project B that links to a conclusion of project A by its hash
   is pinned to that wording. After a typo fix in A, B's link points at an orphan and has to follow the forward
   chain to see the current claim. Zenodo solves the same problem with two identifiers: a *concept* DOI (always
   the latest version) and a *version* DOI per release. Kea needs both: a **concept id**, random, minted once when
   the page is created and stored in its front matter (`uid:`), and a **version id**, the content hash. Links say
   which they mean: "this claim, as it stands now" (concept) or "this claim, as I read it" (version). Retraction
   alerts in [[s-federated-claims]] follow concept links; citations in a paper use version ids.
2. **Hash at release time, not at every save.** A hash per edit makes thousands of ids per day, most of them
   never seen by anyone. Mint version ids for the pages in each release (the `site/vX.Y.Z` tag) and for pages a
   reader commented on; git already keeps every other state.
3. **The host should not be part of the identity.** `https://keahub.eu/p/<project>/C/<hash>` breaks when the
   project is renamed or moves host, and the type letter breaks when a page changes type. Make the identifier
   `kea:<concept>` and `kea:<concept>@<hash>`, and let any host resolve it at `https://<host>/id/<concept>`.
   That is the DOI model: identifier and resolver are separate, and a DOI can be minted later on top of the
   concept id.
4. **Purge and permanence contradict each other.** A purged id must leave a tombstone (what it was, when and why
   it was removed), or links from other projects fail silently.
5. **What is hashed must be defined.** Proposal: the page file in a canonical form (front matter with sorted keys
   and without volatile fields such as `order:`, body with normalised whitespace), sha256, written in base32 and
   shortened to 26 characters. Whitespace-only changes then keep their id; any change of words gives a new one.

Splits and merges (one conclusion becomes two) do not fit a single forward chain; `supersedes` already allows
several targets, so the chain becomes a small graph.

## Size

Concept ids: one front-matter field, written by `kea check --fix` for pages without one, plus a resolver page per
id on the site. Version ids: a hash function and a table written at release. My estimate is 150 to 250 lines; it
is not measured.
