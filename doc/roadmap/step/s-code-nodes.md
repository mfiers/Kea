---
id: s-code-nodes
uid: slrswsadnab2tog6gwmthxo5lm
type: step
title: "Scripts, code and libraries as full members of the graph"
short: "Today code is shown, not reasoned about: code pages exist, but a script is not a node with relations and a library is at most a hand-written resource. Proposal for discussion: scripts and libraries become nodes pinned to a commit or a version."
parent: q-order
status: planned
order: 12
relations:
  relies_on: [s-stable-ids]
---
## What Kea does now

- Every git-tracked file under `code_paths` (kea.yaml) gets a code page with line anchors and its Python symbols, and a list of the pages that point to it.
- Pages point to code with `sources:` or `[[code:path#symbol]]`; the link names the file, not the version of it that made the result.
- A library can be written by hand as a resource (`kind: software`, with `version`), and steps and results point to it with `uses:`. Nothing fills this in from `uv.lock` or `renv.lock`, so in practice it is left out.

So code is visible but has no place in the reasoning: Kea cannot say "result R3 was made by `normalise.py` at commit `a1b2c3d`, with scanpy 1.10.2", and so cannot say which results a later code change makes out of date.

## Proposal (Mark Fiers, 7 November 2026)

Scripts and code are full members of the Kea tree. Libraries are resources pinned to their git commit, so they can be nodes in the graph as well.

## Points to settle (Claude, 7 November 2026)

1. **Written or generated?** Hand-written pages for every script would double the work and go stale. Code nodes should be generated: one node per tracked file (and optionally per function), with the git blob hash as its version id. That hash is already a content hash, so it fits [[s-stable-ids]] without new machinery.
2. **Which edge records "made by"?** A result needs `made_by:` a code node *at a version*. The agent knows the commit when it runs the script; `kea run` (or the Makefile target) could write it into the result's front matter. Without that, the edge is a claim nobody checks.
3. **Libraries from the lock file.** `uv.lock` already pins every package with its version and hash. Generate one resource node per direct dependency (not the hundreds of transitive ones), with the version, the source URL and, for git dependencies, the commit. Hand-written resources stay for databases and datasets.
4. **What changes when code changes?** With 2 and 3 in place, a commit that changes `normalise.py` can mark every result made by its older version as "made by outdated code". That is the check [[s-living-claims]] needs, and the reason to do this at all.
5. **Granularity.** File-level nodes are cheap and robust. Function-level nodes need a parser per language and break on renames; leave them for later.

Open: should a code node appear on the relations map? With a few dozen scripts it makes the map unreadable; a separate "code" layer that can be switched on seems better.
