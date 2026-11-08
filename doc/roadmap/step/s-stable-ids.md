---
id: s-stable-ids
uid: qm555kifex25djeizigkzznigm
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

Every object in the graph (premise, result, conclusion, figure …) gets a unique identifier that never changes, in the spirit of RRIDs and DOIs. Minting real DOIs should stay possible later; for now a URL is enough, on keahub.eu or on whatever host a project is published on:

    https://keahub.eu/p/<project>/C/<long-id>

- The number shown on the site (C1, H2 …) stays the readable name that follows the logic of the story; the long id is the permanent one.
- The long id is the hash of the object. Once written it is stable: a typo fix gives a new id.
- Old ids are never deleted, only orphaned when a page is rewritten; a manual purge removes them.
- The graph stores which id supersedes which, so a reader who arrives at a deprecated object is pointed forward.
- Local ids are not transferable, but that is fixed the moment a project publishes on a host.

This is what [[s-federated-claims]] needs: a link from one project to another must point at something that does not move.

## Review (Claude, 7 November 2026)

The hash part works: it needs no registry, it is the same on every machine, and it proves which text was cited. Four parts need changes (1 to 4; 1 and 4 are also open caveats below), and one needs a definition (5).

1. **A hash names a version, not the claim.** A premise in project B that links to a conclusion of project A by its hash is pinned to that wording. After a typo fix in A, B's link points at an orphan and has to follow the forward chain to see the current claim. Zenodo solves the same problem with two identifiers: a *concept* DOI (always the latest version) and a *version* DOI per release. Kea needs both: a **concept id**, random, minted once when the page is created and stored in its front matter (`uid:`), and a **version id**, the content hash. Links say which they mean: "this claim, as it stands now" (concept) or "this claim, as I read it" (version). Retraction alerts in [[s-federated-claims]] follow concept links; citations in a paper use version ids.
2. **Hash at release time, not at every save.** A hash per edit makes thousands of ids per day, most of them never seen by anyone. Mint version ids for the pages in each release (the `site/vX.Y.Z` tag) and for pages a reader commented on; git already keeps every other state.
3. **The host should not be part of the identity.** `https://keahub.eu/p/<project>/C/<hash>` breaks when the project is renamed or moves host, and the type letter breaks when a page changes type. Make the identifier `kea:<concept>` and `kea:<concept>@<hash>`, and let any host resolve it at `https://<host>/id/<concept>`. That is the DOI model: identifier and resolver are separate, and a DOI can be minted later on top of the concept id.
4. **Purge and permanence contradict each other.** A purged id must leave a tombstone (what it was, when and why it was removed), or links from other projects fail silently.
5. **What is hashed must be defined.** Proposal: the page file in a canonical form (front matter with sorted keys and without volatile fields such as `order:`, body with normalised whitespace), sha256, written in base32 and shortened to 26 characters. Whitespace-only changes then keep their id; any change of words gives a new one.

Splits and merges (one conclusion becomes two) do not fit a single forward chain; `supersedes` already allows several targets, so the chain becomes a small graph.

Two later pages depend on this. A confirmation ([[s-tags]], built 8 November 2026) is stored with the git commit of the page it confirmed; a version id would say the same without git, also for another project that links to the page. Code nodes ([[s-code-nodes]]) would use the git blob hash of a file as its version id: for code the raw bytes are the right identity, for pages the canonical form of point 5 is.

## Size

Concept ids: one front-matter field, written for pages without one by a new option `kea check --fix` (it does not exist yet), plus a resolver page per id on the site. Version ids: a hash function and a table written at release. My estimate is 150 to 250 lines; it is not measured.

## Hosting on per-project subdomains (8 November 2026)

The hub is moving to keahub.eu, with every project on its own subdomain, `https://<project>.keahub.eu/`, instead of `/p/<project>/` (proposed by the infrastructure side, agreed by Mark Fiers). The site code is already free of the prefix (relative links, a configurable root path), so for reading this is a change of the hub's routing only. For identifiers it has consequences (Claude):

1. **Identity lives on the apex, not in the subdomain.** A project name in the host breaks every address when a project is renamed or moves to another hub, which is what point 3 of the review avoids. The hub resolves `https://keahub.eu/id/<concept>` (current version) and `…/id/<concept>@<hash>` (that version) with a redirect to wherever the page lives. Citations and links between projects use these apex addresses; the subdomain is only where one reads.
2. **Concept ids are unique across the hub**, random 128-bit values; the hub refuses an id another project already owns (for example a page copied between projects) and learns the ids of a project from an index sent with each publish. A renamed project keeps an alias that redirects its old subdomain.
3. **Status for other projects comes from the apex, with access control.** [[s-federated-claims]] needs the live state of a page in another project (title, status, current version, confirmed, superseded). The agent fetches it at build time from `…/id/<concept>.json`, not the reader's browser across origins. Projects behind a password answer only to a project key they granted access to, so the resolver does not leak their titles.
4. **The hub keeps old versions.** A version id is only useful while that version can be shown. Each publish replaces the site, so the hub keeps an append-only store of each page's text per released version, separate from the site bundles, which can still be pruned.
5. **One wildcard certificate**, `*.keahub.eu`, not a certificate per project: per-project certificates are published in Certificate Transparency logs and would make every project name public, also of private projects.
6. **Agents stay on the apex** (`remote.url: https://keahub.eu` with the project name; the agent API at `/p/<project>/hub/`), and the hub reports each project's public address, so Kea does not build it from a pattern. Reader pages under `keahub.eu/p/<project>/` redirect to the subdomain.
7. **Reserved names:** www, id, api, hub, admin, mail, static, assets, doi, names starting with `xn--`, and no name ending in `-`.
8. **Logins are per project** (one origin each). A login on the apex that hands each subdomain its own token can come later if readers of several projects need it.

Order: concept ids and the apex resolver first or together with the subdomains, because they decide the hub's routes; then subdomain routing; version ids and the version store with the release step.

## Status (8 November 2026)

Built (Kea 1.13.0):

- Every page has a `uid:`: 128 random bits as 26 lower-case base32 characters, cited as `kea:<uid>`. `kea check --fix` writes one into each page without it, as one line after `id:`, and changes nothing else. `kea check` reports a malformed uid and a uid used by two pages as problems, and pages without one as a note.
- Each state of a page has a version id: 20 base32 characters of the sha256 of the page in a fixed form (front matter with sorted keys and without `order:`, body with whitespace collapsed), cited as `kea:<uid>@<version>`. "About this page" shows both.
- The build writes `_ids.json`. On a site, `/id/<uid>` redirects to the page, `/id/<uid>.json` answers its facts, and `/id/<uid>@<version>` shows that version: the page itself when it is current, else the stored text with a pointer to the current page.
- The hub keeps the Markdown of every version it is sent (`versions/<uid>/<version>.md`, append-only), refuses a publish whose ids belong to another project, and resolves `/id/…` on the apex: readers are sent to the project's own site (and its login); a project's agent with its key gets the facts as JSON.
- Per-project subdomains: with `project_domain:` in hub.yaml, `<project>.<domain>` serves that project at its root; reader pages under `/p/<project>/` redirect there; the agent API stays on the apex. Reserved names and names that are not valid subdomains are refused by `kea hub add`.

Also built (Kea 1.14.0): sign-in with ORCID on the hub. A reader signs in once at the apex; the hub owner approves new ORCID iDs (`kea hub users approve`); each project site gets its own host-only session through a one-time code from the apex (signed, 60 seconds, single use), so no cookie is shared between project subdomains; writes from another origin are refused. Roles per project (reader, commenter, steerer, owner); comments, tags and verdicts carry the reader's ORCID iD (`author_id`), and a confirmation records it in `confirmed:`. Project passwords keep working next to accounts. The cookie design follows a review by the infrastructure side (wiskelab, 8 November 2026).

Next: grants between projects for reading another project's status ([[s-federated-claims]]), and switching project passwords off per project once everyone has an account.
